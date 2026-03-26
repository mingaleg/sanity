from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
import io
import traceback

from .time_limit import TimeLimit

from .stopwatch import StopWatch
from .verdicts import ValidationResult, ValidationVerdict


@dataclass(frozen=True, kw_only=True)
class DetailedValidationResult[Target](ValidationResult):
    target: Target
    timestamp: datetime
    duration: timedelta
    exception: BaseException | None = None


class Validator[Target](ABC):
    @abstractmethod
    def validate(self, target: Target) -> ValidationResult: ...
    
    def time_limit(self) -> timedelta | None:
        return timedelta(seconds=10)   

    def get_detailed_validation_result(self, target: Target) -> DetailedValidationResult[Target]:
        exception: BaseException | None = None
        with StopWatch() as sw, TimeLimit(self.time_limit()):
            try:
                result = self.validate(target)
            except Exception as exc:
                exception = exc
                exc_str_io = io.StringIO()
                traceback.print_exception(exc, file=exc_str_io)
                exc_str = exc_str_io.getvalue().rstrip()
                result = ValidationResult(
                    verdict=ValidationVerdict.INTERNAL_ERROR,
                    reason=exc_str,
                )
        return DetailedValidationResult[Target](
            verdict=result.verdict,
            reason=result.reason,
            target=target,
            timestamp=sw.readings.started,
            duration=sw.readings.duration,
            exception=exception,
        )
