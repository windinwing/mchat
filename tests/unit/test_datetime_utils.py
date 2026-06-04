from datetime import datetime, timezone

from app.utils.datetime_utils import duration_ms


def test_duration_ms_naive_started_aware_finished():
    started = datetime(2026, 6, 4, 10, 0, 0)
    finished = datetime(2026, 6, 4, 10, 0, 2, tzinfo=timezone.utc)
    assert duration_ms(started, finished) == 2000


def test_duration_ms_both_aware():
    started = datetime(2026, 6, 4, 10, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 6, 4, 10, 0, 1, tzinfo=timezone.utc)
    assert duration_ms(started, finished) == 1000
