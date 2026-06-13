from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Float, Date
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
    location_logs = relationship("LocationLog", back_populates="user")
    transfers = relationship("BatchTransfer", back_populates="user")
    temperature_inspections = relationship("TemperatureInspection", back_populates="user")
    temperature_alerts_handled = relationship("TemperatureAlert", foreign_keys="TemperatureAlert.handler_id", back_populates="handler")
    equipment_owned = relationship("Equipment", foreign_keys="Equipment.owner_id", back_populates="owner")
    calibration_plans_owned = relationship("CalibrationPlan", foreign_keys="CalibrationPlan.owner_id", back_populates="owner")
    calibration_records = relationship("CalibrationRecord", back_populates="user")
    calibration_logs = relationship("CalibrationLog", back_populates="user")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    capacity = Column(Integer, nullable=False)
    used = Column(Integer, default=0)
    frozen = Column(Boolean, default=False, nullable=False)
    monitoring_enabled = Column(Boolean, default=False, nullable=False)
    temp_min = Column(Float, nullable=True)
    temp_max = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    batches = relationship("Batch", back_populates="location")
    location_logs = relationship("LocationLog", back_populates="location")
    transfers_from = relationship("BatchTransfer", foreign_keys="BatchTransfer.from_location_id", back_populates="from_location")
    transfers_to = relationship("BatchTransfer", foreign_keys="BatchTransfer.to_location_id", back_populates="to_location")
    temperature_inspections = relationship("TemperatureInspection", back_populates="location")
    temperature_alerts = relationship("TemperatureAlert", back_populates="location")


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
    transfers = relationship("BatchTransfer", back_populates="batch")


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


class LocationLog(Base):
    __tablename__ = "location_logs"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    location = relationship("Location", back_populates="location_logs")
    user = relationship("User", back_populates="location_logs")


class BatchTransfer(Base):
    __tablename__ = "batch_transfers"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("Batch", back_populates="transfers")
    from_location = relationship("Location", foreign_keys=[from_location_id], back_populates="transfers_from")
    to_location = relationship("Location", foreign_keys=[to_location_id], back_populates="transfers_to")
    user = relationship("User", back_populates="transfers")


class TemperatureInspection(Base):
    __tablename__ = "temperature_inspections"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    temperature = Column(Float, nullable=False)
    inspection_date = Column(Date, nullable=False)
    remark = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    location = relationship("Location", back_populates="temperature_inspections")
    user = relationship("User", back_populates="temperature_inspections")


class TemperatureAlert(Base):
    __tablename__ = "temperature_alerts"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False)
    inspection_id = Column(Integer, ForeignKey("temperature_inspections.id"), nullable=False)
    temperature = Column(Float, nullable=False)
    temp_min = Column(Float, nullable=True)
    temp_max = Column(Float, nullable=True)
    status = Column(String(20), default="OPEN", nullable=False)
    handler_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reason = Column(Text, nullable=True)
    disposal = Column(Text, nullable=True)
    handled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    location = relationship("Location", back_populates="temperature_alerts")
    inspection = relationship("TemperatureInspection")
    handler = relationship("User", foreign_keys=[handler_id], back_populates="temperature_alerts_handled")


EQUIPMENT_STATUS_ACTIVE = "ACTIVE"
EQUIPMENT_STATUS_DISABLED = "DISABLED"

PLAN_STATUS_SCHEDULED = "SCHEDULED"
PLAN_STATUS_COMPLETED = "COMPLETED"
PLAN_STATUS_OVERDUE = "OVERDUE"

ACTION_EQUIPMENT_CREATE = "EQUIPMENT_CREATE"
ACTION_EQUIPMENT_UPDATE = "EQUIPMENT_UPDATE"
ACTION_EQUIPMENT_DISABLE = "EQUIPMENT_DISABLE"
ACTION_PLAN_SCHEDULE = "PLAN_SCHEDULE"
ACTION_PLAN_COMPLETE = "PLAN_COMPLETE"
ACTION_CYCLE_UPDATE = "CYCLE_UPDATE"
ACTION_OWNER_CHANGE = "OWNER_CHANGE"


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    manufacturer = Column(String(200), nullable=True)
    model = Column(String(200), nullable=True)
    serial_no = Column(String(100), nullable=True)
    location = Column(String(200), nullable=True)
    calibration_cycle_days = Column(Integer, nullable=False, default=90)
    status = Column(String(20), default=EQUIPMENT_STATUS_ACTIVE, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", foreign_keys=[owner_id], back_populates="equipment_owned")
    calibration_plans = relationship("CalibrationPlan", back_populates="equipment")
    calibration_records = relationship("CalibrationRecord", back_populates="equipment")
    calibration_logs = relationship("CalibrationLog", back_populates="equipment")


class CalibrationPlan(Base):
    __tablename__ = "calibration_plans"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    scheduled_date = Column(Date, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default=PLAN_STATUS_SCHEDULED, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="calibration_plans")
    owner = relationship("User", foreign_keys=[owner_id], back_populates="calibration_plans_owned")
    calibration_record = relationship("CalibrationRecord", back_populates="plan", uselist=False)
    calibration_logs = relationship("CalibrationLog", back_populates="plan")


class CalibrationRecord(Base):
    __tablename__ = "calibration_records"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("calibration_plans.id"), nullable=False, unique=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    completion_date = Column(Date, nullable=False)
    result = Column(String(50), nullable=False)
    certificate_no = Column(String(100), nullable=True)
    remark = Column(Text, nullable=True)
    next_calibration_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    plan = relationship("CalibrationPlan", back_populates="calibration_record")
    equipment = relationship("Equipment", back_populates="calibration_records")
    user = relationship("User", back_populates="calibration_records")


class CalibrationLog(Base):
    __tablename__ = "calibration_logs"

    id = Column(Integer, primary_key=True, index=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=True)
    plan_id = Column(Integer, ForeignKey("calibration_plans.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    remark = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="calibration_logs")
    plan = relationship("CalibrationPlan", back_populates="calibration_logs")
    user = relationship("User", back_populates="calibration_logs")
