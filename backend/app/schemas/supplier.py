from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class SupplierBase(BaseModel):
    name: str = Field(..., max_length=255)
    contact_person: Optional[str] = Field(None, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    default_lead_time_days: int = Field(0, ge=0)

class SupplierCreate(SupplierBase):
    pass

class SupplierResponse(SupplierBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SupplierList(BaseModel):
    items: list[SupplierResponse]
    total: int
    skip: int
    limit: int
