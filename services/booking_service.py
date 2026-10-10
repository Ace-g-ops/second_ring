import json
from datetime import datetime, timezone

from config.settings import BOOKINGS_PATH
from services.missed_call_services import save_json, load_json


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