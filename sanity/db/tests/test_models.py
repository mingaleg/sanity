from datetime import datetime, timedelta, UTC

import pytest
from sqlmodel import select

from sanity.db import TargetTag, ValidationResult
from sanity.engine import ValidationResultRecord, ValidationVerdict


def strip_tz(dt: datetime) -> datetime:
    """Strip timezone for comparison (SQLite doesn't preserve it)."""
    return dt.replace(tzinfo=None)


class TestTargetTag:
    def test_create(self, session):
        tag = TargetTag(value="test-tag")
        session.add(tag)
        session.commit()
        session.refresh(tag)

        assert tag.id is not None
        assert tag.value == "test-tag"

    def test_unique_constraint(self, session):
        tag1 = TargetTag(value="unique-tag")
        session.add(tag1)
        session.commit()

        tag2 = TargetTag(value="unique-tag")
        session.add(tag2)
        with pytest.raises(Exception):  # IntegrityError
            session.commit()


class TestValidationResult:
    def test_create(self, session):
        result = ValidationResult(
            target_id="target-1",
            verdict="PASSED",
            reason="all good",
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            duration_microseconds=1_000_000,
        )
        session.add(result)
        session.commit()

        fetched = session.exec(select(ValidationResult)).first()
        assert fetched is not None
        assert fetched.target_id == "target-1"
        assert fetched.verdict == "PASSED"
        assert fetched.duration_microseconds == 1_000_000

    def test_from_record(self, session):
        record = ValidationResultRecord(
            target_id="target-2",
            target_tags=("tag-a", "tag-b"),
            timestamp=datetime.now(UTC),
            duration=timedelta(seconds=1),
            verdict=ValidationVerdict.PASSED,
            reason="validation passed",
        )

        tag_a = TargetTag(value="tag-a")
        tag_b = TargetTag(value="tag-b")
        session.add(tag_a)
        session.add(tag_b)
        session.commit()

        result = ValidationResult.from_record(record, [tag_a, tag_b])
        session.add(result)
        session.commit()

        fetched = session.exec(select(ValidationResult)).first()
        assert fetched is not None
        assert fetched.target_id == "target-2"
        assert fetched.verdict == "PASSED"
        assert fetched.reason == "validation passed"
        assert fetched.duration_microseconds == 1_000_000
        assert len(fetched.tags) == 2
        assert {t.value for t in fetched.tags} == {"tag-a", "tag-b"}

    def test_update_same_verdict(self, session):
        now = datetime.now(UTC)
        later = now + timedelta(hours=1)

        tag = TargetTag(value="tag")
        session.add(tag)
        session.commit()

        result = ValidationResult(
            target_id="target-3",
            verdict="PASSED",
            reason="first run",
            first_seen=now,
            last_seen=now,
            duration_microseconds=500_000,
        )
        result.tags = [tag]
        session.add(result)
        session.commit()

        record = ValidationResultRecord(
            target_id="target-3",
            target_tags=("tag",),
            timestamp=later,
            duration=timedelta(seconds=2),
            verdict=ValidationVerdict.PASSED,
            reason="second run",
        )

        result.update(record, [tag])
        session.commit()

        assert result.verdict == "PASSED"
        assert result.first_seen == strip_tz(now)  # unchanged
        assert result.last_seen == strip_tz(later)
        assert result.reason == "second run"
        assert result.duration_microseconds == 2_000_000

    def test_update_different_verdict(self, session):
        now = datetime.now(UTC)
        later = now + timedelta(hours=1)

        tag = TargetTag(value="tag")
        session.add(tag)
        session.commit()

        result = ValidationResult(
            target_id="target-4",
            verdict="PASSED",
            reason="first run",
            first_seen=now,
            last_seen=now,
            duration_microseconds=500_000,
        )
        result.tags = [tag]
        session.add(result)
        session.commit()

        record = ValidationResultRecord(
            target_id="target-4",
            target_tags=("tag",),
            timestamp=later,
            duration=timedelta(seconds=3),
            verdict=ValidationVerdict.FAILED,
            reason="now failing",
        )

        result.update(record, [tag])
        session.commit()

        assert result.verdict == "FAILED"
        assert result.first_seen == strip_tz(later)  # reset
        assert result.last_seen == strip_tz(later)
        assert result.reason == "now failing"
        assert result.duration_microseconds == 3_000_000

    def test_to_engine(self, session):
        now = datetime.now(UTC)
        later = now + timedelta(hours=2)

        tag = TargetTag(value="my-tag")
        session.add(tag)
        session.commit()

        result = ValidationResult(
            target_id="target-5",
            verdict="FAILED",
            reason="something wrong",
            ignored=True,
            first_seen=now,
            last_seen=later,
            duration_microseconds=5_000_000,
        )
        result.tags = [tag]
        session.add(result)
        session.commit()
        session.refresh(result)

        record = result.to_engine()

        assert record.target_id == "target-5"
        assert record.target_tags == ("my-tag",)
        assert record.verdict == ValidationVerdict.FAILED
        assert record.reason == "something wrong"
        assert record.ignored is True
        assert record.timestamp == later
        assert record.duration == timedelta(seconds=5)


class TestTagSharing:
    def test_multiple_results_share_tag(self, session):
        shared_tag = TargetTag(value="shared")
        session.add(shared_tag)
        session.commit()

        result1 = ValidationResult(
            target_id="target-a",
            verdict="PASSED",
            reason="ok",
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            duration_microseconds=1_000_000,
        )
        result1.tags = [shared_tag]

        result2 = ValidationResult(
            target_id="target-b",
            verdict="FAILED",
            reason="not ok",
            first_seen=datetime.now(UTC),
            last_seen=datetime.now(UTC),
            duration_microseconds=2_000_000,
        )
        result2.tags = [shared_tag]

        session.add(result1)
        session.add(result2)
        session.commit()

        session.refresh(shared_tag)
        assert len(shared_tag.results) == 2
        assert {r.target_id for r in shared_tag.results} == {"target-a", "target-b"}
