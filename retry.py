import os
from dotenv import load_dotenv
from bimpeai import BimpeAI

load_dotenv()

API_KEY = os.environ["BIMPEAI_API_KEY"]

# Paste the newest agent ID from your BimpeAI Console here:
AGENT_ID = "cmuzv7s8a00gqqq89lgtshje9"

DESTINATION = "+2347030341119"

client = BimpeAI(api_key=API_KEY)

call = client.calls.make(
    AGENT_ID,
    {
        "destination": DESTINATION,
        "is_test_call": True
    }
)

print("Test call response:")
print(call)