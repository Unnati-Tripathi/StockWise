from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
import enum

from sqlalchemy import String, Integer, DateTime, Date, Numeric, ForeignKey, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class InvoiceProcessingStatus(str, enum.Enum):
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    POSTED = "POSTED"
    FAILED = "FAILED"

class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True)
    extracted_supplier_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    invoice_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    
    status: Mapped[InvoiceProcessingStatus] = mapped_column(Enum(InvoiceProcessingStatus, name="invoice_status_enum"), default=InvoiceProcessingStatus.UPLOADED, nullable=False, index=True)
    
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    supplier: Mapped[Optional["Supplier"]] = relationship("Supplier")
    line_items: Mapped[List["InvoiceLineItem"]] = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    
    medicine_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("medicines.id", ondelete="SET NULL"), nullable=True, index=True)
    extracted_medicine_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extracted_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    batch_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    quantity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    
    manufacturing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    
    has_error: Mapped[bool] = mapped_column(default=False, nullable=False)
    validation_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")
    medicine: Mapped[Optional["Medicine"]] = relationship("Medicine")
