from collections.abc import Iterable
from datetime import timedelta

import pytest

from sanity import (
    DetailedValidationResult,
    ValidationResult,
    ValidationVerdict,
    Validator,
    ok,
    failed,
)

from .conftest import requires_enforcement


class PassingValidator(Validator[str]):
    def validate(self, target: str) -> ValidationResult:
        return ok(f"validated {target}")

    def targets_in_scope(self) -> Iterable[str]:
        return []


class FailingValidator(Validator[str]):
    def validate(self, target: str) -> ValidationResult:
        return failed(f"invalid: {target}")

    def targets_in_scope(self) -> Iterable[str]:
        return []


class ExplodingValidator(Validator[str]):
    def validate(self, target: str) -> ValidationResult:
        raise ValueError("boom")

    def targets_in_scope(self) -> Iterable[str]:
        return []


class TestValidator:
    def test_validate_returns_result(self):
        validator = PassingValidator()
        result = validator.validate("test")
        assert result.verdict == ValidationVerdict.PASSED

    def test_get_detailed_validation_result_passing(self):
        validator = PassingValidator()
        result = validator.get_detailed_validation_result("hello")
        assert isinstance(result, DetailedValidationResult)
        assert result.verdict == ValidationVerdict.PASSED
        assert result.reason == "validated hello"
        assert result.target == "hello"
        assert result.timestamp is not None
        assert result.duration.total_seconds() >= 0

    def test_get_detailed_validation_result_failing(self):
        validator = FailingValidator()
        result = validator.get_detailed_validation_result("bad")
        assert result.verdict == ValidationVerdict.FAILED
        assert result.reason == "invalid: bad"
        assert result.target == "bad"

    def test_get_detailed_validation_result_exception(self):
        validator = ExplodingValidator()
        result = validator.get_detailed_validation_result("x")
        assert result.verdict == ValidationVerdict.INTERNAL_ERROR
        assert "ValueError: boom" in result.reason
        assert result.target == "x"


class TestDetailedValidationResult:
    def test_frozen(self):
        validator = PassingValidator()
        result = validator.get_detailed_validation_result("test")
        with pytest.raises(AttributeError):
            result.target = "other"

    def test_exception_none_on_success(self):
        validator = PassingValidator()
        result = validator.get_detailed_validation_result("test")
        assert result.exception is None

    def test_exception_preserved_on_error(self):
        validator = ExplodingValidator()
        result = validator.get_detailed_validation_result("test")
        assert isinstance(result.exception, ValueError)
        assert str(result.exception) == "boom"


class SlowValidator(Validator[str]):
    def validate(self, target: str) -> ValidationResult:
        while True:
            pass

    def targets_in_scope(self) -> Iterable[str]:
        return []

    def time_limit(self) -> timedelta | None:
        return timedelta(milliseconds=50)


class CustomTimeLimitValidator(Validator[str]):
    def validate(self, target: str) -> ValidationResult:
        return ok("done")

    def targets_in_scope(self) -> Iterable[str]:
        return []

    def time_limit(self) -> timedelta | None:
        return timedelta(seconds=30)


class NoTimeLimitValidator(Validator[str]):
    def validate(self, target: str) -> ValidationResult:
        return ok("done")

    def targets_in_scope(self) -> Iterable[str]:
        return []

    def time_limit(self) -> timedelta | None:
        return None


class TestValidatorTimeLimit:
    def test_default_time_limit(self):
        validator = PassingValidator()
        assert validator.time_limit() == timedelta(seconds=10)

    def test_custom_time_limit(self):
        validator = CustomTimeLimitValidator()
        assert validator.time_limit() == timedelta(seconds=30)

    def test_no_time_limit(self):
        validator = NoTimeLimitValidator()
        assert validator.time_limit() is None

    @requires_enforcement
    def test_validator_exceeds_time_limit(self):
        from sanity import TimeLimitExceeded

        validator = SlowValidator()
        result = validator.get_detailed_validation_result("test")
        assert result.verdict == ValidationVerdict.INTERNAL_ERROR
        assert isinstance(result.exception, TimeLimitExceeded)

    def test_validator_with_no_time_limit_completes(self):
        validator = NoTimeLimitValidator()
        result = validator.get_detailed_validation_result("test")
        assert result.verdict == ValidationVerdict.PASSED
        assert result.exception is None
