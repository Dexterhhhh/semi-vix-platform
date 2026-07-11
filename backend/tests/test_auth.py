from fastapi.testclient import TestClient
from app.database.database import Base, engine
from app.main import app


def _client() -> TestClient:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        yield client


def test_login_returns_temporary_mfa_state() -> None:
    for client in _client():
        response = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"})
        assert response.status_code == 200
        body = response.json()
        assert body["mfa_setup_required"] is True
        assert body["temporary_token"]


def test_unauthorized_access_is_rejected() -> None:
    for client in _client():
        assert client.get("/api/auth/me").status_code == 401
        assert client.get("/health").json() == {"status": "ok"}
