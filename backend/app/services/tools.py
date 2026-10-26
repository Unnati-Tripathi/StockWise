"""
Allowlisted tool implementations for the assistant service.

Each function is a pure, read-only database query that can be called by the
Gemini function-calling loop.  No SQL injection vectors exist — all parameters
are validated before use.

Design rules
------------
- All functions are read-only (SELECT only, no mutations).
- Every parameter is validated against strict bounds before being used.
- Functions return plain dicts / lists — no ORM objects leak out.
- ``search_supplier_documents`` is a stub here; Phase 3 replaces it with the
  real RAG call once the document store is available.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryBatch
from app.models.medicine import Medicine
from app.models.supplier import Supplier
from app.models.associations import SupplierMedicine
from app.services.replenishment import generate_recommendations

logger = logging.getLogger(__name__)

# ── Parameter limits (guard against accidental or adversarial large values) ───

_MAX_LIMIT = 100          # max rows returned by any single tool call
_MAX_DAYS = 3650          # max days in expiry look-ahead (~10 years)


# ── Tool declarations (passed to the LLM as function schemas) ─────────────────

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "search_medicines",
        "description": (
            "Search the medicine catalogue by name or therapeutic category. "
            "Returns a list of matching medicines with their codes and categories."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text matched against medicine name and category.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1–100). Defaults to 10.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_inventory_status",
        "description": (
            "Return current on-hand stock levels for all medicines, or for a "
            "specific medicine when medicine_id is provided."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "medicine_id": {
                    "type": "integer",
                    "description": "Optional. Filter to a single medicine by its database ID.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_stockout_risks",
        "description": (
            "Return medicines at stockout risk, optionally filtered by risk level. "
            "Risk levels are CRITICAL, HIGH, MEDIUM, LOW."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "risk_level": {
                    "type": "string",
                    "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                    "description": "Optional. Filter to a specific risk level.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_expiring_batches",
        "description": (
            "Return inventory batches expiring within a given number of days. "
            "Includes already-expired batches (expiry_date < today)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Look-ahead window in days (default 90, max 3650).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_replenishment_recommendations",
        "description": (
            "Return AI-generated replenishment recommendations based on current "
            "stock, demand history, and supplier lead times. Optionally filter by "
            "risk level."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "risk_level": {
                    "type": "string",
                    "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                    "description": "Optional. Filter to a specific risk level.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_supplier_information",
        "description": (
            "Return supplier catalogue data: lead times, minimum order quantities, "
            "and unit purchase prices for all stocked medicines, or for a specific "
            "medicine."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "medicine_id": {
                    "type": "integer",
                    "description": "Optional. Filter to a single medicine by its database ID.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_supplier_documents",
        "description": (
            "Search uploaded supplier policy documents, SOPs, and medicine reference "
            "materials using semantic and keyword search. Returns relevant excerpts."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search documents.",
                },
            },
            "required": ["query"],
        },
    },
]

# Quick lookup: name → callable
_TOOL_REGISTRY: dict[str, Any] = {}  # populated below after function definitions


# ── Tool implementations ───────────────────────────────────────────────────────

def search_medicines(db: Session, *, query: str = "", limit: int = 10) -> list[dict]:
    """Search medicine catalogue by name / category."""
    limit = max(1, min(limit, _MAX_LIMIT))
    query = (query or "").strip()[:200]  # truncate to prevent huge LIKE patterns

    stmt = select(Medicine)
    if query:
        stmt = stmt.where(
            Medicine.name.ilike(f"%{query}%")
            | Medicine.category.ilike(f"%{query}%")
        )
    medicines = db.execute(stmt.limit(limit)).scalars().all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "code": m.code,
            "category": m.category,
            "base_unit": m.base_unit,
            "is_active": m.is_active,
        }
        for m in medicines
    ]


def get_inventory_status(
    db: Session, *, medicine_id: int | None = None
) -> list[dict]:
    """Return on-hand stock totals per medicine."""
    q = select(Medicine)
    if medicine_id is not None:
        medicine_id = int(medicine_id)
        q = q.where(Medicine.id == medicine_id)
    medicines = db.execute(q).scalars().all()

    result = []
    for med in medicines:
        batches = (
            db.execute(
                select(InventoryBatch).where(InventoryBatch.medicine_id == med.id)
            )
            .scalars()
            .all()
        )
        usable = sum(
            b.quantity_on_hand
            for b in batches
            if not b.expiry_date or b.expiry_date >= date.today()
        )
        expired = sum(
            b.quantity_on_hand
            for b in batches
            if b.expiry_date and b.expiry_date < date.today()
        )
        result.append(
            {
                "medicine_id": med.id,
                "medicine_name": med.name,
                "code": med.code,
                "usable_stock": usable,
                "expired_stock": expired,
                "batch_count": len(batches),
            }
        )
    return result


def get_stockout_risks(
    db: Session, *, risk_level: str | None = None
) -> list[dict]:
    """Return replenishment recommendations filtered by risk level."""
    if risk_level:
        risk_level = risk_level.upper().strip()
        valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        if risk_level not in valid:
            raise ValueError(f"Invalid risk_level '{risk_level}'. Must be one of {valid}.")

    recs = generate_recommendations(db).items
    if risk_level:
        recs = [r for r in recs if r.risk_level.value == risk_level]

    return [
        {
            "medicine_id": r.medicine_id,
            "medicine_name": r.medicine_name,
            "risk_level": r.risk_level.value,
            "days_of_stock_remaining": r.days_of_stock_remaining,
            "usable_stock": r.usable_stock,
            "average_daily_demand": r.average_daily_demand,
            "recommended_reorder_quantity": r.recommended_reorder_quantity,
            "preferred_supplier_name": r.preferred_supplier_name,
        }
        for r in recs
    ]


def get_expiring_batches(db: Session, *, days: int = 90) -> list[dict]:
    """Return batches expiring within `days` days (including already expired)."""
    days = max(0, min(int(days), _MAX_DAYS))
    threshold = date.today() + timedelta(days=days)

    rows = db.execute(
        select(InventoryBatch, Medicine)
        .join(Medicine, InventoryBatch.medicine_id == Medicine.id)
        .where(InventoryBatch.expiry_date <= threshold)
        .where(InventoryBatch.quantity_on_hand > 0)
        .order_by(InventoryBatch.expiry_date)
    ).all()

    today = date.today()
    return [
        {
            "medicine_name": med.name,
            "medicine_id": batch.medicine_id,
            "batch_number": batch.batch_number,
            "quantity_on_hand": batch.quantity_on_hand,
            "expiry_date": str(batch.expiry_date),
            "is_expired": batch.expiry_date < today if batch.expiry_date else False,
            "days_until_expiry": (
                (batch.expiry_date - today).days if batch.expiry_date else None
            ),
        }
        for batch, med in rows
    ]


def get_replenishment_recommendations(
    db: Session, *, risk_level: str | None = None
) -> list[dict]:
    """Return full replenishment recommendations, optionally filtered by risk."""
    # Delegate to get_stockout_risks which already handles this
    return get_stockout_risks(db, risk_level=risk_level)


def get_supplier_information(
    db: Session, *, medicine_id: int | None = None
) -> list[dict]:
    """Return supplier-medicine associations with pricing and lead times."""
    q = (
        select(SupplierMedicine, Supplier, Medicine)
        .join(Supplier, SupplierMedicine.supplier_id == Supplier.id)
        .join(Medicine, SupplierMedicine.medicine_id == Medicine.id)
    )
    if medicine_id is not None:
        medicine_id = int(medicine_id)
        q = q.where(SupplierMedicine.medicine_id == medicine_id)

    rows = db.execute(q).all()
    return [
        {
            "medicine_name": med.name,
            "medicine_id": med.id,
            "supplier_name": sup.name,
            "supplier_id": sup.id,
            "lead_time_days": assoc.lead_time_days,
            "minimum_order_quantity": assoc.minimum_order_quantity,
            "unit_purchase_price": (
                float(assoc.unit_purchase_price)
                if assoc.unit_purchase_price is not None
                else None
            ),
        }
        for assoc, sup, med in rows
    ]


def search_supplier_documents(db: Session, *, query: str = "") -> list[dict]:
    """
    Search uploaded pharmacy documents via hybrid RAG.

    Calls the real hybrid_search pipeline (lexical + vector + RRF).
    Returns a graceful placeholder when no documents are indexed.
    """
    from app.services.rag.retrieval import hybrid_search
    from app.providers.factory import get_embedding_provider
    from app.core.security import sanitize_retrieved_content

    query = (query or "").strip()[:500]
    try:
        embedding_provider = get_embedding_provider()
        chunks = hybrid_search(
            db,
            query=query,
            embedding_provider=embedding_provider,
        )
    except Exception as exc:
        logger.warning("RAG search failed: %s", exc)
        return [
            {
                "content": f"Document search is temporarily unavailable: {exc}",
                "source": "system",
                "score": 0.0,
            }
        ]

    if not chunks:
        return [
            {
                "content": (
                    "No matching documents found. Upload supplier policies, SOPs, "
                    "or medicine reference materials via the Documents page."
                ),
                "source": "system",
                "score": 0.0,
            }
        ]

    return [
        {
            "content": sanitize_retrieved_content(c.content),
            "source": c.document_filename,
            "page_number": c.page_number,
            "section_heading": c.section_heading,
            "score": c.score,
            "match_type": c.match_type,
        }
        for c in chunks
    ]


# ── Tool registry ─────────────────────────────────────────────────────────────

_TOOL_REGISTRY = {
    "search_medicines": search_medicines,
    "get_inventory_status": get_inventory_status,
    "get_stockout_risks": get_stockout_risks,
    "get_expiring_batches": get_expiring_batches,
    "get_replenishment_recommendations": get_replenishment_recommendations,
    "get_supplier_information": get_supplier_information,
    "search_supplier_documents": search_supplier_documents,
}


def execute_tool(name: str, db: Session, args: dict[str, Any]) -> Any:
    """
    Execute a named tool from the allowlist with argument validation.

    Filters unexpected parameters to guard against model hallucinations
    causing TypeErrors.

    Raises
    ------
    ValueError
        If the tool name is not in the allowlist (never execute unknown tools).
    """
    if name not in _TOOL_REGISTRY:
        raise ValueError(
            f"Tool '{name}' is not in the allowlist. "
            f"Allowed tools: {list(_TOOL_REGISTRY.keys())}"
        )
    fn = _TOOL_REGISTRY[name]
    
    # Filter unexpected keyword arguments to prevent crashes
    import inspect
    sig = inspect.signature(fn)
    valid_params = set(sig.parameters.keys()) - {"db"}
    
    filtered_args = {}
    for k, v in (args or {}).items():
        if k in valid_params:
            filtered_args[k] = v
        else:
            logger.warning("Ignoring unrecognized argument '%s' for tool '%s'", k, name)

    logger.debug("Executing tool %s with args %s", name, filtered_args)
    return fn(db, **filtered_args)
