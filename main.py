from fastapi import FastAPI
from api.routes import router

app = FastAPI(
    title="SecondRing API",
    description="Outbound missed-call recovery voice agent for local service businesses.",
    version="1.0.0",
)

app.include_router(router)

@app.get("/")
def home():
    return{
        "message": "Secondring is live",
    }