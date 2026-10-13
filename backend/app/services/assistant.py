import json
from typing import List, Dict, Any, Optional
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.medicine import Medicine
from app.models.inventory import InventoryBatch
from app.models.supplier import Supplier
from app.models.associations import SupplierMedicine
from app.services.replenishment import generate_recommendations

class AssistantService:
    def __init__(self, db: Session):
        self.db = db

    def chat(self, query: str) -> Dict[str, Any]:
        """
        Mock LLM orchestration loop.
        It parses the query for keywords and triggers the appropriate tool.
        Returns the natural language reply and the raw tool JSON as evidence.
        """
        query_lower = query.lower()
        
        try:
            if "risk" in query_lower or "recommendation" in query_lower:
                return self._handle_recommendations(query_lower)
            elif "expiry" in query_lower or "expired" in query_lower:
                return self._handle_expiry(query_lower)
            elif "supplier" in query_lower or "compare" in query_lower:
                return self._handle_suppliers(query_lower)
            elif "draft" in query_lower or "proposal" in query_lower:
                return self._handle_draft(query_lower)
            elif "stock" in query_lower or "lookup" in query_lower:
                return self._handle_lookup(query_lower)
            else:
                return {
                    "reply": "I'm sorry, I can only help with inventory lookups, stockout risks, expiry analysis, supplier comparisons, and draft replenishment proposals. How can I assist you?",
                    "evidence": None
                }
        except Exception as e:
            return {
                "reply": f"An error occurred while executing the tool: {str(e)}",
                "evidence": None
            }

    # --- Tool Implementations ---

    def _handle_recommendations(self, query: str) -> Dict[str, Any]:
        # Tool B: Replenishment recommendations
        risk_filter = None
        if "critical" in query:
            risk_filter = "CRITICAL"
        elif "high" in query:
            risk_filter = "HIGH"
            
        recommendations = generate_recommendations(self.db).items
        
        if risk_filter:
            recommendations = [r for r in recommendations if r.risk_level.value == risk_filter]
            
        data = [r.model_dump(mode="json") for r in recommendations]
        
        reply = f"I found {len(recommendations)} medicines matching your risk criteria."
        if risk_filter:
            reply += f" These are currently evaluated at {risk_filter} risk based on demand and lead times."
            
        return {
            "reply": reply,
            "evidence": {"tool_name": "get_recommendations", "data": data}
        }

    def _handle_expiry(self, query: str) -> Dict[str, Any]:
        # Tool D: Expiry analysis
        threshold_date = date.today() + timedelta(days=90)
        
        batches = self.db.execute(
            select(InventoryBatch, Medicine)
            .join(Medicine, InventoryBatch.medicine_id == Medicine.id)
            .where(InventoryBatch.expiry_date <= threshold_date)
            .where(InventoryBatch.quantity_on_hand > 0)
        ).all()
        
        data = []
        expired_count = 0
        expiring_count = 0
        
        for batch, med in batches:
            is_expired = batch.expiry_date < date.today() if batch.expiry_date else False
            if is_expired:
                expired_count += 1
            else:
                expiring_count += 1
                
            data.append({
                "medicine_name": med.name,
                "batch_number": batch.batch_number,
                "quantity": batch.quantity_on_hand,
                "expiry_date": str(batch.expiry_date),
                "is_expired": is_expired
            })
            
        reply = f"I found {expired_count} expired batches and {expiring_count} batches expiring within the next 90 days."
        return {
            "reply": reply,
            "evidence": {"tool_name": "analyze_expiry", "data": data}
        }

    def _handle_suppliers(self, query: str) -> Dict[str, Any]:
        # Tool C: Supplier comparison
        # For simplicity in mock, just return all supplier medicines
        associations = self.db.execute(
            select(SupplierMedicine, Supplier, Medicine)
            .join(Supplier, SupplierMedicine.supplier_id == Supplier.id)
            .join(Medicine, SupplierMedicine.medicine_id == Medicine.id)
        ).all()
        
        data = []
        for assoc, sup, med in associations:
            data.append({
                "medicine_name": med.name,
                "supplier_name": sup.name,
                "lead_time_days": assoc.lead_time_days,
                "minimum_order_quantity": assoc.minimum_order_quantity,
                "price": float(assoc.contract_unit_price) if assoc.contract_unit_price else None
            })
            
        reply = f"Here is the supplier comparison data available in the system."
        return {
            "reply": reply,
            "evidence": {"tool_name": "compare_suppliers", "data": data}
        }

    def _handle_draft(self, query: str) -> Dict[str, Any]:
        # Tool E: Draft replenishment proposal
        recommendations = generate_recommendations(self.db).items
        # Filter to only critical/high for proposal
        draft = [r for r in recommendations if r.risk_level.value in ["CRITICAL", "HIGH"]]
        
        data = []
        for r in draft:
            data.append({
                "medicine_id": r.medicine_id,
                "medicine_name": r.medicine_name,
                "suggested_quantity": r.recommended_reorder_quantity,
                "supplier": r.preferred_supplier_name
            })
            
        reply = f"I have prepared a draft replenishment proposal for {len(draft)} high-risk items. No orders have been placed."
        return {
            "reply": reply,
            "evidence": {"tool_name": "draft_replenishment_proposal", "data": data}
        }

    def _handle_lookup(self, query: str) -> Dict[str, Any]:
        # Tool A: Inventory lookup
        medicines = self.db.execute(select(Medicine)).scalars().all()
        data = []
        for med in medicines:
            # sum quantities
            batches = self.db.execute(select(InventoryBatch).where(InventoryBatch.medicine_id == med.id)).scalars().all()
            total = sum(b.quantity_on_hand for b in batches)
            data.append({
                "medicine_name": med.name,
                "code": med.code,
                "total_stock": total
            })
            
        reply = f"Here is the current inventory lookup summary for all tracked medicines."
        return {
            "reply": reply,
            "evidence": {"tool_name": "lookup_inventory", "data": data}
        }
