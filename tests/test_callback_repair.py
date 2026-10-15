"""Isolated maintenance tests. Never connect to a configured DB or voice service."""

import contextlib
import io
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

# Reuse the suite's existing isolated database/settings/SDK import bootstrap.
import test_callback_sync
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Query, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.repair_callback import main
from services import database
from services.bimpe_service import review_call_history
from services.callback_repair import RepairRefused, apply_review, review
from services.models import Booking, CallLog, MissedCall


@compiles(JSONB, "sqlite")
def sqlite_jsonb(_type, compiler, **kw):
    return "JSON"


NOW = datetime(2026, 10, 15, tzinfo=timezone.utc)
START = NOW - timedelta(days=3)
END = START + timedelta(hours=1)


def provider_call(cid="provider-1", **kwargs):
    values = dict(id=cid, destination="+12025550100", direction="outbound",
                  created_on=(START + timedelta(minutes=5)).isoformat())
    values.update(kwargs)
    return NS(**values)


def page(data, number=1, total=None, pages=1, limit=100, **kwargs):
    meta = dict(current_page=number, total_count=len(data) if total is None else total,
                page_count=pages, limit=limit, has_next_page=number < pages,
                has_previous_page=number > 1)
    meta.update(kwargs)
    return NS(data=data, meta=NS(**meta))


class HistoryTests(unittest.TestCase):
    def test_every_page_including_test_calls_is_requested_without_filters(self):
        client = Mock()
        client.calls.list.side_effect = [
            page([provider_call()], total=2, pages=2, limit=1),
            page([provider_call("provider-2")], number=2, total=2, pages=2, limit=1),
        ]
        self.assertEqual(len(review_call_history(client, "agent")), 2)
        self.assertEqual(client.calls.list.call_args_list[1].kwargs, dict(page=2, limit=100))
        client.calls.make.assert_not_called()

    def test_missing_metadata_and_incomplete_or_inconsistent_pages_are_rejected(self):
        cases = [
            [NS(data=[], meta=None)],
            [page([], total=1)],
            [page([provider_call()], total=2, pages=2, limit=1), page([], number=2, total=2, pages=2, limit=1)],
            [page([provider_call()], total=2, pages=2, limit=1), page([provider_call()], number=2, total=2, pages=2, limit=1)],
            [page([provider_call()], total=2, pages=2, limit=1), page([provider_call("other")], number=2, total=3, pages=2, limit=1)],
            [page([], total=0, has_next_page=True)],
            [page([provider_call()], number=2)],
        ]
        for pages in cases:
            with self.subTest(pages=pages):
                client = Mock()
                client.calls.list.side_effect = pages
                with self.assertRaises(ValueError):
                    review_call_history(client, "agent")

    def test_failure_on_later_page_does_not_return_partial_history(self):
        client = Mock()
        client.calls.list.side_effect = [
            page([provider_call()], total=2, pages=2, limit=1), RuntimeError("provider failed"),
        ]
        with self.assertRaises(RuntimeError):
            review_call_history(client, "agent")

    def test_empty_complete_history_is_valid(self):
        client = Mock()
        client.calls.list.return_value = page([], total=0, pages=0)
        self.assertEqual(review_call_history(client, "agent"), [])


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        for model in (MissedCall, CallLog, Booking):
            model.__table__.create(self.engine)
        self.factory = sessionmaker(bind=self.engine)
        self.db = self.factory()
        self.add_call("target")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_call(self, cid, **kwargs):
        values = dict(id=cid, business_id="salon", customer_name="Test",
                      customer_phone="+12025550100", missed_at=START - timedelta(minutes=10),
                      created_at=START - timedelta(minutes=10), status="callback_in_progress",
                      bimpe_call_id=None)
        values.update(kwargs)
        self.db.add(MissedCall(**values))
        self.db.commit()

    def add_log(self, owner="target", provider=None, **kwargs):
        values = dict(id="log-1", missed_call_id=owner, bimpe_call_id=provider, created_at=START)
        values.update(kwargs)
        self.db.add(CallLog(**values))
        self.db.commit()

    def reviewed(self, history=None):
        with self.factory() as db:
            return review(db, "target", [provider_call()] if history is None else history,
                          START, END, now=NOW)

    def stored(self, cid="target"):
        self.db.expire_all()
        return self.db.get(MissedCall, cid)

    def test_ambiguous_history_blocks_both_recovery_and_orphan_selection(self):
        result = self.reviewed([provider_call(), provider_call("provider-2")])
        self.assertEqual(result.action, "blocked")
        with self.assertRaises(RepairRefused):
            apply_review(self.factory, result, select_orphan_failed=True)
        self.assertIsNone(self.stored().bimpe_call_id)

    def test_ids_linked_to_another_record_or_its_logs_block_recovery(self):
        for log_only in (False, True):
            with self.subTest(log_only=log_only):
                self.add_call("other", status="callback_completed",
                              bimpe_call_id=None if log_only else "provider-1")
                if log_only:
                    self.add_log("other", "provider-1")
                self.assertEqual(self.reviewed().action, "blocked")
                self.db.query(CallLog).delete()
                self.db.query(MissedCall).filter_by(id="other").delete()
                self.db.commit()

    def test_competing_missing_id_attempt_blocks_even_one_provider_candidate(self):
        self.add_call("other")
        self.assertEqual(self.reviewed().action, "blocked")

    def test_pending_and_linked_and_terminal_records_cannot_be_changed(self):
        for status, call_id in (("pending_callback", None), ("failed", None),
                                ("callback_completed", None), ("callback_in_progress", "linked")):
            target = self.stored()
            target.status, target.bimpe_call_id = status, call_id
            self.db.commit()
            with self.assertRaises(RepairRefused):
                self.reviewed()

    def test_recent_or_invalid_windows_are_rejected(self):
        for start, end, hours in ((START, END, 0), (END, START, 24), (START, NOW, 24),
                                  (START - timedelta(days=1), END, 24)):
            with self.assertRaises(RepairRefused):
                review(self.db, "target", [], start, end, now=NOW, stale_hours=hours)

    def test_exact_phone_and_outbound_timing_not_suffix_matching(self):
        for call in (provider_call(destination="+442025550100"),
                     provider_call(direction="inbound"),
                     provider_call(created_on=(END + timedelta(seconds=1)).isoformat())):
            self.assertEqual(self.reviewed([call]).action, "mark-orphan-failed")
        self.assertEqual(self.reviewed([provider_call(destination="+1 (202) 555-0100")]).action, "recover")

    def test_malformed_provider_evidence_never_proves_orphan(self):
        for call in (provider_call(destination="2025550100"), provider_call(created_on="bad"),
                     provider_call(direction="unknown"), provider_call(created_on=None),
                     provider_call(created_on="2026-10-12T10:00:00")):
            with self.assertRaises(RepairRefused):
                self.reviewed([call])

    def test_related_logs_and_bookings_are_reported_and_prevent_orphan_guessing(self):
        self.add_log(provider="provider-1", call_status="ended")
        self.db.add(Booking(id="booking", missed_call_id="target", customer_name="Test",
                            customer_phone="+12025550100", service="Test", status="confirmed",
                            created_at=START))
        self.db.commit()
        result = self.reviewed()
        self.assertEqual(result.action, "recover")
        self.assertEqual(result.report["related_logs"][0]["call_status"], "ended")
        self.assertEqual(result.report["related_bookings"][0]["status"], "confirmed")
        self.assertEqual(self.reviewed([]).action, "blocked")

    def test_conflicting_log_id_or_recent_log_activity_blocks_recovery(self):
        self.add_log(provider="different")
        self.assertEqual(self.reviewed().action, "blocked")
        self.db.query(CallLog).delete()
        self.db.commit()
        self.add_log(provider="provider-1", created_at=NOW)
        self.assertEqual(self.reviewed().action, "blocked")

    def test_orphan_requires_explicit_selection_and_preserves_other_records(self):
        self.add_call("ordinary", status="pending_callback")
        result = self.reviewed([])
        with self.assertRaises(RepairRefused):
            apply_review(self.factory, result)
        self.assertEqual(self.stored().status, "callback_in_progress")
        apply_review(self.factory, result, select_orphan_failed=True)
        self.assertEqual(self.stored().status, "failed")
        self.assertEqual(self.stored("ordinary").status, "pending_callback")
        self.assertEqual(self.db.query(MissedCall).count(), 2)

    def test_recovery_only_attaches_id_and_never_reclassifies_or_retries(self):
        result = self.reviewed()
        with self.assertRaises(RepairRefused):
            apply_review(self.factory, result, select_orphan_failed=True)
        apply_review(self.factory, result)
        self.assertEqual(self.stored().bimpe_call_id, "provider-1")
        self.assertEqual(self.stored().status, "callback_in_progress")
        self.assertEqual(self.db.query(CallLog).count(), 0)
        self.assertEqual(self.db.query(Booking).count(), 0)

    def test_stale_status_id_logs_booking_and_associations_abort(self):
        for change in ("status", "id", "log", "booking", "association"):
            with self.subTest(change=change):
                result = self.reviewed()
                if change == "status":
                    self.stored().status = "pending_callback"
                elif change == "id":
                    self.stored().bimpe_call_id = "newer-id"
                elif change == "log":
                    self.add_log()
                elif change == "booking":
                    self.db.add(Booking(id="new-booking", missed_call_id="target",
                                        customer_name="Test", customer_phone="+12025550100",
                                        service="Test", status="confirmed"))
                else:
                    self.add_call("other", status="callback_completed", bimpe_call_id="provider-1")
                self.db.commit()
                with self.assertRaises(RepairRefused):
                    apply_review(self.factory, result)
                self.db.query(CallLog).delete()
                self.db.query(Booking).delete()
                self.db.query(MissedCall).filter_by(id="other").delete()
                target = self.stored()
                target.status, target.bimpe_call_id = "callback_in_progress", None
                self.db.commit()

    def test_non_exact_update_count_rolls_back_real_update(self):
        update = Query.update
        for count in (0, 2):
            def wrong_count(query, *args, **kwargs):
                update(query, *args, **kwargs)
                return count
            with patch.object(Query, "update", wrong_count), self.assertRaises(RepairRefused):
                apply_review(self.factory, self.reviewed())
            self.assertIsNone(self.stored().bimpe_call_id)

    def cli(self, history=None, extra=()):
        output = io.StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": "isolated", "BIMPEAI_API_KEY": "test-secret",
                                    "BIMPE_AGENT_ID": "test-agent"}, clear=True), \
                patch.object(database, "SessionLocal", self.factory, create=True), \
                patch("services.bimpe_service.review_call_history",
                      return_value=[provider_call()] if history is None else history), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main(["--missed-call-id", "target", "--attempt-start", START.isoformat(),
                         "--attempt-end", END.isoformat(), *extra])
        return code, output.getvalue()

    def test_cli_defaults_to_dry_run_and_requires_id_and_timezone(self):
        code, output = self.cli()
        self.assertEqual(code, 0)
        self.assertIn('"mode": "dry-run"', output)
        self.assertNotIn("test-secret", output)
        self.assertIsNone(self.stored().bimpe_call_id)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main([])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["--missed-call-id", "target", "--attempt-start", "2026-01-01",
                  "--attempt-end", END.isoformat()])

    def test_cli_apply_and_orphan_explicit_selection(self):
        code, _ = self.cli([])
        self.assertEqual(code, 0)
        self.assertEqual(self.stored().status, "callback_in_progress")
        code, _ = self.cli([], ["--apply"])
        self.assertEqual(code, 2)
        self.assertEqual(self.stored().status, "callback_in_progress")
        code, _ = self.cli([], ["--apply", "--mark-orphan-failed"])
        self.assertEqual(code, 0)
        self.assertEqual(self.stored().status, "failed")

    def test_cli_recovery_apply_changes_only_one_target(self):
        self.add_call("ordinary", status="pending_callback")
        code, output = self.cli(extra=["--apply"])
        self.assertEqual(code, 0)
        self.assertIn("exactly one guarded update", output)
        self.assertEqual(self.stored().bimpe_call_id, "provider-1")
        self.assertEqual(self.stored("ordinary").status, "pending_callback")

    def test_cli_rejects_database_change_during_provider_review(self):
        def changing_history():
            self.stored().customer_phone = "+12025550199"
            self.db.commit()
            return [provider_call(destination="+12025550199")]
        with patch.dict(os.environ, {"DATABASE_URL": "isolated", "BIMPEAI_API_KEY": "secret",
                                    "BIMPE_AGENT_ID": "agent"}), \
                patch.object(database, "SessionLocal", self.factory, create=True), \
                patch("services.bimpe_service.review_call_history", side_effect=changing_history), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = main(["--missed-call-id", "target", "--attempt-start", START.isoformat(),
                         "--attempt-end", END.isoformat(), "--apply"])
        self.assertEqual(code, 2)
        self.assertIsNone(self.stored().bimpe_call_id)

    def test_missing_environment_fails_before_database_or_provider_access(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("services.bimpe_service.review_call_history") as history, \
                contextlib.redirect_stderr(io.StringIO()):
            code = main(["--missed-call-id", "target", "--attempt-start", START.isoformat(),
                         "--attempt-end", END.isoformat(), "--apply"])
        self.assertEqual(code, 2)
        history.assert_not_called()

    def test_cli_provider_exception_is_redacted_and_does_not_write(self):
        with patch("services.bimpe_service.review_call_history",
                   side_effect=RuntimeError("postgresql://private-secret")):
            # Do not use cli() here: its history patch would mask this failure.
            with patch.dict(os.environ, {"DATABASE_URL": "isolated", "BIMPEAI_API_KEY": "secret",
                                        "BIMPE_AGENT_ID": "agent"}), \
                    patch.object(database, "SessionLocal", self.factory, create=True), \
                    contextlib.redirect_stderr(io.StringIO()) as output:
                code = main(["--missed-call-id", "target", "--attempt-start", START.isoformat(),
                             "--attempt-end", END.isoformat(), "--apply"])
            self.assertEqual(code, 2)
            self.assertNotIn("private-secret", output.getvalue())
        self.assertIsNone(self.stored().bimpe_call_id)


if __name__ == "__main__":
    unittest.main()
