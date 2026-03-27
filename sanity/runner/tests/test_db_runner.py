from collections.abc import Collection, Iterable
from datetime import datetime, UTC

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from sanity import (
    DBRunner,
    ValidationResult as EngineValidationResult,
    ValidationTarget,
    ValidationVerdict,
    Validator,
    ok,
    failed,
)
from sanity.db import TargetTag, TargetTagLink, ValidationResult


class SimpleTarget(ValidationTarget):
    def __init__(self, id: str, tags: list[str] | None = None):
        self._id = id
        self._tags = tags or []

    def sanity_validation_target_id(self) -> str:
        return self._id

    def sanity_validation_target_tags(self) -> Collection[str]:
        return self._tags


class PassingValidator(Validator[SimpleTarget]):
    def __init__(self, targets: list[SimpleTarget]):
        self._targets = targets

    def validate(self, target: SimpleTarget) -> EngineValidationResult:
        return ok(f"validated {target._id}")

    def targets_in_scope(self) -> Iterable[SimpleTarget]:
        return self._targets


class FailingValidator(Validator[SimpleTarget]):
    def __init__(self, targets: list[SimpleTarget]):
        self._targets = targets

    def validate(self, target: SimpleTarget) -> EngineValidationResult:
        return failed(f"failed {target._id}")

    def targets_in_scope(self) -> Iterable[SimpleTarget]:
        return self._targets


class CustomReasonValidator(Validator[SimpleTarget]):
    def __init__(self, targets: list[SimpleTarget], reason: str):
        self._targets = targets
        self._reason = reason

    def validate(self, target: SimpleTarget) -> EngineValidationResult:
        return ok(self._reason)

    def targets_in_scope(self) -> Iterable[SimpleTarget]:
        return self._targets


class ExplodingValidator(Validator[SimpleTarget]):
    def __init__(self, targets: list[SimpleTarget]):
        self._targets = targets

    def validate(self, target: SimpleTarget) -> EngineValidationResult:
        raise ValueError("boom")

    def targets_in_scope(self) -> Iterable[SimpleTarget]:
        return self._targets


class EmptyValidator(Validator[SimpleTarget]):
    def validate(self, target: SimpleTarget) -> EngineValidationResult:
        return ok("empty")

    def targets_in_scope(self) -> Iterable[SimpleTarget]:
        return []


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


class TestDBRunner:
    def test_run_once_stores_result(self, engine):
        target = SimpleTarget("target-1")
        db_runner = DBRunner([PassingValidator([target])], engine)

        results = list(db_runner.run_once())

        assert len(results) == 1
        assert results[0].target_id == "target-1"
        assert results[0].verdict == "PASSED"

        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored is not None
            assert stored.verdict == "PASSED"

    def test_run_once_creates_tags(self, engine):
        target = SimpleTarget("target-1", tags=["tag-a", "tag-b"])
        db_runner = DBRunner([PassingValidator([target])], engine)

        list(db_runner.run_once())

        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored is not None
            assert len(stored.tags) == 2
            assert {t.value for t in stored.tags} == {"tag-a", "tag-b"}

    def test_run_once_reuses_existing_tags(self, engine):
        target1 = SimpleTarget("target-1", tags=["shared"])
        target2 = SimpleTarget("target-2", tags=["shared"])
        db_runner = DBRunner([PassingValidator([target1, target2])], engine)

        list(db_runner.run_once())

        with Session(engine) as session:
            tags = session.exec(select(TargetTag)).all()
            assert len(tags) == 1
            assert tags[0].value == "shared"

    def test_run_once_updates_existing_result_same_verdict(self, engine):
        target = SimpleTarget("target-1")
        db_runner = DBRunner([PassingValidator([target])], engine)

        # First run
        results1 = list(db_runner.run_once())
        first_seen = results1[0].first_seen

        # Second run
        results2 = list(db_runner.run_once())

        assert results2[0].first_seen == first_seen  # unchanged
        assert results2[0].last_seen >= results2[0].first_seen

        with Session(engine) as session:
            count = len(session.exec(select(ValidationResult)).all())
            assert count == 1  # still one record

    def test_run_once_updates_existing_result_different_verdict(self, engine):
        target = SimpleTarget("target-1")

        # First run - passing
        db_runner1 = DBRunner([PassingValidator([target])], engine)
        results1 = list(db_runner1.run_once())
        assert results1[0].verdict == "PASSED"

        # Second run - failing
        db_runner2 = DBRunner([FailingValidator([target])], engine)
        results2 = list(db_runner2.run_once())
        assert results2[0].verdict == "FAILED"
        assert results2[0].first_seen > results1[0].first_seen  # reset

    def test_run_yields_continuously(self, engine):
        target = SimpleTarget("target-1")
        db_runner = DBRunner([PassingValidator([target])], engine)

        iterator = db_runner.run()
        results = [next(iterator) for _ in range(3)]

        assert len(results) == 3
        assert all(r.target_id == "target-1" for r in results)

    def test_multiple_validators(self, engine):
        target1 = SimpleTarget("target-1")
        target2 = SimpleTarget("target-2")

        db_runner = DBRunner([
            PassingValidator([target1]),
            FailingValidator([target2]),
        ], engine)

        results = list(db_runner.run_once())

        assert len(results) == 2
        assert results[0].verdict == "PASSED"
        assert results[1].verdict == "FAILED"

    def test_tags_change_between_runs(self, engine):
        target = SimpleTarget("target-1", tags=["old-tag"])
        db_runner1 = DBRunner([PassingValidator([target])], engine)
        list(db_runner1.run_once())

        # Change tags
        target._tags = ["new-tag-a", "new-tag-b"]
        db_runner2 = DBRunner([PassingValidator([target])], engine)
        list(db_runner2.run_once())

        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored is not None
            assert {t.value for t in stored.tags} == {"new-tag-a", "new-tag-b"}

    def test_duration_stored_correctly(self, engine):
        target = SimpleTarget("target-1")
        db_runner = DBRunner([PassingValidator([target])], engine)

        results = list(db_runner.run_once())

        assert results[0].duration_microseconds > 0

        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored is not None
            assert stored.duration_microseconds > 0

    def test_reason_changes_with_same_verdict(self, engine):
        target = SimpleTarget("target-1")

        # First run
        db_runner1 = DBRunner([CustomReasonValidator([target], "reason 1")], engine)
        results1 = list(db_runner1.run_once())
        assert results1[0].reason == "reason 1"

        # Second run - same verdict, different reason
        db_runner2 = DBRunner([CustomReasonValidator([target], "reason 2")], engine)
        results2 = list(db_runner2.run_once())
        assert results2[0].reason == "reason 2"
        assert results2[0].verdict == "PASSED"  # same verdict

        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored.reason == "reason 2"

    def test_validator_exception_stores_internal_error(self, engine):
        target = SimpleTarget("target-1")
        db_runner = DBRunner([ExplodingValidator([target])], engine)

        results = list(db_runner.run_once())

        assert len(results) == 1
        assert results[0].verdict == "INTERNAL_ERROR"
        assert "ValueError: boom" in results[0].reason

        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored is not None
            assert stored.verdict == "INTERNAL_ERROR"

    def test_empty_validators(self, engine):
        db_runner = DBRunner([], engine)
        results = list(db_runner.run_once())
        assert results == []

    def test_validator_with_no_targets(self, engine):
        db_runner = DBRunner([EmptyValidator()], engine)
        results = list(db_runner.run_once())
        assert results == []

    def test_target_with_no_tags(self, engine):
        target = SimpleTarget("target-1", tags=[])
        db_runner = DBRunner([PassingValidator([target])], engine)

        results = list(db_runner.run_once())

        assert len(results) == 1
        with Session(engine) as session:
            stored = session.get(ValidationResult, "target-1")
            assert stored is not None
            assert stored.tags == []
