"""Keep provider call outcomes independent from appointment extraction."""


def callback_status_from_details(call_details):
    raw_status = getattr(call_details, "status", None)
    status = str(getattr(raw_status, "value", raw_status) or "")
    status = status.strip().lower().replace("-", "_").replace(" ", "_")
    answered_at = getattr(call_details, "answered_at", None)
    ended_at = getattr(call_details, "ended_at", None)
    error_reason = getattr(call_details, "error_reason", None)

    failed = {
        "failed", "error", "busy", "no_answer", "unanswered",
        "cancelled", "canceled", "rejected",
    }
    completed = {"completed", "callback_completed", "finished"}
    active = {
        "ringing", "queued", "initiated", "dialing", "in_progress",
        "callback_in_progress", "answered", "connected", "ongoing", "started",
    }

    if status in failed or (error_reason and (ended_at or status == "ended")):
        return "failed"
    if status in completed:
        return "callback_completed"
    if status == "ended" or ended_at:
        return "callback_completed" if answered_at else "failed"
    if status in active:
        return "callback_in_progress"
    return None
