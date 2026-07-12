import pyotp
from datetime import date
from fastapi.testclient import TestClient

from app.api import jobs_routes
from app.database.database import Base, SessionLocal, engine
from app.database.models import CalculationJob
from app.main import app
from app.scheduler.tasks import run_historical_calculation_task


def _token(client: TestClient) -> str:
    login = client.post("/api/auth/login", json={"username": "admin", "password": "test-password"}).json()
    setup = client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"]}).json()
    secret = pyotp.parse_uri(setup["provisioning_uri"]).secret
    return client.post("/api/auth/setup-mfa", json={"temporary_token": login["temporary_token"], "totp_code": pyotp.TOTP(secret).now()}).json()["access_token"]


def test_job_and_settings_routes_are_protected_and_persist(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    dispatched: list[int] = []
    monkeypatch.setattr(jobs_routes, "dispatch_historical_job", lambda job_id: dispatched.append(job_id))
    with TestClient(app) as client:
        assert client.get("/api/jobs").status_code == 401
        headers = {"Authorization": f"Bearer {_token(client)}"}
        created = client.post("/api/jobs/create", headers=headers, json={"start_date": "2025-01-01", "end_date": "2025-01-31", "frequency": "daily"})
        assert created.status_code == 202
        job_id = created.json()["id"]
        assert dispatched == [job_id]
        assert client.get(f"/api/jobs/{job_id}", headers=headers).json()["status"] == "PENDING"
        settings = client.put("/api/settings", headers=headers, json={"refresh_frequency_minutes": 30, "selected_symbols": ["SOXX", "NVDA"], "manual_component_weights": None})
        assert settings.status_code == 200
        assert client.get("/api/settings", headers=headers).json()["selected_symbols"] == ["SOXX", "NVDA"]
        assert client.get("/api/settings/system-status", headers=headers).json()["database"] == "OK"


def test_worker_task_updates_mocked_job_lifecycle(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        job = CalculationJob(type="HISTORICAL_SVIX", start_date=date(2025, 1, 1), end_date=date(2025, 1, 2), frequency="daily", status="PENDING", progress=0)
        database.add(job)
        database.commit()
        job_id = job.id
    finally:
        database.close()
    monkeypatch.setattr("app.scheduler.tasks.calculate_svix", lambda *args: [object(), object()])
    result = run_historical_calculation_task.run(job_id)
    assert result["status"] == "COMPLETED"
    database = SessionLocal()
    try:
        saved = database.get(CalculationJob, job_id)
        assert saved.progress == 100
        assert saved.status == "COMPLETED"
    finally:
        database.close()
