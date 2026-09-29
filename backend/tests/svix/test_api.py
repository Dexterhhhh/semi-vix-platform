import pyotp
import json
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient

from app.database.database import Base, SessionLocal, engine
from app.database.models import MarketCollectionRun, SVIXHistory, SVIXObservation
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


def test_history_returns_one_preferred_point_per_day() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        token = _access_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        database = SessionLocal()
        try:
            database.add_all([
                SVIXHistory(timestamp=datetime(2026, 7, 13, 13, 35, tzinfo=timezone.utc), svix=40, core_vol=41, memory_vol=42, ai_vol=43, calculation_quality=.2, estimated=True),
                SVIXHistory(timestamp=datetime(2026, 7, 13, 13, 40, tzinfo=timezone.utc), svix=44, core_vol=45, memory_vol=46, ai_vol=47, calculation_quality=.5, estimated=False, source_feed="alpaca:indicative"),
                SVIXHistory(timestamp=datetime(2026, 7, 13, 13, 50, tzinfo=timezone.utc), svix=45, core_vol=46, memory_vol=47, ai_vol=48, calculation_quality=.5, estimated=False, source_feed="alpaca:indicative"),
                SVIXHistory(timestamp=datetime(2026, 7, 14, 13, 40, tzinfo=timezone.utc), svix=50, core_vol=51, memory_vol=52, ai_vol=53, calculation_quality=.3, estimated=True),
            ])
            database.commit()
        finally:
            database.close()
        response = client.get("/api/svix/history?start_date=2026-07-13&end_date=2026-07-14", headers=headers)
        assert response.status_code == 200
        points = response.json()
        assert len(points) == 2
        assert points[0]["svix"] == 45
        assert points[0]["estimated"] is False
        assert points[1]["svix"] == 50


def test_intraday_and_current_accept_missing_components() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {_access_token(client)}"}
        database = SessionLocal()
        at = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)
        try:
            database.add(MarketCollectionRun(session_date=date(2026, 9, 22), status="COMPLETED", interval_minutes=1, interval_seconds=60, started_at=at, finished_at=at, batch_id="partial-api"))
            database.add(SVIXObservation(session_date=date(2026, 9, 22), valuation_at=at, batch_id="partial-api", method_version="semivix-observe-v1", svix=None, core=None, memory=30, ai=40, status="PARTIAL_COVERAGE", coverage=.25, cached_coverage=0, source_feed="alpaca:indicative", details=json.dumps({"assets": {"MU": {"status": "NEW", "term_method": "single_expiry"}}, "component_counts": {"memory": "1/2", "ai": "1/3"}, "reasons": {"svix": "SOXX_UNAVAILABLE"}, "oldest_input_at": "2026-09-22T13:59:00+00:00"})))
            database.commit()
        finally:
            database.close()
        response = client.get("/api/svix/intraday?session_date=2026-09-22", headers=headers)
        assert response.status_code == 200
        assert response.json()[0]["svix"] is None
        assert response.json()[0]["memory"] == 30
        assert client.get("/api/svix/current", headers=headers).json()["core"] is None
