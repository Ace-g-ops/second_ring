from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from services.database import get_db

from services.missed_call_services import (
    get_missed_calls,
    get_missed_call_by_id,
    get_pending_missed_call,
    mark_callback_started,
    mark_callback_failed,
    synchronize_callback_status,
    attach_bimpe_call_id,
    create_missed_call,
)

from services.booking_service import (
    get_bookings,
    extract_booking,
    save_booking
)

from services.bimpe_service import(
    place_callback_call,
    retrieve_call_details,
    filter_conversation_logs
)


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/missed_calls")
def get_missed_calls_(db: Session = Depends(get_db)):
    missed_calls = get_missed_calls(db)

    return [
        {
            "id": call.id,
            "business_id": call.business_id,
            "customer_name": call.customer_name,
            "customer_phone": call.customer_phone,
            "missed_at": call.missed_at,
            "status": call.status,
            "bimpe_call_id": call.bimpe_call_id
        }
        for call in missed_calls
    ]


@router.get("/api/bookings")
def get_bookings_(db: Session = Depends(get_db)):
    bookings = get_bookings(db)

    return [
        {
            "id": booking.id,
            "missed_call_id": booking.missed_call_id,
            "customer_name": booking.customer_name,
            "customer_phone": booking.customer_phone,
            "service": booking.service,
            "slot": booking.slot,
            "status": booking.status,
            "created_at": booking.created_at
        }
        for booking in bookings
    ]


@router.post("/api/callback/test")
def trigger_test_callback(db: Session = Depends(get_db)):
    missed_call = get_pending_missed_call(db)

    if not missed_call:
        raise HTTPException(
            status_code=404,
            detail="No pending missed calls found."
        )

    bimpe_call_id = _start_callback(db, missed_call)

    return {
        "message": "Test callback initiated.",
        "missed_call_id": missed_call.id,
        "bimpe_call_id": bimpe_call_id
    }
@router.get("/api/callback/{missed_call_id}/result")
def check_callback_result(
    missed_call_id: str,
    db: Session = Depends(get_db)
):
    missed_call = get_missed_call_by_id(db, missed_call_id)

    if not missed_call:
        raise HTTPException(
            status_code=404,
            detail="Missed call not found."
        )

    if not missed_call.bimpe_call_id:
        raise HTTPException(
            status_code=400,
            detail="This missed call has no BimpeAI call ID yet."
        )

    bimpe_call_id = missed_call.bimpe_call_id
    call_details = retrieve_call_details(bimpe_call_id)
    # Persist call lifecycle independently of whether an appointment was booked.
    missed_call = synchronize_callback_status(
        db, missed_call.id, bimpe_call_id, call_details
    )
    if not missed_call or missed_call.bimpe_call_id != bimpe_call_id:
        raise HTTPException(
            status_code=409,
            detail="A newer callback has started. Refresh to retrieve its result.",
        )
    filtered_logs = filter_conversation_logs(call_details)

    transcript = [
        {
            "role": message.role,
            "message": message.message,
            "created_at": message.created_at
        }
        for message in filtered_logs
    ]

    booking_data = extract_booking(transcript, missed_call)

    booking = None

    if (
        missed_call.status == "callback_completed"
        and booking_data["status"] == "confirmed"
    ):
        booking = save_booking(db, booking_data)

    return {
        "missed_call": {
            "id": missed_call.id,
            "business_id": missed_call.business_id,
            "customer_name": missed_call.customer_name,
            "customer_phone": missed_call.customer_phone,
            "missed_at": missed_call.missed_at,
            "status": missed_call.status,
            "bimpe_call_id": missed_call.bimpe_call_id
        },
        "call_status": getattr(call_details, "status", None),
        "answered_at": getattr(call_details, "answered_at", None),
        "error_reason": getattr(call_details, "error_reason", None),
        "started_at": getattr(call_details, "started_at", None),
        "ended_at": getattr(call_details, "ended_at", None),
        "transcript": transcript,
        "booking": {
            "id": booking.id,
            "missed_call_id": booking.missed_call_id,
            "customer_name": booking.customer_name,
            "customer_phone": booking.customer_phone,
            "service": booking.service,
            "slot": booking.slot,
            "status": booking.status,
            "created_at": booking.created_at
        } if booking else booking_data
    }

##new endxpoints
@router.post("/api/missed_calls/test")
def create_test_missed_call(db: Session = Depends(get_db)):
    missed_call_id = f"MC-{int(datetime.now(timezone.utc).timestamp())}"

    missed_call = create_missed_call(
        db=db,
        missed_call_id=missed_call_id,
        business_id="sharp-cuts",
        customer_name="Nuel",
        customer_phone="+2347030341119",
        missed_at=datetime.now(timezone.utc)
    )

    return {
        "message": "Test missed call created.",
        "missed_call": {
            "id": missed_call.id,
            "customer_name": missed_call.customer_name,
            "customer_phone": missed_call.customer_phone,
            "status": missed_call.status
        }
    }

def _start_callback(db: Session, missed_call):
    if missed_call.status == "callback_in_progress":
        raise HTTPException(
            status_code=400,
            detail="Callback is already in progress."
        )

    if missed_call.status == "callback_completed":
        raise HTTPException(
            status_code=400,
            detail="Callback has already been completed."
        )

    if not mark_callback_started(db, missed_call.id):
        raise HTTPException(
            status_code=409,
            detail="This callback is no longer available to start. Refresh the call list.",
        )

    try:
        call_response = place_callback_call(
            customer_phone=missed_call.customer_phone,
            is_test_call=True
        )
    except Exception as exc:
        mark_callback_failed(db, missed_call.id)
        raise HTTPException(
            status_code=502,
            detail="BimpeAI could not start the callback. Please try again.",
        ) from exc

    bimpe_call_id = getattr(call_response, "call_id", None)

    if not bimpe_call_id:
        mark_callback_failed(db, missed_call.id)
        raise HTTPException(
            status_code=502,
            detail="BimpeAI did not return a call ID."
        )

    attach_bimpe_call_id(
        db=db,
        missed_call_id=missed_call.id,
        bimpe_call_id=bimpe_call_id
    )

    return bimpe_call_id


@router.post("/api/callback/{missed_call_id}/trigger")
def trigger_callback(
    missed_call_id: str,
    db: Session = Depends(get_db)
):
    missed_call = get_missed_call_by_id(db, missed_call_id)

    if not missed_call:
        raise HTTPException(status_code=404, detail="Missed call not found.")

    bimpe_call_id = _start_callback(db, missed_call)

    return {
        "message": "Callback initiated.",
        "missed_call_id": missed_call.id,
        "bimpe_call_id": bimpe_call_id
    }
