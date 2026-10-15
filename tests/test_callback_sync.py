"""Regression tests using an isolated SQLite database and a stubbed voice SDK.

Run: python -m unittest discover -s tests -v
No production database, environment secrets, or outbound calls are used.
"""

import sys
import types
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.pool import StaticPool


# Install isolated dependencies before importing application modules. In
# particular, never import the production database or initialize a real SDK.
database = types.ModuleType("services.database")
database.Base = declarative_base()


def unavailable_database():
    raise AssertionError("The test database dependency must be overridden.")


database.get_db = unavailable_database
sys.modules["services.database"] = database
settings = types.ModuleType("config.settings")
settings.BIMPEAI_API_KEY = None
settings.BIMPE_AGENT_ID = None
sys.modules["config.settings"] = settings
sdk = types.ModuleType("bimpeai")
sdk.BimpeAI = Mock()
sys.modules["bimpeai"] = sdk

from main import app
from api import routes
from services.callback_status import callback_status_from_details
from services.missed_call_services import synchronize_callback_status
from services.models import Booking, MissedCall


def details(**overrides):
    values = {
        "status": "ended",
        "answered_at": "2026-01-01T10:00:01Z",
        "started_at": "2026-01-01T10:00:00Z",
        "ended_at": "2026-01-01T10:01:00Z",
        "error_reason": None,
        "conversation_logs": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CallbackSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        # CallLog's PostgreSQL JSONB column is irrelevant to these endpoints.
        MissedCall.__table__.create(self.engine)
        Booking.__table__.create(self.engine)
        self.db = Session(self.engine)

        def test_database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[database.get_db] = test_database
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def add_call(self, status="callback_in_progress", bimpe_call_id="attempt-1"):
        call = MissedCall(
            id="test-call",
            business_id="test-business",
            customer_name="Test customer",
            customer_phone="+12025550100",
            missed_at=datetime.now(timezone.utc),
            status=status,
            bimpe_call_id=bimpe_call_id,
        )
        self.db.add(call)
        self.db.commit()
        return call

    def stored_call(self):
        self.db.expire_all()
        return self.db.get(MissedCall, "test-call")

    @patch("api.routes.retrieve_call_details")
    def test_ended_answered_call_is_saved_without_a_confirmed_booking(self, retrieve):
        self.add_call()
        retrieve.return_value = details()
        response = self.client.get("/api/callback/test-call/result")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["missed_call"]["status"], "callback_completed")
        self.assertEqual(response.json()["booking"]["status"], "needs_follow_up")
        self.assertEqual(self.stored_call().status, "callback_completed")
        self.assertEqual(self.db.query(Booking).count(), 0)
        listing = self.client.get("/api/missed_calls").json()
        self.assertEqual(listing[0]["status"], "callback_completed")

    @patch("api.routes.retrieve_call_details")
    def test_repeated_result_refreshes_do_not_duplicate_a_booking(self, retrieve):
        self.add_call()
        retrieve.return_value = details(conversation_logs=[
            SimpleNamespace(
                role="assistant",
                message="Confirmed for Saturday at 4:00 PM.",
                created_at="2026-01-01T10:00:30Z",
            )
        ])
        for _ in range(2):
            response = self.client.get("/api/callback/test-call/result")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["booking"]["status"], "confirmed")
        self.assertEqual(self.db.query(Booking).count(), 1)
        self.assertEqual(self.stored_call().status, "callback_completed")

    @patch("api.routes.retrieve_call_details")
    def test_ringing_call_does_not_complete_or_book(self, retrieve):
        self.add_call()
        retrieve.return_value = details(status="ringing", answered_at=None, ended_at=None)
        response = self.client.get("/api/callback/test-call/result")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_call().status, "callback_in_progress")
        self.assertEqual(self.db.query(Booking).count(), 0)

    @patch("api.routes.retrieve_call_details")
    def test_unanswered_ended_call_is_failed(self, retrieve):
        self.add_call()
        retrieve.return_value = details(answered_at=None)
        response = self.client.get("/api/callback/test-call/result")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["missed_call"]["status"], "failed")
        self.assertEqual(self.stored_call().status, "failed")

    @patch("api.routes.place_callback_call")
    def test_provider_errors_release_failed_attempt_for_both_trigger_routes(self, place):
        for path in ["/api/callback/test-call/trigger", "/api/callback/test"]:
            with self.subTest(path=path):
                self.db.query(MissedCall).delete()
                self.db.commit()
                self.add_call(status="pending_callback", bimpe_call_id=None)
                place.side_effect = RuntimeError("SDK error")
                response = self.client.post(path)
                self.assertEqual(response.status_code, 502)
                self.assertEqual(self.stored_call().status, "failed")
                self.assertIsNone(self.stored_call().bimpe_call_id)

    @patch("api.routes.place_callback_call")
    def test_missing_provider_id_does_not_leave_an_active_callback(self, place):
        self.add_call(status="pending_callback", bimpe_call_id=None)
        place.return_value = SimpleNamespace(call_id=None)
        response = self.client.post("/api/callback/test-call/trigger")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.stored_call().status, "failed")

    @patch("api.routes.place_callback_call")
    def test_retry_replaces_old_attempt_id_only_after_provider_accepts(self, place):
        self.add_call(status="failed", bimpe_call_id="old-attempt")

        def accepted(**kwargs):
            current = self.stored_call()
            self.assertEqual(current.status, "callback_in_progress")
            self.assertIsNone(current.bimpe_call_id)
            return SimpleNamespace(call_id="new-attempt")

        place.side_effect = accepted
        response = self.client.post("/api/callback/test-call/trigger")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_call().bimpe_call_id, "new-attempt")
        self.assertEqual(self.stored_call().status, "callback_in_progress")
        place.assert_called_once()

    @patch("api.routes.place_callback_call")
    def test_duplicate_triggers_do_not_place_another_call(self, place):
        self.add_call(status="pending_callback", bimpe_call_id=None)
        place.return_value = SimpleNamespace(call_id="accepted-attempt")
        self.assertEqual(self.client.post("/api/callback/test-call/trigger").status_code, 200)
        self.assertEqual(self.client.post("/api/callback/test-call/trigger").status_code, 400)
        place.assert_called_once()

    @patch("api.routes.place_callback_call")
    def test_stale_pending_object_cannot_bypass_atomic_claim(self, place):
        self.add_call(status="pending_callback", bimpe_call_id=None)
        with Session(self.engine) as other:
            stale = other.get(MissedCall, "test-call")
            routes.mark_callback_started(self.db, "test-call")
            with self.assertRaises(routes.HTTPException) as caught:
                routes._start_callback(other, stale)
            self.assertEqual(caught.exception.status_code, 409)
        place.assert_not_called()

    @patch("api.routes.retrieve_call_details")
    def test_old_result_cannot_overwrite_newer_attempt(self, retrieve):
        self.add_call()

        def old_result(_):
            current = self.stored_call()
            current.bimpe_call_id = "new-attempt"
            self.db.commit()
            return details()

        retrieve.side_effect = old_result
        response = self.client.get("/api/callback/test-call/result")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.stored_call().status, "callback_in_progress")
        self.assertEqual(self.stored_call().bimpe_call_id, "new-attempt")

    def test_late_active_result_cannot_regress_terminal_status(self):
        self.add_call(status="callback_completed")
        synchronize_callback_status(self.db, "test-call", "attempt-1", details(status="ringing", ended_at=None))
        self.assertEqual(self.stored_call().status, "callback_completed")

    @patch("api.routes.retrieve_call_details")
    @patch("api.routes.place_callback_call")
    def test_legacy_missing_ids_do_not_invent_an_outcome_or_place_a_call(self, place, retrieve):
        self.add_call(bimpe_call_id=None)
        self.assertEqual(self.client.get("/api/callback/test-call/result").status_code, 400)
        self.assertEqual(self.stored_call().status, "callback_in_progress")
        place.assert_not_called()
        retrieve.assert_not_called()

    def test_published_origin_matches_cors_allowlist_without_slash(self):
        origin = "https://second-ring-dashboard.replit.app"
        response = self.client.options("/api/missed_calls", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], origin)

    def test_unlisted_origins_stay_blocked(self):
        response = self.client.options("/api/missed_calls", headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        })
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_provider_outcome_mapping(self):
        for phase in ["failed", "busy", "no-answer", "cancelled", "error"]:
            with self.subTest(phase=phase):
                self.assertEqual(callback_status_from_details(details(status=phase)), "failed")
        self.assertEqual(callback_status_from_details(details(status="completed", answered_at=None)), "callback_completed")
        self.assertEqual(callback_status_from_details(details(error_reason="provider error")), "failed")
        self.assertIsNone(callback_status_from_details(details(status="unknown", ended_at=None)))


if __name__ == "__main__":
    unittest.main()
