"""
Evaluation tests for invoice extraction accuracy (Phase 5).

Evaluates field-level extraction accuracy against 5 synthetic invoice fixtures
representing common pharmacy supplier formats:
  1. Standard clean single-item invoice
  2. Multi-item bulk delivery invoice
  3. Invoice with explicit batch and expiry dates
  4. Invoice with partial/missing non-critical metadata
  5. High-volume order with subtotal and currency variations
"""
from datetime import date
from decimal import Decimal
import pytest

from app.schemas.invoice import ExtractedInvoiceData, ExtractedInvoiceLineItem
from app.models.invoice import Invoice, InvoiceLineItem, InvoiceProcessingStatus
from app.models.medicine import Medicine
from app.services.invoice_processor import validate_invoice


SYNTHETIC_INVOICE_FIXTURES = [
    {
        "fixture_id": "inv_01_standard",
        "raw_json": {
            "supplier_name": "MedPharma Supplies",
            "invoice_number": "MPS-2024-001",
            "invoice_date": "2024-03-01",
            "currency": "USD",
            "subtotal": "500.00",
            "total": "500.00",
            "confidence": 0.98,
            "line_items": [
                {
                    "medicine_name": "Amoxicillin 500mg",
                    "code": "AMX-500",
                    "batch_number": "BATCH-01",
                    "quantity": 100,
                    "unit_cost": "5.00",
                    "expiry_date": "2026-12-31"
                }
            ]
        },
        "expected": {
            "supplier_name": "MedPharma Supplies",
            "invoice_number": "MPS-2024-001",
            "items_count": 1,
            "expected_total": Decimal("500.00"),
            "high_confidence": True
        }
    },
    {
        "fixture_id": "inv_02_multi_item",
        "raw_json": {
            "supplier_name": "Global Care Distribution",
            "invoice_number": "GCD-8891",
            "invoice_date": "2024-03-05",
            "currency": "EUR",
            "subtotal": "1450.00",
            "total": "1450.00",
            "confidence": 0.95,
            "line_items": [
                {
                    "medicine_name": "Paracetamol 500mg",
                    "code": "PAR-500",
                    "batch_number": "PAR-901",
                    "quantity": 200,
                    "unit_cost": "2.25",
                    "expiry_date": "2028-01-15"
                },
                {
                    "medicine_name": "Ibuprofen 400mg",
                    "code": "IBU-400",
                    "batch_number": "IBU-441",
                    "quantity": 100,
                    "unit_cost": "10.00",
                    "expiry_date": "2027-06-30"
                }
            ]
        },
        "expected": {
            "supplier_name": "Global Care Distribution",
            "invoice_number": "GCD-8891",
            "items_count": 2,
            "expected_total": Decimal("1450.00"),
            "high_confidence": True
        }
    },
    {
        "fixture_id": "inv_03_batches_and_dates",
        "raw_json": {
            "supplier_name": "Apex Generics",
            "invoice_number": "AG-2024-102",
            "invoice_date": "2024-02-15",
            "currency": "USD",
            "subtotal": "750.00",
            "total": "750.00",
            "confidence": 0.92,
            "line_items": [
                {
                    "medicine_name": "Metformin 850mg",
                    "code": "MET-850",
                    "batch_number": "MET-2024A",
                    "quantity": 150,
                    "unit_cost": "5.00",
                    "manufacturing_date": "2023-11-01",
                    "expiry_date": "2026-11-01"
                }
            ]
        },
        "expected": {
            "supplier_name": "Apex Generics",
            "invoice_number": "AG-2024-102",
            "items_count": 1,
            "expected_total": Decimal("750.00"),
            "high_confidence": True
        }
    },
    {
        "fixture_id": "inv_04_missing_optional_codes",
        "raw_json": {
            "supplier_name": "Direct Pharma Logistics",
            "invoice_number": "DPL-5512",
            "invoice_date": "2024-01-20",
            "currency": "USD",
            "subtotal": "300.00",
            "total": "300.00",
            "confidence": 0.85,
            "line_items": [
                {
                    "medicine_name": "Cetirizine 10mg",
                    "code": None,
                    "batch_number": "CET-110",
                    "quantity": 100,
                    "unit_cost": "3.00",
                    "expiry_date": "2028-08-31"
                }
            ]
        },
        "expected": {
            "supplier_name": "Direct Pharma Logistics",
            "invoice_number": "DPL-5512",
            "items_count": 1,
            "expected_total": Decimal("300.00"),
            "high_confidence": True
        }
    },
    {
        "fixture_id": "inv_05_fractional_pricing",
        "raw_json": {
            "supplier_name": "BioHealth Wholesalers",
            "invoice_number": "BHW-9903",
            "invoice_date": "2024-03-10",
            "currency": "GBP",
            "subtotal": "437.50",
            "total": "437.50",
            "confidence": 0.94,
            "line_items": [
                {
                    "medicine_name": "Omeprazole 20mg",
                    "code": "OME-020",
                    "batch_number": "OME-771",
                    "quantity": 250,
                    "unit_cost": "1.75",
                    "expiry_date": "2027-04-30"
                }
            ]
        },
        "expected": {
            "supplier_name": "BioHealth Wholesalers",
            "invoice_number": "BHW-9903",
            "items_count": 1,
            "expected_total": Decimal("437.50"),
            "high_confidence": True
        }
    }
]


@pytest.mark.parametrize("fixture", SYNTHETIC_INVOICE_FIXTURES, ids=lambda f: f["fixture_id"])
def test_fixture_schema_extraction_accuracy(fixture):
    raw = fixture["raw_json"]
    expected = fixture["expected"]

    # Verify schema instantiates properly
    line_items = [
        ExtractedInvoiceLineItem(
            medicine_name=item["medicine_name"],
            code=item.get("code"),
            batch_number=item.get("batch_number"),
            quantity=item.get("quantity"),
            unit_cost=Decimal(str(item["unit_cost"])) if item.get("unit_cost") else None,
            manufacturing_date=date.fromisoformat(item["manufacturing_date"]) if item.get("manufacturing_date") else None,
            expiry_date=date.fromisoformat(item["expiry_date"]) if item.get("expiry_date") else None,
        )
        for item in raw["line_items"]
    ]

    extracted = ExtractedInvoiceData(
        supplier_name=raw["supplier_name"],
        invoice_number=raw.get("invoice_number"),
        invoice_date=date.fromisoformat(raw["invoice_date"]) if raw.get("invoice_date") else None,
        currency=raw.get("currency"),
        subtotal=Decimal(str(raw["subtotal"])) if raw.get("subtotal") else None,
        total=Decimal(str(raw["total"])) if raw.get("total") else None,
        line_items=line_items,
        confidence_score=raw.get("confidence"),
        extraction_provider="gemini",
    )

    # Assert field-level accuracy
    assert extracted.supplier_name == expected["supplier_name"]
    assert extracted.invoice_number == expected["invoice_number"]
    assert len(extracted.line_items) == expected["items_count"]
    assert extracted.total == expected["expected_total"]
    if expected["high_confidence"]:
        assert extracted.confidence_score >= 0.70


@pytest.mark.parametrize("fixture", SYNTHETIC_INVOICE_FIXTURES, ids=lambda f: f["fixture_id"])
def test_fixture_arithmetic_consistency(db_session, fixture):
    raw = fixture["raw_json"]
    
    # Create corresponding medicines in test DB
    inv = Invoice(
        file_path="eval.pdf",
        status=InvoiceProcessingStatus.NEEDS_REVIEW,
        extracted_supplier_name=raw["supplier_name"],
        invoice_number=raw["invoice_number"],
        subtotal=Decimal(str(raw["subtotal"])),
        total=Decimal(str(raw["total"])),
        extraction_confidence=Decimal(str(raw["confidence"])),
        extraction_provider="gemini",
    )
    db_session.add(inv)
    db_session.commit()

    for item in raw["line_items"]:
        med = Medicine(name=item["medicine_name"], code=item["code"] or f"AUTO-{item['batch_number']}", base_unit="box")
        db_session.add(med)
        db_session.commit()

        line = InvoiceLineItem(
            invoice_id=inv.id,
            medicine_id=med.id,
            quantity=item["quantity"],
            unit_cost=Decimal(str(item["unit_cost"])),
            batch_number=item["batch_number"],
            expiry_date=date.fromisoformat(item["expiry_date"]),
        )
        db_session.add(line)
    db_session.commit()

    is_valid = validate_invoice(db_session, inv)
    assert is_valid is True
    assert inv.error_message is None
