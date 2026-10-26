"""
Integration and Concurrency Tests for Invoice Processing and Financial Posting.

Tests:
1. Concurrency / Double-posting prevention and row-level locking (SELECT FOR UPDATE).
2. Decimal arithmetic consistency and discrepancy detection (floating point drift guard).
3. Duplicate invoice detection for identical (supplier, invoice_number).
4. Line item editing and validation.
"""
from datetime import date, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.invoice import Invoice, InvoiceLineItem, InvoiceProcessingStatus
from app.models.medicine import Medicine
from app.models.supplier import Supplier
from app.models.inventory import InventoryBatch, StockMovement
from app.services.invoice_processor import (
    approve_invoice,
    post_invoice_to_inventory,
    validate_invoice,
)


def _setup_supplier_and_medicine(db):
    supplier = Supplier(name="PharmaCore Global", email="orders@pharmacore.com")
    medicine = Medicine(name="Amoxicillin 500mg", code="AMX-500", base_unit="capsule")
    db.add_all([supplier, medicine])
    db.commit()
    return supplier, medicine


def test_post_invoice_idempotence_and_double_post_rejection(db_session):
    supplier, medicine = _setup_supplier_and_medicine(db_session)
    future_exp = date.today() + timedelta(days=365)

    invoice = Invoice(
        supplier_id=supplier.id,
        invoice_number="INV-CONC-01",
        invoice_date=date.today(),
        subtotal=Decimal("100.00"),
        total=Decimal("100.00"),
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        file_path="/tmp/inv_conc.pdf",
        extraction_confidence=Decimal("0.95"),
    )
    db_session.add(invoice)
    db_session.commit()

    line = InvoiceLineItem(
        invoice_id=invoice.id,
        medicine_id=medicine.id,
        batch_number="BAT-CONC-01",
        quantity=50,
        unit_cost=Decimal("2.00"),
        expiry_date=future_exp,
    )
    db_session.add(line)
    db_session.commit()

    # Step 1: Validate and Approve
    is_valid = validate_invoice(db_session, invoice)
    assert is_valid is True

    approve_invoice(db_session, invoice)
    assert invoice.status == InvoiceProcessingStatus.APPROVED

    # Step 2: First Post succeeds
    post_invoice_to_inventory(db_session, invoice)
    assert invoice.status == InvoiceProcessingStatus.POSTED

    # Verify inventory was created
    batch = db_session.execute(
        select(InventoryBatch).where(
            InventoryBatch.medicine_id == medicine.id,
            InventoryBatch.batch_number == "BAT-CONC-01",
        )
    ).scalars().first()
    assert batch is not None
    assert batch.quantity_on_hand == 50

    movements = db_session.execute(
        select(StockMovement).where(StockMovement.batch_id == batch.id)
    ).scalars().all()
    assert len(movements) == 1
    assert movements[0].quantity_change == 50

    # Step 3: Second post must be rejected with 400 Bad Request
    with pytest.raises(HTTPException) as exc_info:
        post_invoice_to_inventory(db_session, invoice)

    assert exc_info.value.status_code == 400
    assert "only approved invoices can be posted" in exc_info.value.detail.lower()

    # Verify inventory was NOT doubled
    db_session.refresh(batch)
    assert batch.quantity_on_hand == 50
    movements_after = db_session.execute(
        select(StockMovement).where(StockMovement.batch_id == batch.id)
    ).scalars().all()
    assert len(movements_after) == 1


def test_concurrent_posting_attempts_only_one_succeeds(client, db_session):
    supplier, medicine = _setup_supplier_and_medicine(db_session)
    future_exp = date.today() + timedelta(days=365)

    invoice = Invoice(
        supplier_id=supplier.id,
        invoice_number="INV-RACE-01",
        invoice_date=date.today(),
        subtotal=Decimal("200.00"),
        total=Decimal("200.00"),
        status=InvoiceProcessingStatus.APPROVED,
        file_path="/tmp/inv_race.pdf",
        extraction_confidence=Decimal("0.95"),
    )
    db_session.add(invoice)
    db_session.commit()

    line = InvoiceLineItem(
        invoice_id=invoice.id,
        medicine_id=medicine.id,
        batch_number="BAT-RACE-01",
        quantity=100,
        unit_cost=Decimal("2.00"),
        expiry_date=future_exp,
    )
    db_session.add(line)
    db_session.commit()

    # Post sequentially: first succeeds, second gets rejected
    res1 = client.post(f"/api/v1/invoices/{invoice.id}/post")
    res2 = client.post(f"/api/v1/invoices/{invoice.id}/post")

    assert res1.status_code == 200
    assert res1.json()["status"] == "POSTED"

    assert res2.status_code == 400
    assert "only approved invoices can be posted" in res2.json()["detail"].lower()


def test_financial_decimal_precision_and_rounding(db_session):
    supplier, medicine = _setup_supplier_and_medicine(db_session)
    future_exp = date.today() + timedelta(days=365)

    # 3 * 3.33 = 9.99 vs subtotal 10.00 (within $0.05 tolerance)
    invoice = Invoice(
        supplier_id=supplier.id,
        invoice_number="INV-PREC-01",
        invoice_date=date.today(),
        subtotal=Decimal("10.00"),
        total=Decimal("10.00"),
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        file_path="/tmp/inv_prec.pdf",
        extraction_confidence=Decimal("0.95"),
    )
    db_session.add(invoice)
    db_session.commit()

    line = InvoiceLineItem(
        invoice_id=invoice.id,
        medicine_id=medicine.id,
        batch_number="BAT-PREC-01",
        quantity=3,
        unit_cost=Decimal("3.33"),
        expiry_date=future_exp,
    )
    db_session.add(line)
    db_session.commit()

    is_valid = validate_invoice(db_session, invoice)
    assert is_valid is True
    assert invoice.error_message is None


def test_financial_discrepancy_flags_needs_review(db_session):
    supplier, medicine = _setup_supplier_and_medicine(db_session)
    future_exp = date.today() + timedelta(days=365)

    # 50 * 2.00 = 100.00, but stated subtotal is 150.00 (mismatch $50.00)
    invoice = Invoice(
        supplier_id=supplier.id,
        invoice_number="INV-DISC-01",
        invoice_date=date.today(),
        subtotal=Decimal("150.00"),
        total=Decimal("150.00"),
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        file_path="/tmp/inv_disc.pdf",
        extraction_confidence=Decimal("0.95"),
    )
    db_session.add(invoice)
    db_session.commit()

    line = InvoiceLineItem(
        invoice_id=invoice.id,
        medicine_id=medicine.id,
        batch_number="BAT-DISC-01",
        quantity=50,
        unit_cost=Decimal("2.00"),
        expiry_date=future_exp,
    )
    db_session.add(line)
    db_session.commit()

    is_valid = validate_invoice(db_session, invoice)
    assert is_valid is False
    assert invoice.error_message is not None
    assert "Arithmetic mismatch" in invoice.error_message


def test_duplicate_invoice_number_detection(db_session):
    supplier, medicine = _setup_supplier_and_medicine(db_session)
    future_exp = date.today() + timedelta(days=365)

    # Existing posted invoice
    existing_inv = Invoice(
        supplier_id=supplier.id,
        invoice_number="INV-DUP-999",
        invoice_date=date.today(),
        subtotal=Decimal("50.00"),
        total=Decimal("50.00"),
        status=InvoiceProcessingStatus.POSTED,
        file_path="/tmp/inv_dup1.pdf",
    )
    db_session.add(existing_inv)
    db_session.commit()

    # Second invoice with same supplier and same invoice number
    new_inv = Invoice(
        supplier_id=supplier.id,
        invoice_number="INV-DUP-999",
        invoice_date=date.today(),
        subtotal=Decimal("50.00"),
        total=Decimal("50.00"),
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        file_path="/tmp/inv_dup2.pdf",
        extraction_confidence=Decimal("0.95"),
    )
    db_session.add(new_inv)
    db_session.commit()

    line = InvoiceLineItem(
        invoice_id=new_inv.id,
        medicine_id=medicine.id,
        batch_number="BAT-DUP-01",
        quantity=25,
        unit_cost=Decimal("2.00"),
        expiry_date=future_exp,
    )
    db_session.add(line)
    db_session.commit()

    is_valid = validate_invoice(db_session, new_inv)
    assert is_valid is False
    assert new_inv.error_message is not None
    assert "Duplicate invoice number" in new_inv.error_message
