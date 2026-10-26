import os
import json
import shutil
import uuid
import logging
from typing import List, Tuple, Optional
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import UploadFile, HTTPException

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.invoice import Invoice, InvoiceLineItem, InvoiceProcessingStatus
from app.models.medicine import Medicine
from app.models.supplier import Supplier
from app.models.inventory import InventoryBatch, StockMovement, MovementType
from app.schemas.invoice import ExtractedInvoiceData, ExtractedInvoiceLineItem
from app.core.config import settings

logger = logging.getLogger(__name__)

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
            ],
            extraction_provider="mock",
            confidence_score=1.0,
        )


class GeminiExtractionProvider(InvoiceExtractionProvider):
    """
    Invoice extraction using Gemini's document understanding capabilities.

    Sends the invoice file to Gemini with a strict JSON schema prompt.
    Fields the model cannot determine are returned as null — it never invents values.
    Low-confidence results are flagged in the returned data.
    """

    _EXTRACTION_PROMPT = """You are an expert pharmacy invoice parser.

Extract ALL fields from the invoice document and return ONLY valid JSON matching this exact schema:
{
  "supplier_name": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "YYYY-MM-DD or null",
  "currency": "string (ISO 4217, e.g. USD) or null",
  "subtotal": "decimal string or null",
  "total": "decimal string or null",
  "confidence": 0.0 to 1.0,
  "line_items": [
    {
      "medicine_name": "string",
      "code": "string or null",
      "batch_number": "string or null",
      "quantity": integer or null,
      "unit_cost": "decimal string or null",
      "manufacturing_date": "YYYY-MM-DD or null",
      "expiry_date": "YYYY-MM-DD or null"
    }
  ]
}

Rules:
- Return ONLY the JSON object — no markdown, no explanations.
- If a field is not clearly visible, set it to null — NEVER invent values.
- quantity must be a plain integer (not a string).
- All monetary amounts must be decimal strings (e.g. "12.50")."""

    def extract(self, file_path: str) -> ExtractedInvoiceData:
        try:
            from google import genai  # type: ignore[import]
            from google.genai import types  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("google-genai is not installed.") from exc

        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required for GeminiExtractionProvider."
            )

        client = genai.Client(api_key=api_key)

        # Read and encode the file
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        _, ext = os.path.splitext(file_path)
        mime_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        mime_type = mime_map.get(ext.lower(), "application/octet-stream")

        try:
            response = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    types.Part.from_text(text=self._EXTRACTION_PROMPT),
                ],
            )
            raw_text = response.text or ""
        except Exception as exc:
            logger.error("Gemini invoice extraction failed: %s", exc)
            raise RuntimeError(f"Gemini extraction failed: {exc}") from exc

        # Strip markdown fences if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Gemini extraction JSON: %s", exc)
            raise RuntimeError(
                f"Gemini returned invalid JSON: {exc}. Raw: {cleaned[:200]}"
            ) from exc

        confidence = float(data.get("confidence", 0.5))

        def _to_decimal(val) -> Optional[Decimal]:
            if val is None:
                return None
            try:
                return Decimal(str(val))
            except InvalidOperation:
                return None

        def _to_date(val) -> Optional[date]:
            if not val:
                return None
            try:
                from datetime import date as dt_date
                return dt_date.fromisoformat(str(val))
            except ValueError:
                return None

        line_items = []
        for item in data.get("line_items", []):
            line_items.append(
                ExtractedInvoiceLineItem(
                    medicine_name=item.get("medicine_name") or "Unknown",
                    code=item.get("code"),
                    batch_number=item.get("batch_number"),
                    quantity=item.get("quantity"),
                    unit_cost=_to_decimal(item.get("unit_cost")),
                    manufacturing_date=_to_date(item.get("manufacturing_date")),
                    expiry_date=_to_date(item.get("expiry_date")),
                )
            )

        return ExtractedInvoiceData(
            supplier_name=data.get("supplier_name") or "Unknown Supplier",
            invoice_number=data.get("invoice_number"),
            invoice_date=_to_date(data.get("invoice_date")),
            currency=data.get("currency"),
            subtotal=_to_decimal(data.get("subtotal")),
            total=_to_decimal(data.get("total")),
            line_items=line_items,
            confidence_score=confidence,
            extraction_provider="gemini",
            raw_extraction_result=cleaned,
        )


# Factory/Injection point
def get_extraction_provider() -> InvoiceExtractionProvider:
    provider_name = settings.invoice_extraction_provider.lower()
    if provider_name == "gemini":
        if not settings.gemini_api_key:
            logger.warning(
                "invoice_extraction_provider=gemini but GEMINI_API_KEY is not set. "
                "Falling back to mock extraction."
            )
            return MockExtractionProvider()
        return GeminiExtractionProvider()
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
        invoice.extraction_provider = extracted_data.extraction_provider
        invoice.extraction_confidence = (
            Decimal(str(round(extracted_data.confidence_score, 3)))
            if extracted_data.confidence_score is not None
            else None
        )
        if extracted_data.raw_extraction_result:
            try:
                invoice.raw_extraction_json = json.loads(extracted_data.raw_extraction_result)
            except Exception:
                invoice.raw_extraction_json = {"raw": extracted_data.raw_extraction_result}
        else:
            invoice.raw_extraction_json = None
        
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

    # Arithmetic validation: sum of line items vs subtotal/total
    line_total = Decimal("0.00")
    has_line_prices = False
    for line in invoice.line_items:
        if line.quantity is not None and line.unit_cost is not None:
            line_total += Decimal(str(line.quantity)) * Decimal(str(line.unit_cost))
            has_line_prices = True

    expected_total = invoice.subtotal if invoice.subtotal is not None else invoice.total
    if expected_total is not None and has_line_prices and line_total > 0:
        diff = abs(line_total - Decimal(str(expected_total)))
        if diff > Decimal("0.05"):
            arith_msg = f"Arithmetic mismatch: Line items sum ({line_total:.2f}) does not match expected total ({Decimal(str(expected_total)):.2f})."
            if invoice.error_message:
                invoice.error_message += f" | {arith_msg}"
            else:
                invoice.error_message = arith_msg
            has_blocking_error = True

    # Confidence threshold check: low-confidence extractions flagged for review
    threshold = Decimal(str(settings.invoice_confidence_threshold))
    if invoice.extraction_confidence is not None and invoice.extraction_confidence < threshold:
        conf_msg = f"Low extraction confidence ({float(invoice.extraction_confidence):.2f} < {float(threshold):.2f}). Manual review required."
        if invoice.error_message:
            invoice.error_message += f" | {conf_msg}"
        else:
            invoice.error_message = conf_msg
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
    # Concurrency control: Acquire exclusive row lock on the invoice to prevent concurrent double-posting
    locked_inv = db.execute(
        select(Invoice).where(Invoice.id == invoice.id).with_for_update()
    ).scalars().first()

    target_invoice = locked_inv or invoice

    if target_invoice.status != InvoiceProcessingStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only APPROVED invoices can be posted")
        
    # Revalidate
    if not validate_invoice(db, target_invoice):
        raise HTTPException(status_code=400, detail="Invoice validation failed during posting")
        
    try:
        # Iterate and create batches/movements inside a transaction
        for line in target_invoice.line_items:
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
                reference=f"Invoice {target_invoice.invoice_number}"
            )
            db.add(movement)
            
            # Update batch quantity
            batch.quantity_on_hand += line.quantity
            
        target_invoice.status = InvoiceProcessingStatus.POSTED
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to post invoice: {str(e)}")
