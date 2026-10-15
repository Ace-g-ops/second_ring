"""Real PostgreSQL checks on a disposable, local-only cluster.

Skips when PostgreSQL binaries are unavailable. Never reads DATABASE_URL.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_callback_sync  # Isolated model/settings bootstrap; no configured DB.
from test_callback_repair import END, NOW, START, provider_call
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from services import callback_repair
from services.callback_repair import RepairRefused, apply_review, review
from services.models import Booking, CallLog, MissedCall


@unittest.skipUnless(shutil.which("initdb") and shutil.which("pg_ctl"),
                     "Local PostgreSQL binaries are not installed.")
class PostgresRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="callback-repair-pg-")
        cls.data = str(Path(cls.temp.name) / "data")
        cls.started = False
        try:
            subprocess.run(["initdb", "-D", cls.data, "-U", "maintenance_test",
                            "--auth=trust", "--no-instructions"],
                           check=True, capture_output=True)
            subprocess.run(["pg_ctl", "-D", cls.data, "-l", str(Path(cls.temp.name) / "server.log"),
                            "-o", f"-k {cls.temp.name} -p 56439 -c listen_addresses=''",
                            "-w", "start"], check=True, capture_output=True)
            cls.started = True
            # A Unix socket inside a mode-0700 temp directory; no network listener.
            cls.engine = create_engine(URL.create(
                "postgresql+psycopg", username="maintenance_test", database="postgres",
                query={"host": cls.temp.name, "port": "56439"},
            ))
            cls.factory = sessionmaker(bind=cls.engine)
        except Exception:
            cls.cleanup()
            raise

    @classmethod
    def cleanup(cls):
        if hasattr(cls, "engine"):
            cls.engine.dispose()
        if cls.started:
            subprocess.run(["pg_ctl", "-D", cls.data, "-m", "immediate", "-w", "stop"],
                           check=True, capture_output=True)
        cls.temp.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    def setUp(self):
        for model in (MissedCall, CallLog, Booking):
            model.__table__.create(self.engine)
        with self.factory.begin() as db:
            db.add(MissedCall(id="target", business_id="salon", customer_name="Test",
                             customer_phone="+12025550100", missed_at=START, created_at=START,
                             status="callback_in_progress"))

    def tearDown(self):
        for model in (Booking, CallLog, MissedCall):
            model.__table__.drop(self.engine)

    def reviewed(self):
        with self.factory() as db:
            return review(db, "target", [provider_call()], START, END, now=NOW)

    def test_real_postgres_guarded_recovery_and_duplicate_apply_refusal(self):
        reviewed = self.reviewed()
        apply_review(self.factory, reviewed)
        with self.factory() as db:
            target = db.get(MissedCall, "target")
            self.assertEqual(target.bimpe_call_id, "provider-1")
            self.assertEqual(target.status, "callback_in_progress")
        with self.assertRaises(RepairRefused):
            apply_review(self.factory, reviewed)

    def test_same_status_missing_id_after_a_new_attempt_is_still_stale(self):
        reviewed = self.reviewed()
        with self.factory.begin() as db:
            db.query(MissedCall).filter_by(id="target").update({"status": "pending_callback"})
        with self.factory.begin() as db:
            db.query(MissedCall).filter_by(id="target").update({"status": "callback_in_progress"})
        with self.assertRaises(RepairRefused):
            apply_review(self.factory, reviewed)
        with self.factory() as db:
            self.assertIsNone(db.get(MissedCall, "target").bimpe_call_id)

    def test_transaction_blocks_concurrent_new_provider_associations(self):
        reviewed = self.reviewed()
        real_evidence = callback_repair.evidence
        blocked = []

        def check_lock(db, target_id):
            with self.factory() as other:
                other.execute(text("SET LOCAL lock_timeout = '100ms'"))
                try:
                    other.add(MissedCall(id="competitor", business_id="salon",
                                         customer_name="Test", customer_phone="+12025550199",
                                         missed_at=START, status="callback_completed",
                                         bimpe_call_id="provider-1"))
                    other.flush()
                except OperationalError:
                    blocked.append(True)
                    other.rollback()
                else:
                    self.fail("Concurrent association was not blocked by maintenance locks.")
            return real_evidence(db, target_id)

        with patch.object(callback_repair, "evidence", side_effect=check_lock):
            apply_review(self.factory, reviewed)
        self.assertEqual(blocked, [True])
        with self.factory() as db:
            self.assertEqual(db.query(MissedCall).count(), 1)
            self.assertEqual(db.get(MissedCall, "target").bimpe_call_id, "provider-1")


if __name__ == "__main__":
    unittest.main()
