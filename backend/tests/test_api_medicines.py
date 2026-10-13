def test_create_medicine(client):
    response = client.post(
        "/api/v1/medicines/",
        json={"code": "TEST-01", "name": "Test Med", "base_unit": "box"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["code"] == "TEST-01"
    assert data["name"] == "Test Med"
    assert data["is_active"] is True
    assert "id" in data

def test_create_duplicate_medicine_code(client):
    client.post("/api/v1/medicines/", json={"code": "DUP-01", "name": "M1", "base_unit": "box"})
    response = client.post("/api/v1/medicines/", json={"code": "dup-01", "name": "M2", "base_unit": "strip"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

def test_get_medicines_list(client):
    client.post("/api/v1/medicines/", json={"code": "MED1", "name": "M1", "base_unit": "box"})
    client.post("/api/v1/medicines/", json={"code": "MED2", "name": "M2", "base_unit": "box"})
    
    response = client.get("/api/v1/medicines/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
