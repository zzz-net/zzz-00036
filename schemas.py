from pydantic import BaseModel, Field
from datetime import datetime
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
