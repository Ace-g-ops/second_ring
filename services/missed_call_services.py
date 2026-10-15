from datetime import datetime, timezone

from sqlalchemy.orm import Session

from services.models import MissedCall
from services.callback_status import callback_status_from_details
from services.security import encrypt_phone, hash_phone


def get_missed_calls(db: Session):
    return (
        db.query(MissedCall)
        .order_by(MissedCall.missed_at.desc())
        .all()
    )


def get_missed_call_by_id(db: Session, missed_call_id: str):
    return (
        db.query(MissedCall)
        .filter(MissedCall.id == missed_call_id)
        .first()
    )


def get_pending_missed_call(db: Session):
    return (
        db.query(MissedCall)
        .filter(MissedCall.status == "pending_callback")
        .order_by(MissedCall.missed_at.asc())
        .first()
    )


def create_missed_call(
    db: Session,
    missed_call_id: str,
    business_id: str,
    customer_name: str,
    customer_phone: str,
    missed_at: datetime,
):
    missed_call = MissedCall(
        id=missed_call_id,
        business_id=business_id,
        customer_name=customer_name,
        customer_phone_encrypted=encrypt_phone(customer_phone),
        phone_hash=hash_phone(customer_phone),
        missed_at=missed_at,
        status="pending_callback",
    )

    db.add(missed_call)
    db.commit()
    db.refresh(missed_call)

    return missed_call


def mark_callback_started(db: Session, missed_call_id: str):
    updated = (
        db.query(MissedCall)
        .filter(
            MissedCall.id == missed_call_id,
            MissedCall.status.in_(["pending_callback", "failed"]),
        )
        .update(
            {"status": "callback_in_progress", "bimpe_call_id": None},
            synchronize_session=False,
        )
    )
    db.commit()

    if not updated:
        return None

    missed_call = get_missed_call_by_id(db, missed_call_id)
    db.refresh(missed_call)

    return missed_call


def mark_callback_failed(db: Session, missed_call_id: str):
    (
        db.query(MissedCall)
        .filter(
            MissedCall.id == missed_call_id,
            MissedCall.status == "callback_in_progress",
            MissedCall.bimpe_call_id.is_(None),
        )
        .update({"status": "failed"}, synchronize_session=False)
    )
    db.commit()


def synchronize_callback_status(
    db: Session,
    missed_call_id: str,
    bimpe_call_id: str,
    call_details,
):
    status = callback_status_from_details(call_details)

    if status:
        query = db.query(MissedCall).filter(
            MissedCall.id == missed_call_id,
            MissedCall.bimpe_call_id == bimpe_call_id,
        )

        if status == "callback_in_progress":
            query = query.filter(
                MissedCall.status.in_(
                    ["pending_callback", "callback_in_progress"]
                )
            )

        query.update({"status": status}, synchronize_session=False)
        db.commit()

    missed_call = get_missed_call_by_id(db, missed_call_id)

    if missed_call:
        db.refresh(missed_call)

    return missed_call


def mark_callback_completed(db: Session, missed_call_id: str):
    missed_call = get_missed_call_by_id(db, missed_call_id)

    if not missed_call:
        return None

    missed_call.status = "callback_completed"
    db.commit()
    db.refresh(missed_call)

    return missed_call


def attach_bimpe_call_id(
    db: Session,
    missed_call_id: str,
    bimpe_call_id: str,
):
    missed_call = get_missed_call_by_id(db, missed_call_id)

    if not missed_call:
        return None

    missed_call.bimpe_call_id = bimpe_call_id
    db.commit()
    db.refresh(missed_call)

    return missed_call