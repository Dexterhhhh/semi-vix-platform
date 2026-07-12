import pyotp
from fastapi.testclient import TestClient

from app.api import provider as provider_api
from app.data.exceptions import ProviderUnavailableError
from app.database.database import Base, engine
from app.database.models import AuditEvent, ProviderCredential
from app.main import app


class OfflineProvider:
    async def connect(self) -> None:
        raise ProviderUnavailableError("gateway not reachable")

    async def disconnect(self) -> None:
        return None

    async def health_check(self) -> bool:
        return False


def _access_token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"}).json()
    setup = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"]}).json()
    secret = pyotp.parse_uri(setup["provisioning_uri"]).secret
    activated = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"], "totp_code": pyotp.TOTP(secret).now()})
    return activated.json()["access_token"]


def test_provider_routes_require_authentication_and_never_echo_credentials(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(provider_api, "create_provider", lambda *_args, **_kwargs: OfflineProvider())
    with TestClient(app) as client:
        assert client.get("/api/provider/status").status_code == 401
        token = _access_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        secret = "never-return-this-provider-secret"
        configured = client.post("/api/provider/configure", headers=headers, json={"provider": "IBKR", "host": "host.docker.internal", "port": 7497, "client_id": 19, "credentials": {"api_key": "id", "secret": secret}})
        assert configured.status_code == 200
        assert secret not in configured.text
        assert configured.json() == {"provider": "IBKR", "enabled": True}
        configuration = client.get("/api/provider/configuration", headers=headers)
        assert configuration.status_code == 200
        assert configuration.json()["credentials_present"] is True
        assert configuration.json()["host"] == "host.docker.internal"
        assert configuration.json()["port"] == 7497
        assert configuration.json()["client_id"] == 19
        assert secret not in configuration.text
        assert client.post("/api/provider/configure", headers=headers, json={"provider": "IBKR", "host": "localhost", "port": 70000, "unknown": True}).status_code == 422
        status = client.post("/api/provider/test-connection", headers=headers)
        assert status.status_code == 200
        assert status.json()["connected"] is False
        assert status.json()["error"] == "Provider unavailable"
    from app.database.database import SessionLocal

    database = SessionLocal()
    try:
        assert database.query(AuditEvent).filter_by(action="provider.configure").count() == 1
        assert database.query(ProviderCredential).one().secret_encrypted != secret
    finally:
        database.close()
