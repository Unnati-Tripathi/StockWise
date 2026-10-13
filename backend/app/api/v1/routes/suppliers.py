from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Optional
from app.db.session import get_db
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierResponse, SupplierList

router = APIRouter()

@router.get("/", response_model=SupplierList)
def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    total = db.scalar(select(func.count(Supplier.id))) or 0
    suppliers = db.execute(select(Supplier).offset(skip).limit(limit)).scalars().all()
    return {"items": suppliers, "total": total, "skip": skip, "limit": limit}

@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
    supplier_in: SupplierCreate,
    db: Session = Depends(get_db)
):
    new_supplier = Supplier(
        name=supplier_in.name.strip(),
        contact_person=supplier_in.contact_person.strip() if supplier_in.contact_person else None,
        email=supplier_in.email.strip() if supplier_in.email else None,
        phone=supplier_in.phone.strip() if supplier_in.phone else None,
        default_lead_time_days=supplier_in.default_lead_time_days
    )
    db.add(new_supplier)
    db.commit()
    db.refresh(new_supplier)
    return new_supplier

@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db)
):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier
