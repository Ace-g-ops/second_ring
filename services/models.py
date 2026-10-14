from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from services.database import Base


class MissedCall(Base):
    __tablename__ = "missed_calls"

    id = Column(String, primary_key=True)
    business_id = Column(String, nullable=False)
    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=False)
    missed_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False, default="pending_callback")
    bimpe_call_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True)
    missed_call_id = Column(
        String,
        ForeignKey("missed_calls.id"),
        unique=True,
        nullable=False
    )
    customer_name = Column(String, nullable=False)
    customer_phone = Column(String, nullable=False)
    service = Column(String, nullable=False)
    slot = Column(String, nullable=True)
    status = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(String, primary_key=True)
    missed_call_id = Column(
        String,
        ForeignKey("missed_calls.id"),
        nullable=False
    )
    bimpe_call_id = Column(String, nullable=True)
    call_status = Column(String, nullable=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    error_reason = Column(Text, nullable=True)
    transcript = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)