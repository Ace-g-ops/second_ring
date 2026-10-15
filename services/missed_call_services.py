from datetime import datetime, timezone
from sqlalchemy.orm import Session
from services.models import MissedCall


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
        customer_phone=customer_phone,
        missed_at=missed_at,
        status="pending_callback"
    )

    db.add(missed_call)
    db.commit()
    db.refresh(missed_call)

    return missed_call


def mark_callback_started(db: Session, missed_call_id: str):
    missed_call = get_missed_call_by_id(db, missed_call_id)

    if not missed_call:
        return None

    missed_call.status = "callback_in_progress"
    db.commit()
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
    bimpe_call_id: str
):
    missed_call = get_missed_call_by_id(db, missed_call_id)

    if not missed_call:
        return None

    missed_call.bimpe_call_id = bimpe_call_id
    db.commit()
    db.refresh(missed_call)

    return missed_call