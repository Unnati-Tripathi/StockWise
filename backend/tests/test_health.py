from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "stockwise-api"
    assert data["version"] == settings.app_version

def test_invalid_endpoint():
    response = client.get("/api/v1/unknown")
    assert response.status_code == 404
