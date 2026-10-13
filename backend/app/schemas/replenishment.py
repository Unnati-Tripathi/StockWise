from enum import Enum
from typing import List, Optional
from datetime import date
from decimal import Decimal
from pydantic import BaseModel

class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"

class ReplenishmentRecommendation(BaseModel):
    medicine_id: int
    medicine_code: str
    medicine_name: str
    
    usable_stock: int
    confirmed_incoming_stock: int
    
    units_sold_lookback: int
    average_daily_demand: float
    days_of_stock_cover: Optional[float]
    estimated_stockout_date: Optional[date]
    
    supplier_lead_time_days: int
    
    risk_level: RiskLevel
    reason_codes: List[str]
    
    recommended_reorder_quantity: Optional[int]
    
    preferred_supplier_id: Optional[int]
    preferred_supplier_name: Optional[str]
    estimated_unit_cost: Optional[Decimal]
    
    data_quality_warnings: List[str]
    explanation: str

class ReplenishmentList(BaseModel):
    items: List[ReplenishmentRecommendation]
    total_analyzed: int
    skip: int
    limit: int
