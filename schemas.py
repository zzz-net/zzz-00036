from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from typing import Optional, List


class LocationBase(BaseModel):
    code: str
    name: str
    capacity: int = Field(gt=0)


class LocationCreate(LocationBase):
    pass


class LocationResponse(LocationBase):
    id: int
    used: int
    frozen: bool
    monitoring_enabled: bool = False
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class UserBase(BaseModel):
    username: str
    role: str


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class BatchBase(BaseModel):
    batch_no: str
    reagent_name: str
    total_quantity: int = Field(gt=0)
    expiry_date: str
    location_code: str


class BatchCreate(BatchBase):
    username: str
    remark: Optional[str] = None


class BatchResponse(BaseModel):
    id: int
    batch_no: str
    reagent_name: str
    total_quantity: int
    available_quantity: int
    expiry_date: str
    location_id: int
    location_name: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AuditLogResponse(BaseModel):
    id: int
    batch_id: int
    batch_no: Optional[str] = None
    user_id: int
    username: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    quantity: int
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    remark: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ActionRequest(BaseModel):
    username: str
    quantity: Optional[int] = Field(default=None, gt=0)
    remark: Optional[str] = None


class BatchListResponse(BaseModel):
    items: List[BatchResponse]
    total: int


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int


class ErrorResponse(BaseModel):
    detail: str


class LocationActionRequest(BaseModel):
    username: str
    remark: Optional[str] = None


class LocationLogResponse(BaseModel):
    id: int
    location_id: int
    location_code: Optional[str] = None
    user_id: int
    username: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    remark: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LocationLogListResponse(BaseModel):
    items: List[LocationLogResponse]
    total: int


class BatchTransferCreate(BaseModel):
    username: str
    to_location_code: str
    remark: Optional[str] = None


class BatchTransferResponse(BaseModel):
    id: int
    batch_id: int
    batch_no: str
    from_location_id: int
    from_location_code: str
    to_location_id: int
    to_location_code: str
    user_id: int
    username: str
    user_role: str
    remark: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BatchTransferListResponse(BaseModel):
    items: List[BatchTransferResponse]
    total: int


class LocationTempConfigRequest(BaseModel):
    username: str
    monitoring_enabled: bool
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None

    @field_validator("temp_min", "temp_max", mode="before")
    @classmethod
    def validate_temp_not_nan(cls, v):
        if v is not None:
            try:
                v = float(v)
            except (ValueError, TypeError):
                raise ValueError("温度值必须是有效数字")
            if v != v:
                raise ValueError("温度值不能为 NaN")
        return v


class TemperatureInspectionCreate(BaseModel):
    username: str
    temperature: float
    inspection_date: str
    remark: Optional[str] = None

    @field_validator("temperature", mode="before")
    @classmethod
    def validate_temperature(cls, v):
        try:
            v = float(v)
        except (ValueError, TypeError):
            raise ValueError("温度值必须是有效数字")
        if v != v:
            raise ValueError("温度值不能为 NaN")
        if v < -273.15:
            raise ValueError("温度值不能低于绝对零度 (-273.15°C)")
        return v

    @field_validator("inspection_date", mode="before")
    @classmethod
    def validate_inspection_date(cls, v):
        try:
            date.fromisoformat(v)
        except (ValueError, TypeError):
            raise ValueError("巡检日期格式无效，需为 YYYY-MM-DD")
        return v


class TemperatureInspectionResponse(BaseModel):
    id: int
    location_id: int
    location_code: Optional[str] = None
    user_id: int
    username: Optional[str] = None
    user_role: Optional[str] = None
    temperature: float
    inspection_date: str
    remark: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TemperatureAlertResponse(BaseModel):
    id: int
    location_id: int
    location_code: Optional[str] = None
    inspection_id: int
    temperature: float
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    status: str
    handler_id: Optional[int] = None
    handler_name: Optional[str] = None
    reason: Optional[str] = None
    disposal: Optional[str] = None
    handled_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class TemperatureAlertHandleRequest(BaseModel):
    username: str
    reason: str = Field(min_length=1)
    disposal: str = Field(min_length=1)


class EquipmentBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=50)
    manufacturer: Optional[str] = Field(default=None, max_length=200)
    model: Optional[str] = Field(default=None, max_length=200)
    serial_no: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    calibration_cycle_days: int = Field(gt=0, default=90)
    owner_username: Optional[str] = None


class EquipmentCreate(EquipmentBase):
    username: str


class EquipmentUpdate(BaseModel):
    username: str
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    category: Optional[str] = Field(default=None, min_length=1, max_length=50)
    manufacturer: Optional[str] = Field(default=None, max_length=200)
    model: Optional[str] = Field(default=None, max_length=200)
    serial_no: Optional[str] = Field(default=None, max_length=100)
    location: Optional[str] = Field(default=None, max_length=200)
    calibration_cycle_days: Optional[int] = Field(default=None, gt=0)
    owner_username: Optional[str] = None


class EquipmentDisableRequest(BaseModel):
    username: str
    remark: Optional[str] = None


class EquipmentResponse(BaseModel):
    id: int
    code: str
    name: str
    category: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_no: Optional[str] = None
    location: Optional[str] = None
    calibration_cycle_days: int
    status: str
    owner_id: Optional[int] = None
    owner_username: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EquipmentListResponse(BaseModel):
    items: List[EquipmentResponse]
    total: int


class CalibrationPlanCreate(BaseModel):
    username: str
    equipment_code: str
    scheduled_date: str
    owner_username: Optional[str] = None

    @field_validator("scheduled_date", mode="before")
    @classmethod
    def validate_scheduled_date(cls, v):
        try:
            date.fromisoformat(v)
        except (ValueError, TypeError):
            raise ValueError("计划日期格式无效，需为 YYYY-MM-DD")
        return v


class CalibrationPlanScheduleUpdate(BaseModel):
    username: str
    scheduled_date: Optional[str] = None
    owner_username: Optional[str] = None

    @field_validator("scheduled_date", mode="before")
    @classmethod
    def validate_scheduled_date(cls, v):
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except (ValueError, TypeError):
            raise ValueError("计划日期格式无效，需为 YYYY-MM-DD")
        return v


class CalibrationPlanResponse(BaseModel):
    id: int
    equipment_id: int
    equipment_code: Optional[str] = None
    equipment_name: Optional[str] = None
    scheduled_date: str
    owner_id: Optional[int] = None
    owner_username: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CalibrationPlanListResponse(BaseModel):
    items: List[CalibrationPlanResponse]
    total: int


class CalibrationRecordCreate(BaseModel):
    username: str
    completion_date: str
    result: str = Field(min_length=1, max_length=50)
    certificate_no: Optional[str] = Field(default=None, max_length=100)
    remark: Optional[str] = None
    next_calibration_date: Optional[str] = None

    @field_validator("completion_date", "next_calibration_date", mode="before")
    @classmethod
    def validate_date_fields(cls, v):
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except (ValueError, TypeError):
            raise ValueError("日期格式无效，需为 YYYY-MM-DD")
        return v


class CalibrationRecordResponse(BaseModel):
    id: int
    plan_id: int
    equipment_id: int
    equipment_code: Optional[str] = None
    equipment_name: Optional[str] = None
    user_id: int
    username: Optional[str] = None
    user_role: Optional[str] = None
    completion_date: str
    result: str
    certificate_no: Optional[str] = None
    remark: Optional[str] = None
    next_calibration_date: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CalibrationRecordListResponse(BaseModel):
    items: List[CalibrationRecordResponse]
    total: int


class CalibrationLogResponse(BaseModel):
    id: int
    equipment_id: Optional[int] = None
    equipment_code: Optional[str] = None
    plan_id: Optional[int] = None
    user_id: int
    username: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    remark: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CalibrationLogListResponse(BaseModel):
    items: List[CalibrationLogResponse]
    total: int
