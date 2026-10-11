import json
from datetime import datetime, timezone

from config.settings import(
    MISSED_CALLS_PATH,
    CALL_RESULTS_PATH,
)

##this function will load the missed calls from a json file 
def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)

##this function will save the missed calls to a json file
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2) 

def get_missed_calls():
    return load_json(MISSED_CALLS_PATH)

def get_pending_missed_call():
    calls = get_missed_calls()

    for call in calls:
        if call["status"] == "pending_callback":
            return call

    return None

##this function will mark a missed call as having a callback started
def mark_callback_started(missed_call_id):
    calls = get_missed_calls()

    for call in calls:
        if call["id"] == missed_call_id:
            call["status"] = "callback_in_progress"
            save_json(MISSED_CALLS_PATH, calls)
            return call
    return None

def log_call_result(missed_call_id, outcome, details=None):
    results = load_json(CALL_RESULTS_PATH)

    result = {
        "missed_call_id": missed_call_id,
        "outcome": outcome,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    results.append(result)
    save_json(CALL_RESULTS_PATH, results)

    return result

def attach_bimpe_call_id(missed_call_id, bimpe_call_id):
    calls = get_missed_calls()

    for call in calls:
        if call["id"] == missed_call_id:
            call("bimpe_call_id") == bimpe_call_id
            save_json(MISSED_CALLS_PATH, calls)
            return call
    return None


