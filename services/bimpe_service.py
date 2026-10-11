from bimpeai import BimpeAI

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




