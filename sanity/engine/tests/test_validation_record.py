from collections.abc import Collection
from datetime import datetime, timedelta, UTC

import pytest

from sanity import ValidationResultRecord, ValidationTarget, ValidationVerdict, Validator, ValidationResult, ok


class TestValidationResultRecord:
    def test_creation(self):
        record = ValidationResultRecord(
            target_id="test:1",
            target_tags=["tag1", "tag2"],
            timestamp=datetime.now(UTC),
            duration=timedelta(seconds=1),
            verdict=ValidationVerdict.PASSED,
            reason="all good",
        )
        assert record.target_id == "test:1"
        assert record.target_tags == ["tag1", "tag2"]
        assert record.verdict == ValidationVerdict.PASSED
        assert record.reason == "all good"
        assert record.ignored is False

    def test_ignored_default_false(self):
        record = ValidationResultRecord(
            target_id="test:1",
            target_tags=[],
            timestamp=datetime.now(UTC),
            duration=timedelta(seconds=0),
            verdict=ValidationVerdict.FAILED,
            reason="bad",
        )
        assert record.ignored is False

    def test_ignored_explicit(self):
        record = ValidationResultRecord(
            target_id="test:1",
            target_tags=[],
            timestamp=datetime.now(UTC),
            duration=timedelta(seconds=0),
            verdict=ValidationVerdict.FAILED,
            reason="bad",
            ignored=True,
        )
        assert record.ignored is True

    def test_frozen(self):
        record = ValidationResultRecord(
            target_id="test:1",
            target_tags=[],
            timestamp=datetime.now(UTC),
            duration=timedelta(seconds=0),
            verdict=ValidationVerdict.PASSED,
            reason="ok",
        )
        with pytest.raises(AttributeError):
            record.target_id = "other"


class _TestTarget(ValidationTarget):
    def __init__(self, value: str):
        self.value = value

    def sanity_validation_target_id(self) -> str:
        return f"test:{self.value}"

    def sanity_validation_target_tags(self) -> Collection[str]:
        return ["test"]


class _TestValidator(Validator[_TestTarget]):
    def validate(self, target: _TestTarget) -> ValidationResult:
        return ok(f"validated {target.value}")


class TestFromDetailedValidationResult:
    def test_creates_record(self):
        validator = _TestValidator()
        target = _TestTarget("hello")
        detailed = validator.get_detailed_validation_result(target)
        record = ValidationResultRecord.from_detailed_validation_result(detailed)
        assert record.target_id == "test:hello"
        assert record.target_tags == ["test"]
        assert record.verdict == ValidationVerdict.PASSED
        assert record.reason == "validated hello"
        assert record.ignored is False
        assert record.timestamp == detailed.timestamp
        assert record.duration == detailed.duration
