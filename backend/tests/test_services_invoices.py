import pytest
from datetime import date
from decimal import Decimal
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceProcessingStatus
from app.models.medicine import Medicine
from app.models.inventory import InventoryBatch
from app.services.invoice_processor import (
    validate_invoice, 
    approve_invoice,
    post_invoice_to_inventory
)
from fastapi import HTTPException

def test_validate_invoice_success(db_session):
    # Setup medicine
    med = Medicine(name="Test Med", code="TM-01", base_unit="box")
    db_session.add(med)
    db_session.commit()
    
    # Setup invoice
    inv = Invoice(
        file_path="dummy.pdf",
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        supplier_id=1,
        invoice_number="INV-1"
    )
    db_session.add(inv)
    db_session.commit()
    
    # Setup valid line item
    line = InvoiceLineItem(
        invoice_id=inv.id,
        medicine_id=med.id,
        quantity=10,
        batch_number="B-1",
        expiry_date=date(2030, 1, 1)
    )
    db_session.add(line)
    db_session.commit()
    
    assert validate_invoice(db_session, inv) is True
    assert line.has_error is False

def test_validate_invoice_missing_medicine(db_session):
    inv = Invoice(file_path="dummy.pdf", status=InvoiceProcessingStatus.NEEDS_REVIEW)
    db_session.add(inv)
    db_session.commit()
    
    line = InvoiceLineItem(
        invoice_id=inv.id,
        medicine_id=None, # Missing
        quantity=10,
        batch_number="B-1",
        expiry_date=date(2030, 1, 1)
    )
    db_session.add(line)
    db_session.commit()
    
    assert validate_invoice(db_session, inv) is False
    assert line.has_error is True
    assert "Medicine not matched" in line.validation_message

def test_validate_invoice_duplicate(db_session):
    # Posted invoice
    posted = Invoice(
        file_path="dummy.pdf",
        status=InvoiceProcessingStatus.POSTED,
        supplier_id=1,
        invoice_number="DUP-1"
    )
    db_session.add(posted)
    db_session.commit()
    
    # New invoice with same number
    inv = Invoice(
        file_path="dummy.pdf",
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        supplier_id=1,
        invoice_number="DUP-1"
    )
    db_session.add(inv)
    db_session.commit()
    
    assert validate_invoice(db_session, inv) is False
    assert "Duplicate" in inv.error_message

def test_approve_invoice(db_session):
    med = Medicine(name="Test Med", code="TM-01", base_unit="box")
    db_session.add(med)
    db_session.commit()
    
    inv = Invoice(file_path="dummy.pdf", status=InvoiceProcessingStatus.NEEDS_REVIEW)
    db_session.add(inv)
    db_session.commit()
    
    line = InvoiceLineItem(
        invoice_id=inv.id, medicine_id=med.id, quantity=10, batch_number="B-1", expiry_date=date(2030, 1, 1)
    )
    db_session.add(line)
    db_session.commit()
    
    approve_invoice(db_session, inv)
    assert inv.status == InvoiceProcessingStatus.APPROVED

def test_post_invoice_to_inventory(db_session):
    med = Medicine(name="Test Med", code="TM-01", base_unit="box")
    db_session.add(med)
    db_session.commit()
    
    inv = Invoice(file_path="dummy.pdf", status=InvoiceProcessingStatus.APPROVED)
    db_session.add(inv)
    db_session.commit()
    
    line = InvoiceLineItem(
        invoice_id=inv.id, medicine_id=med.id, quantity=10, batch_number="B-1", expiry_date=date(2030, 1, 1), unit_cost=Decimal("5.00")
    )
    db_session.add(line)
    db_session.commit()
    
    post_invoice_to_inventory(db_session, inv)
    
    assert inv.status == InvoiceProcessingStatus.POSTED
    
    # Check inventory batch created
    batch = db_session.query(InventoryBatch).filter_by(batch_number="B-1").first()
    assert batch is not None
    assert batch.quantity_on_hand == 10
    
    # Ensure repeated posting fails
    with pytest.raises(HTTPException):
        post_invoice_to_inventory(db_session, inv)
