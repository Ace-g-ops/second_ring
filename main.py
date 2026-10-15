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
        "https://second-ring-dashboard.replit.app/",
        "https://8071646e-25b5-45c5-9ba9-dd4c1917bfea-00-20ejidf7yy43z.reed.replit.dev",
        "http://127.0.0.1"
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