from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class MedicineBase(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    base_unit: str = Field(..., max_length=50)

class MedicineCreate(MedicineBase):
    pass

class MedicineResponse(MedicineBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class MedicineList(BaseModel):
    items: list[MedicineResponse]
    total: int
    skip: int
    limit: int
