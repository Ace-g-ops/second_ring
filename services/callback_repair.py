"""Offline operator maintenance only. Never imported by HTTP routes."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import DDL, String, cast, literal_column

from services.models import Booking, CallLog, MissedCall
from services.missed_call_services import get_missed_call_by_id


class RepairRefused(ValueError):
    pass


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise RepairRefused("String timestamps must include a timezone.")
    if not isinstance(value, datetime):
        raise RepairRefused("Missing or invalid timestamp.")
    # Existing models use datetime.utcnow; PostgreSQL/SQLite may return naive UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def phone(value):
    # Only normalize formatting, never guess a country code or compare suffixes.
    value = re.sub(r"[\s().-]", "", value or "")
    if not re.fullmatch(r"\+[1-9]\d{6,14}", value):
        raise RepairRefused("An exact international recipient number is required.")
    return value


def _row(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def evidence(db, missed_call_id):
    target = get_missed_call_by_id(db, missed_call_id)
    if target is None:
        raise RepairRefused("Missed call not found.")
    calls = db.query(MissedCall).order_by(MissedCall.id).all()
    logs = db.query(CallLog).order_by(CallLog.id).all()
    bookings = db.query(Booking).filter_by(missed_call_id=missed_call_id).order_by(Booking.id).all()
    related_logs = [log for log in logs if log.missed_call_id == missed_call_id]
    # Include every existing provider association, not just the target's phone.
    associations = {}
    for item in calls + logs:
        if item.bimpe_call_id:
            owner = item.id if isinstance(item, MissedCall) else item.missed_call_id
            associations.setdefault(item.bimpe_call_id, set()).add(owner)
    # Older unresolved attempts for this recipient can own the same provider call.
    competitors = []
    for item in calls:
        if item.id == missed_call_id or item.status != "callback_in_progress":
            continue
        try:
            same_phone = phone(item.customer_phone) == phone(target.customer_phone)
        except RepairRefused:
            # An unparseable number cannot safely establish a different recipient.
            same_phone = True
        if same_phone and not item.bimpe_call_id:
            competitors.append(_row(item))
    snapshot = {
        "target": _row(target),
        "logs": [_row(log) for log in related_logs],
        "bookings": [_row(booking) for booking in bookings],
        "competitors": competitors,
        "associations": {key: sorted(owners) for key, owners in sorted(associations.items())},
    }
    if db.get_bind().dialect.name == "postgresql":
        # Catch ABA: a callback can leave/re-enter the same status with a NULL
        # ID without changing any existing application timestamp.
        snapshot["target_version"] = db.query(cast(literal_column("xmin"), String)).select_from(
            MissedCall
        ).filter(MissedCall.id == missed_call_id).scalar()
    return snapshot


@dataclass(frozen=True)
class Review:
    missed_call_id: str
    fingerprint: str
    action: str
    call_id: str | None
    report: dict


def review(db, missed_call_id, history, start, end, *, now=None, stale_hours=24):
    """History must come from review_call_history, not a filtered provider page."""
    start, end, now = utc(start), utc(end), utc(now or datetime.now(timezone.utc))
    if stale_hours < 1 or start >= end or end > now - timedelta(hours=stale_hours):
        raise RepairRefused("Use an ordered attempt window ending at least stale-hours ago (minimum 1 hour).")
    data = evidence(db, missed_call_id)
    target = data["target"]
    if target["status"] != "callback_in_progress" or target["bimpe_call_id"] is not None:
        raise RepairRefused("Only callback_in_progress records with a NULL provider ID are eligible.")
    if start < max(utc(target["created_at"]), utc(target["missed_at"])):
        raise RepairRefused("The attempt window cannot begin before the missed call was recorded.")
    recipient = phone(target["customer_phone"])
    candidates = []
    for call in history:
        # Bad/missing provider evidence blocks BOTH recovery and orphan selection.
        try:
            destination = phone(call.destination)
            created = utc(call.created_on)
            direction = call.direction.lower()
        except (AttributeError, TypeError, ValueError):
            raise RepairRefused("Provider history has unverifiable recipient/timing/direction evidence.") from None
        if direction not in ("inbound", "outbound"):
            raise RepairRefused("Provider history has an unknown direction.")
        if destination == recipient and direction == "outbound" and start <= created <= end:
            candidates.append(call.id)
    log_ids = {log["bimpe_call_id"] for log in data["logs"] if log["bimpe_call_id"]}
    reasons = []
    if any(
        log[key] is not None and utc(log[key]) > end
        for log in data["logs"]
        for key in ("created_at", "answered_at", "ended_at")
    ):
        reasons.append("Related log activity is newer than the selected attempt window.")
    if data["competitors"]:
        reasons.append("Another unresolved attempt has the same or unverifiable recipient.")
    if len(candidates) > 1:
        reasons.append("Multiple provider calls match the window.")
    if log_ids and log_ids != set(candidates):
        reasons.append("Related log IDs disagree with provider history/window.")
    if any(set(data["associations"].get(cid, [])) - {missed_call_id} for cid in candidates):
        reasons.append("A matching provider ID is already linked to another missed call.")
    if not candidates and (data["bookings"] or data["logs"]):
        # Even ID-less logs may describe an actual call; absence is not proof.
        reasons.append("Related bookings/logs require manual investigation before declaring an orphan.")
    action = "blocked" if reasons else ("recover" if candidates else "mark-orphan-failed")
    report = {
        "missed_call_id": missed_call_id,
        "expected_status": target["status"],
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "history_calls_reviewed": len(history), "history_complete": True,
        "matching_call_ids": candidates,
        "related_logs": [
            {key: log[key] for key in ("id", "bimpe_call_id", "call_status", "created_at", "answered_at", "ended_at")}
            for log in data["logs"]
        ],
        "related_bookings": [
            {key: booking[key] for key in ("id", "status", "created_at")}
            for booking in data["bookings"]
        ],
        "action": action, "reasons": reasons,
    }
    return Review(missed_call_id, _digest(data), action, candidates[0] if len(candidates) == 1 else None, report)


def apply_review(session_factory, reviewed, *, select_orphan_failed=False):
    """Recheck evidence and update exactly one row in a short transaction."""
    if reviewed.action == "blocked":
        raise RepairRefused("Ambiguous evidence: no changes permitted.")
    if reviewed.action == "mark-orphan-failed" and not select_orphan_failed:
        raise RepairRefused("Orphan failure requires explicit --mark-orphan-failed selection.")
    if reviewed.action == "recover" and select_orphan_failed:
        raise RepairRefused("A provider call exists; orphan failure is not permitted.")
    with session_factory() as db, db.begin():
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            # Existing writers do not share an advisory-lock convention. Table
            # locks close the association-check/write race, including new logs.
            # Held only for the local recheck + single UPDATE, never HTTP calls.
            db.execute(DDL("LOCK TABLE missed_calls, call_logs, bookings IN SHARE ROW EXCLUSIVE MODE"))
        elif dialect != "sqlite":
            raise RepairRefused("Unsupported database dialect for guarded maintenance.")
        current = evidence(db, reviewed.missed_call_id)
        if _digest(current) != reviewed.fingerprint:
            raise RepairRefused("Database evidence changed since review; rerun dry-run.")
        values = (
            {"bimpe_call_id": reviewed.call_id}
            if reviewed.action == "recover"
            else {"status": "failed"}
        )
        count = db.query(MissedCall).filter(
            MissedCall.id == reviewed.missed_call_id,
            MissedCall.status == "callback_in_progress",
            MissedCall.bimpe_call_id.is_(None),
        ).update(values, synchronize_session=False)
        if count != 1:
            raise RepairRefused("Expected exactly one guarded update; transaction rolled back.")
