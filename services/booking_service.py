from datetime import datetime, timezone
from sqlalchemy.orm import Session
from services.models import Booking


def get_bookings(db: Session):
    return (
        db.query(Booking)
        .order_by(Booking.created_at.desc())
        .all()
    )


def get_booking_by_missed_call_id(db: Session, missed_call_id: str):
    return (
        db.query(Booking)
        .filter(Booking.missed_call_id == missed_call_id)
        .first()
    )


def extract_booking(transcript, missed_call):
    full_text = " ".join(
        message["message"]
        for message in transcript
    ).lower()

    slot = None

    if "confirmed for saturday at 4:00 pm" in full_text:
        slot = "Saturday 4:00 PM"
    elif "confirmed for saturday at 11:00 am" in full_text:
        slot = "Saturday 11:00 AM"

    return {
        "id": f"BK-{missed_call.id}",
        "missed_call_id": missed_call.id,
        "customer_name": missed_call.customer_name,
        "customer_phone": missed_call.customer_phone,
        "service": "Haircut",
        "slot": slot,
        "status": "confirmed" if slot else "needs_follow_up",
        "created_at": datetime.now(timezone.utc)
    }


def save_booking(db: Session, booking_data: dict):
    existing = get_booking_by_missed_call_id(
        db,
        booking_data["missed_call_id"]
    )

    if existing:
        return existing

    booking = Booking(**booking_data)

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return booking