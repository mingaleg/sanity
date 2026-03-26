import time

import pytest

from sanity import StopWatch, StopWatchError, StopWatchReadings


class TestStopWatch:
    def test_context_manager_sets_timestamps(self):
        with StopWatch() as sw:
            pass
        assert sw.started is not None
        assert sw.finished is not None
        assert sw.finished >= sw.started

    def test_readings_returns_stopwatch_readings(self):
        with StopWatch() as sw:
            time.sleep(0.01)
        readings = sw.readings
        assert isinstance(readings, StopWatchReadings)
        assert readings.duration.total_seconds() >= 0.01

    def test_readings_cached(self):
        with StopWatch() as sw:
            pass
        assert sw.readings is sw.readings

    def test_readings_before_start_raises(self):
        sw = StopWatch()
        with pytest.raises(StopWatchError, match="had not started"):
            _ = sw.readings

    def test_readings_before_finish_raises(self):
        sw = StopWatch()
        sw.__enter__()
        with pytest.raises(StopWatchError, match="had not finished"):
            _ = sw.readings


class TestStopWatchReadings:
    def test_frozen(self):
        with StopWatch() as sw:
            pass
        with pytest.raises(AttributeError):
            sw.readings.duration = None
