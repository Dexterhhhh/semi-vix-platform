"""Replay retained collection batches on a backup database.

Run from ``backend`` with DATABASE_URL pointed at a restored copy:
``python -m app.services.observation_replay 2026-09-22 2026-09-24``
Add ``--write`` after inspecting the dry-run batch list. Historical quote
and correlation inputs are limited to what was available at each batch time.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import MarketCollectionRun, OptionSnapshot, StockSnapshot
from app.scheduler.market_hours import _calendar, session_bounds
from app.services.svix_observation import calculate_observation


def replay_observations(database: Session, start: date, end: date, *, write: bool = False) -> list[dict[str, object]]:
    if end < start:
        raise ValueError("end must not precede start")
    results: list[dict[str, object]] = []
    for session_date in (index.date() for index in _calendar().schedule(start_date=start, end_date=end).index):
        bounds = session_bounds(session_date)
        if bounds is None:
            continue
        rows = database.query(OptionSnapshot.batch_id, OptionSnapshot.received_at).filter(
            OptionSnapshot.batch_id.is_not(None), OptionSnapshot.received_at >= bounds[0],
            OptionSnapshot.received_at <= bounds[1],
        ).order_by(OptionSnapshot.received_at.asc()).all()
        batches: dict[str, list[datetime]] = defaultdict(list)
        for batch_id, received_at in rows:
            batches[batch_id].append(received_at)
        for batch_id, timestamps in batches.items():
            run = database.query(MarketCollectionRun).filter_by(batch_id=batch_id).first()
            if run is not None and run.session_date != session_date:
                raise ValueError(f"Batch {batch_id} spans different trading sessions")
            valuation_at = run.finished_at if run and run.finished_at else max(timestamps)
            item: dict[str, object] = {"session_date": session_date.isoformat(), "batch_id": batch_id, "valuation_at": valuation_at.isoformat()}
            if not write:
                item["status"] = "READY"
                results.append(item)
                continue
            if run is None:
                stock_times = [value for (value,) in database.query(StockSnapshot.received_at).filter_by(batch_id=batch_id).all()]
                valuation_at = max((*timestamps, *stock_times))
                run = MarketCollectionRun(
                    session_date=session_date, status="COMPLETED", interval_minutes=1,
                    interval_seconds=60, started_at=min(timestamps), finished_at=valuation_at,
                    batch_id=batch_id, option_quotes_saved=len(timestamps),
                    error_message="Replay: completion inferred from latest saved input",
                )
                database.add(run)
                database.commit()
            observation = calculate_observation(database, batch_id)
            item["status"] = "OBSERVED" if observation else "NO_NEW_DATA"
            item["valuation_at"] = run.finished_at.isoformat()
            results.append(item)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay retained Semi-VIX batches in a backup database")
    parser.add_argument("start", type=date.fromisoformat)
    parser.add_argument("end", type=date.fromisoformat)
    parser.add_argument("--write", action="store_true", help="Persist inferred runs and observations")
    arguments = parser.parse_args()
    with SessionLocal() as database:
        for result in replay_observations(database, arguments.start, arguments.end, write=arguments.write):
            print(result)


if __name__ == "__main__":
    main()
