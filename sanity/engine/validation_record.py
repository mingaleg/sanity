from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .verdicts import ValidationVerdict

if TYPE_CHECKING:
    from .target import ValidationTarget
    from .validator import DetailedValidationResult


@dataclass(frozen=True, kw_only=True)
class ValidationResultRecord:
    target_id: str
    target_tags: Collection[str]
    timestamp: datetime
    duration: timedelta
    verdict: ValidationVerdict
    reason: str
    ignored: bool = False

    @staticmethod
    def from_detailed_validation_result[T: ValidationTarget](
        result: DetailedValidationResult[T],
    ) -> ValidationResultRecord:
        target = result.target
        return ValidationResultRecord(
            target_id=target.sanity_validation_target_id(),
            target_tags=target.sanity_validation_target_tags(),
            timestamp=result.timestamp,
            duration=result.duration,
            verdict=result.verdict,
            reason=result.reason,
            ignored=result.ignored,
        )
