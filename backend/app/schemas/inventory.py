from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field
from decimal import Decimal
from app.models.inventory import MovementType

class InventoryBatchResponse(BaseModel):
    id: int
    medicine_id: int
    batch_number: str
    expiry_date: Optional[date]
    quantity_on_hand: int
    unit_purchase_price: Decimal
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class StockMovementCreate(BaseModel):
    medicine_id: int
    batch_id: Optional[int] = None
    movement_type: MovementType
    quantity_change: int = Field(..., description="Must not be 0. Positive for receipts/returns, negative for sales/damage.")
    unit_cost: Optional[Decimal] = None
    reference: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=1000)

class StockMovementResponse(BaseModel):
    id: int
    medicine_id: int
    batch_id: Optional[int]
    movement_type: MovementType
    quantity_change: int
    unit_cost: Optional[Decimal]
    reference: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

class StockMovementList(BaseModel):
    items: list[StockMovementResponse]
    total: int
    skip: int
    limit: int

class InventoryBatchList(BaseModel):
    items: list[InventoryBatchResponse]
    total: int
    skip: int
    limit: int

class InventorySummaryResponse(BaseModel):
    total_active_medicines: int
    total_batches: int
    total_units_in_stock: int
    expired_batches: int
    expiring_soon_batches: int
