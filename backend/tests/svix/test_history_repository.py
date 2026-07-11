from datetime import datetime, timezone

from app.database.database import Base, SessionLocal, engine
from app.svix.models import SVIXResult
from app.svix.svix_repository import SVIXRepository


def test_svix_history_repository_upserts_and_queries_results() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        timestamp = datetime.now(timezone.utc)
        repository = SVIXRepository(database)
        first = SVIXResult(timestamp=timestamp, svix=30.0, core_vol=25.0, memory_vol=35.0, ai_vol=32.0, weights={"SOXX": 1.0}, correlation_matrix=[[1.0]], calculation_quality=0.9)
        repository.save(first)
        database.commit()
        updated = first.model_copy(update={"svix": 31.0})
        repository.save(updated)
        database.commit()
        assert repository.latest().svix == 31.0
        assert len(repository.by_time_range(timestamp, timestamp)) == 1
    finally:
        database.close()
