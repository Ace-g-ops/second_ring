import json
import re
from pathlib import Path
from datetime import datetime, timezone

from config.settings import BOOKINGS_PATH
from services.missed_call_services import save_json, load_json

BOOKINGS_FILE = Path("booking.json")

AVAILABLE_SLOTS = {
    "saturday 11:00 am": ["11", "eleven", "11am", "11 am", "morning"],
    "saturday 4:00 pm": ["4", "four", "4pm", "4 pm", "afternoon"]
}


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
    full_text = " ".join(
        message["message"]
        for message in transcript
    ).lower()

    slot = None

    confirmation = re.search(
        r"confirmed for\s+(saturday\s+at\s+\d{1,2}(?::\d{2})?\s*[ap]m)",
        full_text
    )

    if confirmation:
        raw_slot = confirmation.group(1)

        if "4" in raw_slot or "four" in raw_slot:
            slot = "Saturday 4:00 PM"
        elif "11" in raw_slot or "eleven" in raw_slot:
            slot = "Saturday 11:00 AM"

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

## this function block help to struturally block ids from getting reduplicated
def save_booking(booking):
    bookings = get_bookings()

    already_saved = any(
        existing["missed_call_id"] == booking["missed_call_id"]
        for existing in bookings
    )

    if already_saved:
        return booking

    bookings.append(booking)
    BOOKINGS_FILE.write_text(json.dumps(bookings, indent=2))

    return booking
