from datetime import datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, Integer, DateTime, Numeric, ForeignKey, func, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class SupplierMedicine(Base):
    __tablename__ = "supplier_medicines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    supplier_id: Mapped[int] = mapped_column(Integer, ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    medicine_id: Mapped[int] = mapped_column(Integer, ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False, index=True)
    supplier_product_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    unit_purchase_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    minimum_order_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('supplier_id', 'medicine_id', name='uix_supplier_medicine'),
        CheckConstraint('minimum_order_quantity >= 0', name='check_moq_non_negative'),
        CheckConstraint('lead_time_days >= 0', name='check_lead_time_non_negative'),
    )

    supplier: Mapped["Supplier"] = relationship("Supplier", back_populates="medicines")
    medicine: Mapped["Medicine"] = relationship("Medicine", back_populates="suppliers")
