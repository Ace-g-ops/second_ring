from bimpeai import BimpeAI
from datetime import datetime

from config.settings import(
    BIMPEAI_API_KEY,
    BIMPE_AGENT_ID,
)


client = BimpeAI(api_key=BIMPEAI_API_KEY)

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


def review_call_history(history_client=None, agent_id=None):
    """Read ALL agent calls. Missing/inconsistent pagination fails closed.

    Do not use Page.__iter__: it treats absent metadata as end-of-history.
    No recipient, status or test-call filters: those can hide another attempt.
    """
    history_client = history_client or client
    agent_id = agent_id or BIMPE_AGENT_ID
    calls = []
    seen_ids = set()
    expected_total = expected_pages = None
    for number in range(1, 10001):
        page = history_client.calls.list(agent_id, page=number, limit=100)
        meta = page.meta
        if meta is None:
            raise ValueError("Provider history has no pagination metadata.")
        if expected_total is None:
            expected_total, expected_pages = meta.total_count, meta.page_count
        if (
            meta.current_page != number
            or meta.total_count != expected_total
            or meta.page_count != expected_pages
            or meta.limit <= 0
            or expected_total < 0
            or expected_pages < 0
            or meta.has_next_page != (number < expected_pages)
            or meta.has_previous_page != (number > 1)
            or number > max(1, expected_pages)
            or len(page.data) > meta.limit
            or (expected_total > 0 and expected_pages != (expected_total + meta.limit - 1) // meta.limit)
            or (expected_total == 0 and expected_pages not in (0, 1))
            or (meta.has_next_page and len(page.data) != meta.limit)
        ):
            raise ValueError("Provider history pagination is inconsistent.")
        for call in page.data:
            if not call.id or call.id in seen_ids:
                raise ValueError("Provider history contains missing/duplicate IDs.")
            seen_ids.add(call.id)
            calls.append(call)
        if not meta.has_next_page:
            if len(calls) != expected_total:
                raise ValueError("Provider history is incomplete.")
            return calls
        if not page.data:
            raise ValueError("Provider history has an empty intermediate page.")
    raise ValueError("Provider history exceeded the safety page limit.")


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




