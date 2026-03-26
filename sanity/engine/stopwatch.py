from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import Self


class StopWatch(AbstractContextManager):
    started: datetime | None = None
    finished: datetime | None = None
    time_limit: timedelta | None = None

    def __enter__(self) -> Self:
        self.started = datetime.now(UTC)
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.finished = datetime.now(UTC)
        return None

    @cached_property
    def readings(self) -> "StopWatchReadings":
        if self.started is None:
            raise StopWatchError("StopWatch had not started")
        if self.finished is None:
            raise StopWatchError("StopWatch had not finished")
        return StopWatchReadings(
            started=self.started,
            finished=self.finished,
            duration=self.finished - self.started,
        )


@dataclass(frozen=True, kw_only=True)
class StopWatchReadings:
    started: datetime
    finished: datetime
    duration: timedelta


class StopWatchError(Exception):
    ...
