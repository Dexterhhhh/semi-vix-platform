from datetime import date

from app.services.alpaca_history import _chunks, _month_windows, _utc_midnight


def test_alpaca_history_month_windows_and_chunks_are_bounded() -> None:
    assert _month_windows(date(2025, 1, 15), date(2025, 3, 2)) == [
        (date(2025, 1, 15), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 28)),
        (date(2025, 3, 1), date(2025, 3, 2)),
    ]
    batches = list(_chunks([str(index) for index in range(205)]))
    assert [len(batch) for batch in batches] == [100, 100, 5]
    assert _utc_midnight(date(2026, 7, 13)) == "2026-07-13T00:00:00Z"
