import math
from datetime import date, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func

from app.models.medicine import Medicine
from app.models.inventory import InventoryBatch, StockMovement, MovementType
from app.models.associations import SupplierMedicine
from app.models.supplier import Supplier
from app.schemas.replenishment import RiskLevel, ReplenishmentRecommendation, ReplenishmentList

# --- Pure Calculation Functions ---

def calculate_usable_inventory(batches: List[InventoryBatch], today: date, warning_days: int) -> Tuple[int, List[str]]:
    usable_stock = 0
    warnings = []
    
    for batch in batches:
        # Treat negative stock as an integrity error
        if batch.quantity_on_hand < 0:
            warnings.append(f"Negative stock found in batch {batch.batch_number}")
            continue
            
        # Ignore expired batches
        if batch.expiry_date and batch.expiry_date < today:
            warnings.append(f"Excluded expired batch {batch.batch_number} ({batch.quantity_on_hand} units)")
            continue
            
        usable_stock += batch.quantity_on_hand
        
        # Flag batches near expiry
        if batch.expiry_date and batch.expiry_date <= (today + timedelta(days=warning_days)):
            warnings.append(f"Batch {batch.batch_number} approaches expiry on {batch.expiry_date}")
            
    return usable_stock, warnings

def calculate_average_daily_demand(movements: List[StockMovement], lookback_days: int) -> Tuple[int, float]:
    if lookback_days <= 0:
        return 0, 0.0
        
    total_sold = 0
    for mov in movements:
        if mov.movement_type == MovementType.SALE:
            total_sold += abs(mov.quantity_change)
            
    return total_sold, total_sold / lookback_days

def evaluate_risk_level(
    usable_stock: int, 
    average_daily_demand: float, 
    lead_time_days: int, 
    safety_stock_days: int
) -> Tuple[RiskLevel, List[str]]:
    if average_daily_demand <= 0:
        return RiskLevel.UNKNOWN, ["NO_SALES_HISTORY"]
        
    if usable_stock == 0:
        return RiskLevel.CRITICAL, ["STOCK_EXHAUSTED"]
        
    days_cover = usable_stock / average_daily_demand
    reasons = []
    
    if days_cover <= lead_time_days:
        level = RiskLevel.CRITICAL
        reasons.append("STOCKOUT_IMMINENT")
    elif days_cover <= lead_time_days + safety_stock_days:
        level = RiskLevel.HIGH
        reasons.append("BELOW_SAFETY_STOCK")
    elif days_cover <= lead_time_days + (safety_stock_days * 2):
        level = RiskLevel.MEDIUM
        reasons.append("APPROACHING_SAFETY_STOCK")
    else:
        level = RiskLevel.LOW
        
    return level, reasons

def calculate_reorder_quantity(
    average_daily_demand: float, 
    lead_time_days: int, 
    safety_stock_days: int, 
    usable_stock: int, 
    confirmed_incoming_stock: int, 
    moq: int
) -> int:
    if average_daily_demand <= 0:
        return 0
        
    target_stock = average_daily_demand * (lead_time_days + safety_stock_days)
    deficit = target_stock - usable_stock - confirmed_incoming_stock
    
    if deficit <= 0:
        return 0
        
    suggested_qty = math.ceil(deficit)
    
    # Apply minimum order quantity logic: round up to nearest multiple of MOQ if MOQ > 0
    # Or just ensure it's at least MOQ. "round upward to a valid order quantity"
    if moq > 0:
        if suggested_qty < moq:
            suggested_qty = moq
        else:
            # Round up to nearest multiple of MOQ
            remainder = suggested_qty % moq
            if remainder != 0:
                suggested_qty += (moq - remainder)
                
    return suggested_qty

def select_preferred_supplier(supplier_links: List[Tuple[SupplierMedicine, Supplier]]) -> Optional[Tuple[SupplierMedicine, Supplier]]:
    # Filter active suppliers
    active_links = [link for link in supplier_links if link[1].is_active]
    
    if not active_links:
        return None
        
    # Sort by unit_purchase_price ASC, then lead_time_days ASC
    active_links.sort(key=lambda x: (
        x[0].unit_purchase_price, 
        x[0].lead_time_days if x[0].lead_time_days is not None else x[1].default_lead_time_days
    ))
    
    return active_links[0]


# --- Service Layer Functions ---

def generate_recommendations(
    db: Session,
    lookback_days: int = 30,
    safety_stock_days: int = 3,
    expiry_warning_days: int = 60,
    limit: int = 50,
    skip: int = 0,
    risk_level: Optional[RiskLevel] = None,
    medicine_id: Optional[int] = None
) -> ReplenishmentList:
    today = date.today()
    lookback_date = today - timedelta(days=lookback_days)
    
    # 1. Base Medicine Query
    med_query = select(Medicine).where(Medicine.is_active == True)
    if medicine_id:
        med_query = med_query.where(Medicine.id == medicine_id)
        
    medicines = db.execute(med_query.offset(skip).limit(limit)).scalars().all()
    total_analyzed = len(medicines) # Since we are iterating all fetched. Actual total would need count query.
    # To correctly calculate total count without limit:
    count_q = select(func.count(Medicine.id)).where(Medicine.is_active == True)
    if medicine_id:
        count_q = count_q.where(Medicine.id == medicine_id)
    total_count = db.scalar(count_q) or 0
    
    recommendations = []
    
    for med in medicines:
        # Fetch batches
        batches = db.execute(
            select(InventoryBatch).where(InventoryBatch.medicine_id == med.id)
        ).scalars().all()
        
        # Fetch movements for demand
        movements = db.execute(
            select(StockMovement)
            .where(StockMovement.medicine_id == med.id)
            .where(StockMovement.movement_type == MovementType.SALE)
            .where(func.date(StockMovement.created_at) >= lookback_date)
        ).scalars().all()
        
        # Fetch suppliers
        supplier_links_rows = db.execute(
            select(SupplierMedicine, Supplier)
            .join(Supplier, SupplierMedicine.supplier_id == Supplier.id)
            .where(SupplierMedicine.medicine_id == med.id)
        ).all()
        supplier_links = [(row.SupplierMedicine, row.Supplier) for row in supplier_links_rows]
        
        # Perform calculations
        usable_stock, warnings = calculate_usable_inventory(batches, today, expiry_warning_days)
        units_sold, avg_daily_demand = calculate_average_daily_demand(movements, lookback_days)
        
        confirmed_incoming = 0 # Future expansion
        
        # Supplier selection
        best_supplier_link = select_preferred_supplier(supplier_links)
        
        pref_supplier_id = None
        pref_supplier_name = None
        est_unit_cost = None
        lead_time = 0
        moq = 0
        
        if best_supplier_link:
            sm, sup = best_supplier_link
            pref_supplier_id = sup.id
            pref_supplier_name = sup.name
            est_unit_cost = sm.unit_purchase_price
            lead_time = sm.lead_time_days if sm.lead_time_days is not None else sup.default_lead_time_days
            moq = sm.minimum_order_quantity
        else:
            warnings.append("No active eligible suppliers found for this medicine")
            
        r_level, reason_codes = evaluate_risk_level(usable_stock, avg_daily_demand, lead_time, safety_stock_days)
        
        # Apply filter early
        if risk_level and r_level != risk_level:
            continue
            
        reorder_qty = None
        if best_supplier_link and avg_daily_demand > 0:
            reorder_qty = calculate_reorder_quantity(
                avg_daily_demand, lead_time, safety_stock_days, usable_stock, confirmed_incoming, moq
            )
            
        days_cover = (usable_stock / avg_daily_demand) if avg_daily_demand > 0 else None
        estimated_stockout = (today + timedelta(days=int(days_cover))) if days_cover is not None else None
        
        explanation = f"Average demand is {avg_daily_demand:.2f}/day. "
        if best_supplier_link:
            explanation += f"Lead time is {lead_time} days. "
        else:
            explanation += "No supplier available to estimate lead time. "
            
        if reorder_qty is not None and reorder_qty > 0:
            explanation += f"Recommending {reorder_qty} units."
        elif reorder_qty == 0:
            explanation += "Stock is sufficient."
            
        rec = ReplenishmentRecommendation(
            medicine_id=med.id,
            medicine_code=med.code,
            medicine_name=med.name,
            usable_stock=usable_stock,
            confirmed_incoming_stock=confirmed_incoming,
            units_sold_lookback=units_sold,
            average_daily_demand=avg_daily_demand,
            days_of_stock_cover=days_cover,
            estimated_stockout_date=estimated_stockout,
            supplier_lead_time_days=lead_time,
            risk_level=r_level,
            reason_codes=reason_codes,
            recommended_reorder_quantity=reorder_qty,
            preferred_supplier_id=pref_supplier_id,
            preferred_supplier_name=pref_supplier_name,
            estimated_unit_cost=est_unit_cost,
            data_quality_warnings=warnings,
            explanation=explanation
        )
        recommendations.append(rec)
        
    return ReplenishmentList(
        items=recommendations,
        total_analyzed=total_count,
        skip=skip,
        limit=limit
    )
