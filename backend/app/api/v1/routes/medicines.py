from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Optional
from app.db.session import get_db
from app.models.medicine import Medicine
from app.schemas.medicine import MedicineCreate, MedicineResponse, MedicineList

router = APIRouter()

@router.get("/", response_model=MedicineList)
def list_medicines(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    total = db.scalar(select(func.count(Medicine.id))) or 0
    medicines = db.execute(select(Medicine).offset(skip).limit(limit)).scalars().all()
    return {"items": medicines, "total": total, "skip": skip, "limit": limit}

@router.post("/", response_model=MedicineResponse, status_code=status.HTTP_201_CREATED)
def create_medicine(
    medicine_in: MedicineCreate,
    db: Session = Depends(get_db)
):
    code_normalized = medicine_in.code.strip().upper()
    existing = db.execute(select(Medicine).where(Medicine.code == code_normalized)).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Medicine with this code already exists")
    
    new_medicine = Medicine(
        code=code_normalized,
        name=medicine_in.name.strip(),
        category=medicine_in.category.strip() if medicine_in.category else None,
        base_unit=medicine_in.base_unit.strip()
    )
    db.add(new_medicine)
    db.commit()
    db.refresh(new_medicine)
    return new_medicine

@router.get("/{medicine_id}", response_model=MedicineResponse)
def get_medicine(
    medicine_id: int,
    db: Session = Depends(get_db)
):
    medicine = db.get(Medicine, medicine_id)
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine
