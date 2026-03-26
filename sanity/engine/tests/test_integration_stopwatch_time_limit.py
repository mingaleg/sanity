import time
from datetime import timedelta
from unittest.mock import patch

import pytest

from sanity import (
    NoEnforcementBehavior,
    StopWatch,
    TimeLimit,
    TimeLimitExceeded,
    enforce_time_limit,
)


class TestStopWatchWithTimeLimit:
    def test_stopwatch_records_full_time_when_overrun(self):
        with patch("sanity.engine.time_limit._can_enforce", return_value=False):
            with enforce_time_limit(NoEnforcementBehavior.BEST_EFFORT):
                with pytest.raises(TimeLimitExceeded):
                    with StopWatch() as sw, TimeLimit(timedelta(milliseconds=20)):
                        time.sleep(0.05)
                # StopWatch should record the actual elapsed time (~50ms), not the limit (20ms)
                assert sw.readings.duration >= timedelta(milliseconds=50)
