from app.services.assistant import AssistantService
from app.models.medicine import Medicine
from app.models.inventory import InventoryBatch
from app.models.supplier import Supplier
from app.models.associations import SupplierMedicine
from datetime import date, timedelta
from decimal import Decimal

def test_assistant_unrecognized_query(db_session):
    service = AssistantService(db_session)
    result = service.chat("What is the meaning of life?")
    assert "I can only help with inventory" in result["reply"]
    assert result["evidence"] is None

def test_assistant_lookup(db_session):
    med = Medicine(name="Aspirin", code="ASP", base_unit="box")
    db_session.add(med)
    db_session.commit()
    
    batch = InventoryBatch(medicine_id=med.id, batch_number="B1", quantity_on_hand=50, unit_purchase_price=Decimal("1.00"))
    db_session.add(batch)
    db_session.commit()
    
    service = AssistantService(db_session)
    result = service.chat("Lookup stock for all medicines")
    
    assert "inventory lookup summary" in result["reply"]
    assert result["evidence"]["tool_name"] == "lookup_inventory"
    data = result["evidence"]["data"]
    assert len(data) == 1
    assert data[0]["medicine_name"] == "Aspirin"
    assert data[0]["total_stock"] == 50

def test_assistant_expiry(db_session):
    med = Medicine(name="Aspirin", code="ASP", base_unit="box")
    db_session.add(med)
    db_session.commit()
    
    # Expired batch
    b1 = InventoryBatch(medicine_id=med.id, batch_number="B1", quantity_on_hand=50, unit_purchase_price=Decimal("1.0"), expiry_date=date.today() - timedelta(days=10))
    # Valid batch
    b2 = InventoryBatch(medicine_id=med.id, batch_number="B2", quantity_on_hand=50, unit_purchase_price=Decimal("1.0"), expiry_date=date.today() + timedelta(days=200))
    
    db_session.add_all([b1, b2])
    db_session.commit()
    
    service = AssistantService(db_session)
    result = service.chat("Which batches are approaching expiry?")
    
    assert "expired batches" in result["reply"]
    data = result["evidence"]["data"]
    assert len(data) == 1
    assert data[0]["batch_number"] == "B1"
    assert data[0]["is_expired"] is True
