from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
import enum
from sqlalchemy import String, Integer, DateTime, Date, Numeric, ForeignKey, func, CheckConstraint, UniqueConstraint, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class MovementType(str, enum.Enum):
    RECEIPT = "RECEIPT"
    SALE = "SALE"
    CUSTOMER_RETURN = "CUSTOMER_RETURN"
    DAMAGE = "DAMAGE"
    ADJUSTMENT = "ADJUSTMENT"

class InventoryBatch(Base):
    __tablename__ = "inventory_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    medicine_id: Mapped[int] = mapped_column(Integer, ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False, index=True)
    batch_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_purchase_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('medicine_id', 'batch_number', name='uix_medicine_batch'),
        CheckConstraint('quantity_on_hand >= 0', name='check_batch_qty_non_negative'),
    )

    medicine: Mapped["Medicine"] = relationship("Medicine", back_populates="batches")
    movements: Mapped[List["StockMovement"]] = relationship("StockMovement", back_populates="batch")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    medicine_id: Mapped[int] = mapped_column(Integer, ForeignKey("medicines.id", ondelete="RESTRICT"), nullable=False, index=True)
    batch_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("inventory_batches.id", ondelete="RESTRICT"), nullable=True, index=True)
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType, name="movement_type_enum"), nullable=False, index=True)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint('quantity_change != 0', name='check_movement_qty_non_zero'),
    )

    medicine: Mapped["Medicine"] = relationship("Medicine", back_populates="movements")
    batch: Mapped[Optional["InventoryBatch"]] = relationship("InventoryBatch", back_populates="movements")
