from pydantic import BaseModel, ConfigDict, Field
from datetime import date, datetime
from typing import Optional, List, Any
from decimal import Decimal
from app.models.invoice import InvoiceProcessingStatus

# Extraction schemas (used by the AI provider mock)
class ExtractedInvoiceLineItem(BaseModel):
    medicine_name: str
    code: Optional[str] = None
    batch_number: Optional[str] = None
    quantity: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    manufacturing_date: Optional[date] = None
    expiry_date: Optional[date] = None

class ExtractedInvoiceData(BaseModel):
    supplier_name: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    currency: Optional[str] = None
    subtotal: Optional[Decimal] = None
    total: Optional[Decimal] = None
    line_items: List[ExtractedInvoiceLineItem] = []
    # Traceability / audit fields (Phase 4)
    confidence_score: Optional[float] = None        # 0.0–1.0; None = not reported
    extraction_provider: Optional[str] = None       # "mock" | "gemini"
    raw_extraction_result: Optional[str] = None     # raw JSON string from the model


# API schemas
class InvoiceUploadResponse(BaseModel):
    id: int
    status: InvoiceProcessingStatus
    message: str

class InvoiceLineItemResponse(BaseModel):
    id: int
    medicine_id: Optional[int] = None
    extracted_medicine_name: Optional[str] = None
    extracted_code: Optional[str] = None
    batch_number: Optional[str] = None
    quantity: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    manufacturing_date: Optional[date] = None
    expiry_date: Optional[date] = None
    has_error: bool
    validation_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class InvoiceResponse(BaseModel):
    id: int
    supplier_id: Optional[int] = None
    extracted_supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    currency: Optional[str] = None
    subtotal: Optional[Decimal] = None
    total: Optional[Decimal] = None
    status: InvoiceProcessingStatus
    error_message: Optional[str] = None
    extraction_provider: Optional[str] = None
    extraction_confidence: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime
    line_items: List[InvoiceLineItemResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class InvoiceLineItemUpdate(BaseModel):
    medicine_id: Optional[int] = None
    batch_number: Optional[str] = None
    quantity: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    manufacturing_date: Optional[date] = None
    expiry_date: Optional[date] = None
