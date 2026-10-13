import os
import shutil
import uuid
from typing import List, Tuple
from datetime import date
from decimal import Decimal
from fastapi import UploadFile, HTTPException

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.invoice import Invoice, InvoiceLineItem, InvoiceProcessingStatus
from app.models.medicine import Medicine
from app.models.supplier import Supplier
from app.models.inventory import InventoryBatch, StockMovement, MovementType
from app.schemas.invoice import ExtractedInvoiceData, ExtractedInvoiceLineItem

# File storage configuration
STORAGE_DIR = "storage/invoices"

def save_upload_file(upload_file: UploadFile) -> str:
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR)
    
    # Generate safe internal filename
    ext = os.path.splitext(upload_file.filename)[1]
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(STORAGE_DIR, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
        
    return file_path

# --- Provider Abstraction ---
class InvoiceExtractionProvider:
    def extract(self, file_path: str) -> ExtractedInvoiceData:
        raise NotImplementedError()

class MockExtractionProvider(InvoiceExtractionProvider):
    def extract(self, file_path: str) -> ExtractedInvoiceData:
        # Return deterministic mock data for tests and development
        return ExtractedInvoiceData(
            supplier_name="Global Pharma Ltd",
            invoice_number="INV-2023-001",
            invoice_date=date.today(),
            currency="USD",
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            line_items=[
                ExtractedInvoiceLineItem(
                    medicine_name="Amoxicillin 500mg",
                    code="AMX-500",
                    batch_number="B-12345",
                    quantity=100,
                    unit_cost=Decimal("5.00"),
                    expiry_date=date(2025, 12, 31)
                ),
                ExtractedInvoiceLineItem(
                    medicine_name="Unknown Medicine",
                    code="UNK-001",
                    batch_number="B-999",
                    quantity=50,
                    unit_cost=Decimal("20.00")
                )
            ]
        )

# Factory/Injection point
def get_extraction_provider() -> InvoiceExtractionProvider:
    return MockExtractionProvider()

# --- Workflow Services ---

def process_invoice_extraction(db: Session, invoice: Invoice) -> None:
    try:
        invoice.status = InvoiceProcessingStatus.PROCESSING
        db.commit()
        
        provider = get_extraction_provider()
        extracted_data = provider.extract(invoice.file_path)
        
        # Map supplier
        supplier = db.execute(
            select(Supplier).where(Supplier.name.ilike(f"%{extracted_data.supplier_name}%"))
        ).scalars().first()
        
        invoice.supplier_id = supplier.id if supplier else None
        invoice.extracted_supplier_name = extracted_data.supplier_name
        invoice.invoice_number = extracted_data.invoice_number
        invoice.invoice_date = extracted_data.invoice_date
        invoice.currency = extracted_data.currency
        invoice.subtotal = extracted_data.subtotal
        invoice.total = extracted_data.total
        
        # Create line items
        for line in extracted_data.line_items:
            # Try to map medicine by code or name
            medicine = None
            if line.code:
                medicine = db.execute(select(Medicine).where(Medicine.code == line.code)).scalars().first()
            if not medicine and line.medicine_name:
                medicine = db.execute(select(Medicine).where(Medicine.name.ilike(f"%{line.medicine_name}%"))).scalars().first()
                
            db_line = InvoiceLineItem(
                invoice_id=invoice.id,
                medicine_id=medicine.id if medicine else None,
                extracted_medicine_name=line.medicine_name,
                extracted_code=line.code,
                batch_number=line.batch_number,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                manufacturing_date=line.manufacturing_date,
                expiry_date=line.expiry_date
            )
            db.add(db_line)
            
        invoice.status = InvoiceProcessingStatus.NEEDS_REVIEW
        db.commit()
        
        # Run validation
        validate_invoice(db, invoice)
        
    except Exception as e:
        db.rollback()
        invoice.status = InvoiceProcessingStatus.FAILED
        invoice.error_message = str(e)
        db.commit()

def validate_invoice(db: Session, invoice: Invoice) -> bool:
    """Validates the invoice and sets has_error and validation_messages on line items."""
    has_blocking_error = False
    
    # Check for duplicate invoice
    if invoice.invoice_number and invoice.supplier_id:
        duplicate = db.execute(
            select(Invoice).where(
                Invoice.id != invoice.id,
                Invoice.invoice_number == invoice.invoice_number,
                Invoice.supplier_id == invoice.supplier_id,
                Invoice.status == InvoiceProcessingStatus.POSTED
            )
        ).scalars().first()
        
        if duplicate:
            invoice.error_message = "Duplicate invoice number for this supplier has already been posted."
            has_blocking_error = True
    
    for line in invoice.line_items:
        errors = []
        
        if not line.medicine_id:
            errors.append("Medicine not matched.")
        if not line.quantity or line.quantity <= 0:
            errors.append("Invalid quantity.")
        if not line.batch_number:
            errors.append("Batch number is required.")
        if not line.expiry_date:
            errors.append("Expiry date is required.")
        elif line.expiry_date < date.today():
            errors.append("Batch is already expired.")
            
        if line.manufacturing_date and line.expiry_date and line.expiry_date < line.manufacturing_date:
            errors.append("Expiry date is before manufacturing date.")
            
        if errors:
            line.has_error = True
            line.validation_message = " | ".join(errors)
            has_blocking_error = True
        else:
            line.has_error = False
            line.validation_message = None
            
    db.commit()
    return not has_blocking_error

def approve_invoice(db: Session, invoice: Invoice) -> None:
    if invoice.status != InvoiceProcessingStatus.NEEDS_REVIEW:
        raise HTTPException(status_code=400, detail="Invoice is not in NEEDS_REVIEW state")
        
    is_valid = validate_invoice(db, invoice)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Cannot approve invoice with validation errors")
        
    invoice.status = InvoiceProcessingStatus.APPROVED
    db.commit()

def post_invoice_to_inventory(db: Session, invoice: Invoice) -> None:
    if invoice.status != InvoiceProcessingStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only APPROVED invoices can be posted")
        
    # Revalidate
    if not validate_invoice(db, invoice):
        raise HTTPException(status_code=400, detail="Invoice validation failed during posting")
        
    try:
        # Iterate and create batches/movements inside a transaction
        for line in invoice.line_items:
            # Find or create batch (use with_for_update to lock the batch if it exists)
            batch = db.execute(
                select(InventoryBatch).where(
                    InventoryBatch.medicine_id == line.medicine_id,
                    InventoryBatch.batch_number == line.batch_number
                ).with_for_update()
            ).scalars().first()
            
            if not batch:
                batch = InventoryBatch(
                    medicine_id=line.medicine_id,
                    batch_number=line.batch_number,
                    expiry_date=line.expiry_date,
                    quantity_on_hand=0,
                    unit_purchase_price=line.unit_cost or 0
                )
                db.add(batch)
                db.flush() # flush to get batch.id
                
            # Create stock movement
            movement = StockMovement(
                medicine_id=line.medicine_id,
                batch_id=batch.id,
                movement_type=MovementType.RECEIPT,
                quantity_change=line.quantity,
                unit_cost=line.unit_cost,
                reference=f"Invoice {invoice.invoice_number}"
            )
            db.add(movement)
            
            # Update batch quantity
            batch.quantity_on_hand += line.quantity
            
        invoice.status = InvoiceProcessingStatus.POSTED
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to post invoice: {str(e)}")
