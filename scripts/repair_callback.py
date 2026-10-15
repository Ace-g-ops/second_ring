"""Operator-only command; no web endpoint and no call placement/retry."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Use an ISO timestamp with timezone.") from None


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--missed-call-id", required=True)
    result.add_argument("--attempt-start", type=timestamp, required=True)
    result.add_argument("--attempt-end", type=timestamp, required=True)
    result.add_argument("--stale-hours", type=int, default=24)
    result.add_argument("--apply", action="store_true", help="Commit one guarded repair (default: dry-run).")
    result.add_argument("--mark-orphan-failed", action="store_true", help="Explicitly select orphan failure, only if complete history has no matching call.")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    # Do not allow SDK/SQLAlchemy exception logging to disclose connection URLs,
    # authorization headers, recipient details or environment configuration.
    logging.disable(logging.CRITICAL)
    try:
        # Require process environment, not a silently discovered .env file.
        for key in ("DATABASE_URL", "BIMPEAI_API_KEY", "BIMPE_AGENT_ID"):
            if not os.environ.get(key):
                print(f"Required environment variable is missing: {key}", file=sys.stderr)
                return 2
        from services.database import SessionLocal
        from services.bimpe_service import review_call_history
        from services.callback_repair import RepairRefused, _digest, apply_review, evidence, review

        with SessionLocal() as db:
            before = _digest(evidence(db, args.missed_call_id))
        history = review_call_history()
        with SessionLocal() as db:
            reviewed = review(
                db, args.missed_call_id, history, args.attempt_start,
                args.attempt_end, stale_hours=args.stale_hours,
            )
        if reviewed.fingerprint != before:
            raise RepairRefused("Database evidence changed during provider history review.")
        print(json.dumps({"mode": "apply" if args.apply else "dry-run", **reviewed.report}, default=str, indent=2))
        if reviewed.action == "blocked":
            return 2
        if args.mark_orphan_failed and reviewed.action != "mark-orphan-failed":
            raise RepairRefused("A provider call exists; orphan failure is not permitted.")
        if args.apply:
            apply_review(SessionLocal, reviewed, select_orphan_failed=args.mark_orphan_failed)
            print("Committed exactly one guarded update. No call was placed or retried.")
        else:
            print("No changes made. Re-run with --apply to commit; orphan failure also requires --mark-orphan-failed.")
        return 0
    except Exception:
        # Never interpolate external exception messages: they may contain secrets.
        print("Repair refused or review failed; no repair committed. Check configuration, complete history, and current evidence, then rerun dry-run.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
