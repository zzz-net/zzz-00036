from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    audit_logs = relationship("AuditLog", back_populates="user")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=False)
    used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    batches = relationship("Batch", back_populates="location")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_no = Column(String(100), unique=True, index=True, nullable=False)
    reagent_name = Column(String(200), nullable=False)
    total_quantity = Column(Integer, nullable=False)
    available_quantity = Column(Integer, nullable=False)
    expiry_date = Column(String(20), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    status = Column(String(20), default="REGISTERED", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    location = relationship("Location", back_populates="batches")
    audit_logs = relationship("AuditLog", back_populates="batch")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    quantity = Column(Integer, default=0)
    from_status = Column(String(20))
    to_status = Column(String(20))
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("Batch", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")
