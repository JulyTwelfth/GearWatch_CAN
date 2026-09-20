from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


def test_health_check_returns_service_status() -> None:
    response = TestClient(app).get("/health")
    settings = get_settings()

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }
