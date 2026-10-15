from fastapi import FastAPI
from api.routes import router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SecondRing API",
    description="Outbound missed-call recovery voice agent for local service businesses.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://second-ring-dashboard.replit.app/"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def home():
    return{
        "message": "Secondring is live",
    }