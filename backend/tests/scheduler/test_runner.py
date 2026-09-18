from datetime import date

from app.database.database import Base, SessionLocal, engine
from app.database.models import CalculationJob, SystemSettings
from app.scheduler import runner


def test_runner_consumes_oldest_pending_job(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        first = CalculationJob(type="HISTORICAL_SVIX", start_date=date(2025, 1, 1), end_date=date(2025, 1, 2), frequency="daily", status="PENDING", progress=0)
        second = CalculationJob(type="HISTORICAL_SVIX", start_date=date(2025, 2, 1), end_date=date(2025, 2, 2), frequency="daily", status="PENDING", progress=0)
        database.add_all((first, second))
        database.commit()
        first_id = first.id
    finally:
        database.close()

    called: list[int] = []
    monkeypatch.setattr(runner, "run_historical_calculation_task", lambda job_id: called.append(job_id) or {"status": "COMPLETED"})

    assert runner.run_pending_job() == {"status": "COMPLETED"}
    assert called == [first_id]


def test_runner_clears_maintenance_request_only_after_success(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        database.add(SystemSettings(key="maintenance_requested", value="true"))
        database.commit()
    finally:
        database.close()

    monkeypatch.setattr(runner, "data_lifecycle_maintenance_task", lambda force=False: {"status": "COMPLETED", "forced": force})

    assert runner.run_maintenance() == {"status": "COMPLETED", "forced": True}
    database = SessionLocal()
    try:
        assert database.query(SystemSettings).filter_by(key="maintenance_requested").one().value == "false"
    finally:
        database.close()
