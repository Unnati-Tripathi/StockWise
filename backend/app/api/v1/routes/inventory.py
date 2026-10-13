from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, exc
from typing import Optional
from datetime import datetime, date, timedelta
from app.db.session import get_db
from app.models.inventory import InventoryBatch, StockMovement, MovementType
from app.models.medicine import Medicine
from app.schemas.inventory import (
    StockMovementCreate, StockMovementResponse, StockMovementList,
    InventoryBatchResponse, InventoryBatchList, InventorySummaryResponse
)

router = APIRouter()

@router.get("/batches", response_model=InventoryBatchList)
def list_batches(
    medicine_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    query = select(InventoryBatch)
    if medicine_id is not None:
        query = query.where(InventoryBatch.medicine_id == medicine_id)
        
    total = db.scalar(select(func.count(InventoryBatch.id)).select_from(query.subquery())) or 0
    batches = db.execute(query.offset(skip).limit(limit)).scalars().all()
    return {"items": batches, "total": total, "skip": skip, "limit": limit}

@router.get("/summary", response_model=InventorySummaryResponse)
def get_inventory_summary(
    db: Session = Depends(get_db)
):
    total_active_medicines = db.scalar(select(func.count(Medicine.id)).where(Medicine.is_active == True)) or 0
    total_batches = db.scalar(select(func.count(InventoryBatch.id))) or 0
    total_units_in_stock = db.scalar(select(func.sum(InventoryBatch.quantity_on_hand))) or 0
    
    today = date.today()
    thirty_days_from_now = today + timedelta(days=30)
    
    expired_batches = db.scalar(select(func.count(InventoryBatch.id)).where(InventoryBatch.expiry_date < today)) or 0
    expiring_soon_batches = db.scalar(select(func.count(InventoryBatch.id)).where(
        InventoryBatch.expiry_date >= today,
        InventoryBatch.expiry_date <= thirty_days_from_now
    )) or 0
    
    return {
        "total_active_medicines": total_active_medicines,
        "total_batches": total_batches,
        "total_units_in_stock": total_units_in_stock,
        "expired_batches": expired_batches,
        "expiring_soon_batches": expiring_soon_batches
    }

@router.get("/movements", response_model=StockMovementList)
def list_movements(
    medicine_id: Optional[int] = Query(None),
    movement_type: Optional[MovementType] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    query = select(StockMovement)
    if medicine_id is not None:
        query = query.where(StockMovement.medicine_id == medicine_id)
    if movement_type is not None:
        query = query.where(StockMovement.movement_type == movement_type)
        
    total = db.scalar(select(func.count(StockMovement.id)).select_from(query.subquery())) or 0
    movements = db.execute(query.order_by(StockMovement.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    return {"items": movements, "total": total, "skip": skip, "limit": limit}

@router.post("/movements", response_model=StockMovementResponse, status_code=status.HTTP_201_CREATED)
def create_stock_movement(
    movement_in: StockMovementCreate,
    db: Session = Depends(get_db)
):
    if movement_in.quantity_change == 0:
        raise HTTPException(status_code=422, detail="Quantity change must not be zero")
        
    # Validation logic based on movement type signs
    if movement_in.movement_type in (MovementType.RECEIPT, MovementType.CUSTOMER_RETURN):
        if movement_in.quantity_change < 0:
            raise HTTPException(status_code=422, detail="Receipts and returns must have a positive quantity change")
    elif movement_in.movement_type in (MovementType.SALE, MovementType.DAMAGE):
        if movement_in.quantity_change > 0:
            raise HTTPException(status_code=422, detail="Sales and damages must have a negative quantity change")

    try:
        # Verify medicine exists
        medicine = db.get(Medicine, movement_in.medicine_id)
        if not medicine:
            raise HTTPException(status_code=404, detail="Medicine not found")

        if movement_in.batch_id:
            # Lock the row for update to prevent concurrent overselling
            batch = db.execute(
                select(InventoryBatch)
                .where(InventoryBatch.id == movement_in.batch_id)
                .with_for_update()
            ).scalars().first()
            
            if not batch:
                raise HTTPException(status_code=404, detail="Batch not found")
            if batch.medicine_id != movement_in.medicine_id:
                raise HTTPException(status_code=422, detail="Batch does not belong to the specified medicine")

            if batch.quantity_on_hand + movement_in.quantity_change < 0:
                raise HTTPException(status_code=409, detail="Insufficient stock in the specified batch")

            # Apply change to batch
            batch.quantity_on_hand += movement_in.quantity_change
        else:
            # Requires batch-level stock change for all but adjustments without batches (if allowed)
            # Depending on business rules, we require batch_id for everything but adjustments.
            if movement_in.movement_type != MovementType.ADJUSTMENT:
                raise HTTPException(status_code=422, detail="Batch ID is required for this movement type")

        new_movement = StockMovement(
            medicine_id=movement_in.medicine_id,
            batch_id=movement_in.batch_id,
            movement_type=movement_in.movement_type,
            quantity_change=movement_in.quantity_change,
            unit_cost=movement_in.unit_cost,
            reference=movement_in.reference,
            notes=movement_in.notes
        )
        db.add(new_movement)
        db.commit()
        db.refresh(new_movement)
        return new_movement

    except exc.IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Database integrity error occurred")
    except Exception as e:
        db.rollback()
        raise e
