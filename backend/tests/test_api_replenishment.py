def test_get_replenishment_recommendations_empty(client, db_session):
    response = client.get("/api/v1/replenishment/recommendations")
    assert response.status_code == 200
    data = response.json()
    assert data["total_analyzed"] == 0
    assert len(data["items"]) == 0

def test_get_replenishment_recommendations_with_medicine(client, db_session):
    # 1. Create a supplier
    sup_res = client.post("/api/v1/suppliers/", json={
        "name": "Test Supplier",
        "default_lead_time_days": 5
    })
    sup_id = sup_res.json()["id"]
    
    # 2. Create a medicine
    med_res = client.post("/api/v1/medicines/", json={
        "code": "RPL-01",
        "name": "Replenish Med",
        "base_unit": "box"
    })
    med_id = med_res.json()["id"]
    
    # Wait, we need to create SupplierMedicine association.
    # The API doesn't have an endpoint for this yet in Step 3!
    # So we'll have to insert it directly into db_session for this integration test.
    from app.models.associations import SupplierMedicine
    sm = SupplierMedicine(
        supplier_id=sup_id,
        medicine_id=med_id,
        unit_purchase_price=10.0,
        minimum_order_quantity=50,
        lead_time_days=4
    )
    db_session.add(sm)
    db_session.commit()
    
    # 3. Request recommendations
    response = client.get("/api/v1/replenishment/recommendations")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    item = data["items"][0]
    
    # With no sales and no stock, risk should be UNKNOWN and reorder 0
    assert item["medicine_code"] == "RPL-01"
    assert item["usable_stock"] == 0
    assert item["average_daily_demand"] == 0
    assert item["risk_level"] == "UNKNOWN"
    assert item["recommended_reorder_quantity"] is None
    
    # Test specific medicine endpoint
    single_res = client.get(f"/api/v1/replenishment/recommendations/{med_id}")
    assert single_res.status_code == 200
    assert single_res.json()["medicine_code"] == "RPL-01"
