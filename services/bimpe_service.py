from bimpeai import BimpeAI
from datetime import datetime

from config.settings import(
    BIMPEAI_API_KEY,
    BIMPE_AGENT_ID,
)


client = BIMPEAI(api_key=BIMPEAI_API_KEY)

def place_callback_call(customer_phone: str, is_test_call: bool = True):
    response = client.calls.make(
        BIMPE_AGENT_ID,
        {
            "destination": customer_phone,
            "is_test_call": is_test_call,
        }
    )

    return response

def retrieve_call_details(bimpe_call_id: str):
    return client.calls.retrieve(
        BIMPE_AGENT_ID,
        bimpe_call_id
    )

def filter_conversation_logs(call_details):
    logs = getattr(call_details, "conversation_logs", []) or []

    started_at = getattr(call_details, "started_at", None)
    ended_at = getattr(call_details, "ended_at", None)

    if not started_at or not ended_at:
        return []

    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))

    filtered = []

    for message in logs:
        created_at = getattr(message, "created_at", None)

        if not created_at:
            continue

        message_time = datetime.fromisoformat(
            created_at.replace("Z", "+00:00")
        )

        if start <= message_time <= end:
            filtered.append(message)

    return filtered




