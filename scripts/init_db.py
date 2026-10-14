import sys
from pathlib import Path

# Allow running from project root:
# python scripts/init_db.py
sys.path.append(str(Path(__file__).resolve().parent.parent))

from services.database import Base, engine
from services.models import MissedCall, Booking, CallLog


def init_db():
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully.")


if __name__ == "__main__":
    init_db()