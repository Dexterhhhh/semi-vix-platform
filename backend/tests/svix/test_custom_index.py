from datetime import datetime, timezone

import numpy as np
import pyotp
import pytest
from fastapi.testclient import TestClient

from app.database.database import Base, engine
from app.database.models import CustomIndex, CustomIndexVersion
from app.main import app
from app.services.custom_index import CustomIndexDefinition, calculate_custom_index
from tests.svix.conftest import VALUATION_TIME, two_expiry_chain


def _token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"}).json()
    setup = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"]}).json()
    secret = pyotp.parse_uri(setup["provisioning_uri"]).secret
    return client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"], "totp_code": pyotp.TOTP(secret).now()}).json()["access_token"]


def test_custom_index_configuration_creates_versions_and_validates_weights() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {_token(client)}"}
        assert client.get("/api/custom-index", headers=headers).json() is None
        payload = {"name": "Owner AI Index", "enabled": True, "missing_policy": "STRICT", "components": [{"symbol": "nvda", "weight_percent": 60}, {"symbol": "AMD", "weight_percent": 40}]}
        created = client.put("/api/custom-index", headers=headers, json=payload)
        assert created.status_code == 200
        assert created.json()["version"] == 1
        assert created.json()["components"][0]["symbol"] == "NVDA"
        unchanged = client.put("/api/custom-index", headers=headers, json={**payload, "enabled": False})
        assert unchanged.json()["version"] == 1
        changed = client.put("/api/custom-index", headers=headers, json={**payload, "components": [{"symbol": "NVDA", "weight_percent": 50}, {"symbol": "AMD", "weight_percent": 50}]})
        assert changed.json()["version"] == 2
        invalid = client.put("/api/custom-index", headers=headers, json={**payload, "components": [{"symbol": "NVDA", "weight_percent": 80}]})
        assert invalid.status_code == 422


def test_custom_index_engine_calculates_weighted_portfolio_and_enforces_policy() -> None:
    index = CustomIndex(id=1, name="Test", enabled=True, missing_policy="STRICT")
    version = CustomIndexVersion(id=1, custom_index_id=1, version_number=1, name="Test", missing_policy="STRICT", created_at=datetime.now(timezone.utc))
    definition = CustomIndexDefinition(index=index, version=version, weights={"NVDA": .6, "AMD": .4})
    quotes = {symbol: two_expiry_chain(symbol) for symbol in definition.weights}
    returns = {symbol: (0.001 * np.sin(np.arange(260) / (position + 2))).tolist() for position, symbol in enumerate(definition.weights)}
    result = calculate_custom_index(definition, quotes, returns, VALUATION_TIME)
    assert result.value > 0
    assert result.calculation_quality > 0
    with pytest.raises(ValueError, match="missing required"):
        calculate_custom_index(definition, {"NVDA": quotes["NVDA"]}, {"NVDA": returns["NVDA"]}, VALUATION_TIME)
