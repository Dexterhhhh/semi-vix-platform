import pyotp
from fastapi.testclient import TestClient
from app.database.database import Base, engine
from app.main import app


def test_mfa_setup_and_verification() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"}).json()
        setup = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"]})
        assert setup.status_code == 200
        secret = pyotp.parse_uri(setup.json()["provisioning_uri"]).secret
        activate = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"], "totp_code": pyotp.TOTP(secret).now()})
        assert activate.status_code == 200
        access_token = activate.json()["access_token"]
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}).status_code == 200

        second_login = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"}).json()
        verified = client.post("/api/auth/verify-mfa", json={"temporary_token": second_login["temporary_token"], "totp_code": pyotp.TOTP(secret).now()})
        assert verified.status_code == 200
