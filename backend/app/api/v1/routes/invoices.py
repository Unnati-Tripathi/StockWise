from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List

from app.core.security import validate_uploaded_file
from app.db.session import get_db
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceProcessingStatus
from app.schemas.invoice import InvoiceUploadResponse, InvoiceResponse, InvoiceLineItemUpdate
from app.services.invoice_processor import (
    save_upload_file,
    process_invoice_extraction,
    approve_invoice,
    post_invoice_to_inventory,
    validate_invoice
)

router = APIRouter()

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"]

@router.post("/", response_model=InvoiceUploadResponse)
async def upload_invoice(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    contents = await file.read()
    try:
        validate_uploaded_file(file.filename or "", contents, set(ALLOWED_EXTENSIONS), MAX_FILE_SIZE)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid file type: {exc}")
    
    # Reset cursor for saving
    await file.seek(0)
    
    file_path = save_upload_file(file)
    
    invoice = Invoice(
        file_path=file_path,
        status=InvoiceProcessingStatus.UPLOADED
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    
    # Trigger extraction in background
    background_tasks.add_task(process_invoice_extraction, db, invoice)
    
    return InvoiceUploadResponse(
        id=invoice.id,
        status=invoice.status,
        message="Invoice uploaded and extraction started."
    )

@router.get("/", response_model=List[InvoiceResponse])
def get_invoices(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    invoices = db.execute(
        select(Invoice).order_by(Invoice.created_at.desc()).offset(skip).limit(limit)
    ).scalars().all()
    return invoices

@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

@router.put("/{invoice_id}/lines/{line_id}", response_model=InvoiceResponse)
def update_invoice_line(
    invoice_id: int, 
    line_id: int, 
    update_data: InvoiceLineItemUpdate,
    db: Session = Depends(get_db)
):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    if invoice.status not in [InvoiceProcessingStatus.NEEDS_REVIEW, InvoiceProcessingStatus.FAILED]:
        raise HTTPException(status_code=400, detail="Can only edit line items while in review state")
        
    line = db.get(InvoiceLineItem, line_id)
    if not line or line.invoice_id != invoice_id:
        raise HTTPException(status_code=404, detail="Line item not found")
        
    # Update fields if provided
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(line, key, value)
        
    db.commit()
    
    # Revalidate
    validate_invoice(db, invoice)
    db.refresh(invoice)
    return invoice

@router.post("/{invoice_id}/approve", response_model=InvoiceResponse)
def approve_invoice_endpoint(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    approve_invoice(db, invoice)
    db.refresh(invoice)
    return invoice

@router.post("/{invoice_id}/post", response_model=InvoiceResponse)
def post_invoice_endpoint(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    post_invoice_to_inventory(db, invoice)
    db.refresh(invoice)
    return invoice
