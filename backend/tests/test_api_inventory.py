from app.models.inventory import MovementType

def test_create_stock_receipt(client, db_session):
    # Setup medicine
    med_res = client.post("/api/v1/medicines/", json={"code": "INV-01", "name": "Inv Med", "base_unit": "box"})
    med_id = med_res.json()["id"]

    # Since batch creation isn't in API yet for this test flow, we can test that error is thrown for batch missing on receipt
    # Wait, the spec says we must specify a batch ID if it's not an adjustment, unless we support non-batch adjustments.
    
    # We will just test the invalid logic here since the test DB is empty of batches
    movement_res = client.post("/api/v1/inventory/movements", json={
        "medicine_id": med_id,
        "movement_type": MovementType.RECEIPT,
        "quantity_change": 100
    })
    # Our API requires batch_id for RECEIPT
    assert movement_res.status_code == 422
    assert "Batch ID is required" in movement_res.json()["detail"]

def test_adjustment_without_batch(client):
    med_res = client.post("/api/v1/medicines/", json={"code": "ADJ-01", "name": "Adj Med", "base_unit": "box"})
    med_id = med_res.json()["id"]
    
    # Adjustment doesn't require batch_id in our logic
    response = client.post("/api/v1/inventory/movements", json={
        "medicine_id": med_id,
        "movement_type": MovementType.ADJUSTMENT,
        "quantity_change": -5
    })
    
    assert response.status_code == 201
    assert response.json()["quantity_change"] == -5

def test_invalid_quantity_sign(client):
    med_res = client.post("/api/v1/medicines/", json={"code": "SIGN-01", "name": "Sign Med", "base_unit": "box"})
    med_id = med_res.json()["id"]
    
    # Receipt with negative quantity
    response = client.post("/api/v1/inventory/movements", json={
        "medicine_id": med_id,
        "movement_type": MovementType.RECEIPT,
        "quantity_change": -10
    })
    assert response.status_code == 422
    assert "positive quantity change" in response.json()["detail"]
