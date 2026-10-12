from fastapi import APIRouter, HTTPException
from datetime import datetime

from services.bimpe_service import(
    place_callback_call,
    filter_conversation_logs,
    retrieve_call_details
) 
from services.booking_service import get_bookings
from services.missed_call_services import (
    get_missed_calls,
    get_pending_missed_call,
    mark_callback_started,
    log_call_result,
    attach_bimpe_call_id
)

router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok"}

@router.get("/api/missed_calls")
def get_missed_calls_():
    return get_missed_calls()

@router.get("/api/bookings")
def get_bookings_():
    return get_bookings()

@router.post("/api/callback/test")
def trigger_test_callback():
    missed_call = get_pending_missed_call()

    if not missed_call:
        raise HTTPException(
            status_code=404, 
            detail="No pending missed calls found."
        )

    mark_callback_started(missed_call["id"])

    call_response = place_callback_call(
        customer_phone=missed_call["customer_phone"],
        is_test_call=True,
    )

    bimpe_call_id = getattr(call_response, "call_id", None)

    if bimpe_call_id:
        attach_bimpe_call_id(
            missed_call_id=missed_call["id"],
            bimpe_call_id=bimpe_call_id
        )

    log_call_result(
        missed_call_id=missed_call["id"],
        outcome="test_call_initiated",
        details={
            "response": str(call_response)
        }
    )

    return {
        "message": "Test callback initiated.",
        "missed_call": missed_call,
        "bimpeai_response": str(call_response)
    }

##this route get the each calls made alongside their ids
@router.get("/api/callback/{missed_call_id}/result")
def check_callback_result(missed_call_id: str):
    calls = get_missed_calls()

    missed_call = next(
        (call for call in calls if call["id"] == missed_call_id),
        None
    )

    if not missed_call:
        raise HTTPException(
            status_code=404,
            detail="Missed call not found."
        )

    bimpe_call_id = missed_call.get("bimpe_call_id")

    if not bimpe_call_id:
        raise HTTPException(
            status_code=400,
            detail="This missed call has no BimpeAI call ID yet."
        )

    call_details = retrieve_call_details(bimpe_call_id)
    filtered_logs = filter_conversation_logs(call_details)

    transcript = [
        {
            "role": message.role,
            "message": message.message,
            "created_at": message.created_at
        }
        for message in filtered_logs
    ]

    return {
        "missed_call": missed_call,
        "call_status": getattr(call_details, "status", None),
        "answered_at": getattr(call_details, "answered_at", None),
        "error_reason": getattr(call_details, "error_reason", None),
        "started_at": getattr(call_details, "started_at", None),
        "ended_at": getattr(call_details, "ended_at", None),
        "transcript": transcript
    }
