from dataclasses import dataclass
from enum import StrEnum


class ValidationVerdict(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, kw_only=True)
class ValidationResult:
    verdict: ValidationVerdict
    reason: str
    ignored: bool = False


def ok(reason: str = "") -> ValidationResult:
    return ValidationResult(verdict=ValidationVerdict.PASSED, reason=reason)


def failed(reason: str) -> ValidationResult:
    return ValidationResult(verdict=ValidationVerdict.FAILED, reason=reason)


def skipped(reason: str) -> ValidationResult:
    return ValidationResult(verdict=ValidationVerdict.SKIPPED, reason=reason)


def not_applicable(reason: str = "") -> ValidationResult:
    return ValidationResult(verdict=ValidationVerdict.NOT_APPLICABLE, reason=reason)


def ignored_result(result: ValidationResult) -> ValidationResult:
    return ValidationResult(verdict=result.verdict, reason=result.reason, ignored=True)


def just_ignored(reason: str) -> ValidationResult:
    return ValidationResult(verdict=ValidationVerdict.SKIPPED, reason=reason, ignored=True)
