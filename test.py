import os
from bimpeai import BimpeAI
from dotenv import load_dotenv

load_dotenv()

client = BimpeAI(api_key=os.environ["BIMPEAI_API_KEY"])

##making a small workflow
workflow=client.workflows.create(
    name="Second Ring",

    system_prompt="""
    You are SecondRing, a callback assistant for Sharp Cuts Salon.

    Start by saying:
    'Hello, this is SecondRing calling from Sharp Cuts Salon.
    We missed your call earlier. How can I help you?'

    Keep responses short and natural for a phone call.
    Do not invent services, prices, or available times.
    """

)

print("Workflow Created:", workflow.id)

##create an agent for a bound call

agent=client.agents.create(
    name="SecondRing",
    description="Callback assistant for Sharp Cuts Salon",
    workflow_id=workflow.id
)

print("Agent Created:", agent.id)

##placing a cal test outbound
call=client.calls.make(
    agent.id,
    {
        "destination":"+2347030341119",
        "is_test_call":True
    }
)

print("Test Call Placed:", call)

