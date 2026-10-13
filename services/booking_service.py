import json
import re
from pathlib import Path
from datetime import datetime, timezone

from config.settings import BOOKINGS_PATH
from services.missed_call_services import save_json, load_json

BOOKINGS_FILE = Path("booking.json")

def get_bookings():
    return load_json(BOOKINGS_PATH)

## function for creating bookings
def create_booking(
    missed_call_id,
    customer_name,
    customer_phone,
    service,
    appointment_time,
):
    bookings = get_bookings()

    booking = {
        "id": f"BK-{len(bookings) + 1:03d}",
        "missed_call_id": missed_call_id,
        "business_id": "sharp-cuts",
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service": service,
        "appointment_time": appointment_time,
        "status": "booked_by_agent",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    bookings.append(booking)
    save_json(BOOKINGS_PATH, bookings) ## this saves bookings to the booking path.
    return booking


def create_follow_up(
    missed_call_id,
    customer_name,
    customer_phone,
    reason,
):
    bookings = get_bookings()

    follow_up = {
        "id": f"BK-{len(bookings) + 1:03d}",
        "missed_call_id": missed_call_id,
        "business_id": "sharp-cuts",
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "service": None,
        "appointment_time": None,
        "status": "needs_owner_follow_up",
        "reason": reason,
        "created_at": datetime.utcnow().isoformat()
    }

    bookings.append(follow_up)
    save_json(BOOKINGS_PATH, bookings)

    return follow_up

def extract_booking(transcript, missed_call):
    text = " ".join(
        m["message"] for m in transcript if m["role"] == "user"
    ).lower()

    slot = None
    if "11" in text and ("am" in text or "morning" in text):
        slot = "Saturday 11:00 AM"
    elif "4" in text and ("pm" in text or "afternoon" in text):
        slot = "Saturday 4:00 PM"

    return {
        "booking_id": f"BK-{missed_call['id']}",
        "missed_call_id": missed_call["id"],
        "customer_name": missed_call["customer_name"],
        "customer_phone": missed_call["customer_phone"],
        "service": "Haircut",
        "slot": slot,
        "status": "confirmed" if slot else "needs_follow_up",
        "created_at": datetime.now(timezone.utc).isoformat()
    }

def save_booking(booking):
    bookings = []

    if BOOKINGS_FILE.exists():
        bookings = json.loads(BOOKINGS_FILE.read_text())

        bookings.append(booking)

        BOOKINGS_FILE.write_text(json.dumps(bookings, indent=2))
