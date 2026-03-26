from datetime import UTC, datetime, timedelta
from typing import Self

from sqlmodel import Field, Relationship, SQLModel

from sanity.engine import ValidationResultRecord, ValidationVerdict


def _to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC-aware. Assumes naive datetimes are UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class TargetTagLink(SQLModel, table=True):
    __tablename__ = "target_tag_links"

    target_id: str = Field(foreign_key="validation_results.target_id", primary_key=True)
    tag_id: int = Field(foreign_key="target_tags.id", primary_key=True)


class TargetTag(SQLModel, table=True):
    __tablename__ = "target_tags"

    id: int | None = Field(default=None, primary_key=True)
    value: str = Field(unique=True, index=True)

    results: list["ValidationResult"] = Relationship(
        back_populates="tags", link_model=TargetTagLink
    )


class ValidationResult(SQLModel, table=True):
    __tablename__ = "validation_results"

    target_id: str = Field(primary_key=True)
    verdict: str = Field(index=True)
    reason: str
    ignored: bool = False
    first_seen: datetime = Field(index=True)
    last_seen: datetime = Field(index=True)
    duration_microseconds: int

    tags: list[TargetTag] = Relationship(back_populates="results", link_model=TargetTagLink)

    @classmethod
    def from_record(cls, record: ValidationResultRecord, tags: list[TargetTag]) -> Self:
        result = cls(
            target_id=record.target_id,
            verdict=record.verdict.value,
            reason=record.reason,
            ignored=record.ignored,
            first_seen=record.timestamp,
            last_seen=record.timestamp,
            duration_microseconds=int(record.duration.total_seconds() * 1_000_000),
        )
        result.tags = tags
        return result

    def update(self, record: ValidationResultRecord, tags: list[TargetTag]) -> None:
        """Update with new record. Resets first_seen if verdict changed."""
        if record.verdict.value != self.verdict:
            self.verdict = record.verdict.value
            self.first_seen = record.timestamp
        self.reason = record.reason
        self.ignored = record.ignored
        self.last_seen = record.timestamp
        self.duration_microseconds = int(record.duration.total_seconds() * 1_000_000)
        self.tags = tags

    def to_engine(self) -> ValidationResultRecord:
        return ValidationResultRecord(
            target_id=self.target_id,
            target_tags=tuple(t.value for t in self.tags),
            verdict=ValidationVerdict(self.verdict),
            reason=self.reason,
            ignored=self.ignored,
            timestamp=_to_utc(self.last_seen),
            duration=timedelta(microseconds=self.duration_microseconds),
        )
