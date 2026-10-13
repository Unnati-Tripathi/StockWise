from datetime import date, timedelta
from app.models.inventory import InventoryBatch, StockMovement, MovementType
from app.services.replenishment import (
    calculate_usable_inventory,
    calculate_average_daily_demand,
    evaluate_risk_level,
    calculate_reorder_quantity,
    RiskLevel
)

def test_calculate_usable_inventory_excludes_expired():
    today = date(2023, 10, 1)
    b1 = InventoryBatch(batch_number="B1", quantity_on_hand=100, expiry_date=date(2023, 11, 1))
    b2 = InventoryBatch(batch_number="B2", quantity_on_hand=50, expiry_date=date(2023, 9, 1)) # expired
    b3 = InventoryBatch(batch_number="B3", quantity_on_hand=-10, expiry_date=date(2024, 1, 1)) # negative stock

    usable, warnings = calculate_usable_inventory([b1, b2, b3], today, 60)
    assert usable == 100
    assert len(warnings) == 3 # 1 for expired, 1 for negative, 1 for near expiry (B1 is in 31 days)

def test_calculate_average_daily_demand():
    m1 = StockMovement(movement_type=MovementType.SALE, quantity_change=-10)
    m2 = StockMovement(movement_type=MovementType.SALE, quantity_change=-5)
    m3 = StockMovement(movement_type=MovementType.RECEIPT, quantity_change=100) # should be ignored
    
    total, avg = calculate_average_daily_demand([m1, m2, m3], 30)
    assert total == 15
    assert avg == 0.5

def test_calculate_average_daily_demand_zero_history():
    total, avg = calculate_average_daily_demand([], 30)
    assert total == 0
    assert avg == 0.0

def test_evaluate_risk_level():
    # 0 demand
    r, w = evaluate_risk_level(100, 0, 5, 3)
    assert r == RiskLevel.UNKNOWN
    
    # Critical: exhausted
    r, w = evaluate_risk_level(0, 10, 5, 3)
    assert r == RiskLevel.CRITICAL
    
    # Critical: days_cover (4) <= lead_time (5)
    r, w = evaluate_risk_level(40, 10, 5, 3)
    assert r == RiskLevel.CRITICAL
    
    # High: days_cover (7) <= lead_time (5) + safety (3)
    r, w = evaluate_risk_level(70, 10, 5, 3)
    assert r == RiskLevel.HIGH
    
    # Medium: days_cover (10) <= lead_time (5) + safety*2 (6)
    r, w = evaluate_risk_level(100, 10, 5, 3)
    assert r == RiskLevel.MEDIUM
    
    # Low: days_cover (15) > 11
    r, w = evaluate_risk_level(150, 10, 5, 3)
    assert r == RiskLevel.LOW

def test_calculate_reorder_quantity_moq():
    # Target = 10 * (5 + 3) = 80
    # Deficit = 80 - 20 (usable) - 0 (incoming) = 60
    # MOQ = 25 -> Should round up to 75
    qty = calculate_reorder_quantity(10.0, 5, 3, 20, 0, 25)
    assert qty == 75

def test_calculate_reorder_quantity_no_deficit():
    # Target = 80
    # Deficit = 80 - 100 = -20 -> No reorder
    qty = calculate_reorder_quantity(10.0, 5, 3, 100, 0, 25)
    assert qty == 0

def test_calculate_reorder_quantity_zero_demand():
    qty = calculate_reorder_quantity(0.0, 5, 3, 0, 0, 25)
    assert qty == 0
