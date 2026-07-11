import pyotp
from fastapi.testclient import TestClient

from app.database.database import Base, engine
from app.main import app


def _access_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"}).json()
    setup = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"]}).json()
    secret = pyotp.parse_uri(setup["provisioning_uri"]).secret
    activated = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"], "totp_code": pyotp.TOTP(secret).now()})
    return activated.json()["access_token"]


def test_svix_endpoints_require_authentication_and_report_empty_history() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        assert client.get("/api/svix/current").status_code == 401
        token = _access_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/svix/current", headers=headers).status_code == 404
        assert client.get("/api/svix/history?start_date=2026-01-01&end_date=2026-01-31", headers=headers).json() == []
