from collections.abc import Iterable, Iterator
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from sanity.db import TargetTag, ValidationResult
from sanity.engine import DetailedValidationResult, ValidationResultRecord, ValidationTarget, Validator

from .runner import Runner


class DBRunner:
    """Runs validators and stores results to the database.

    Example:
        >>> engine = create_engine("sqlite:///sanity.db")
        >>> db_runner = DBRunner(validators=[MyValidator()], engine=engine)
        >>> db_runner.run()  # runs forever, storing results
    """

    def __init__(self, validators: Iterable[Validator[Any]], engine: Engine):
        self._runner = Runner(validators)
        self._engine = engine

    def run(self) -> Iterator[ValidationResult]:
        """Run validators continuously, storing results to DB."""
        while True:
            yield from self.run_once()

    def run_once(self) -> Iterator[ValidationResult]:
        """Run all validators once, storing results to DB."""
        for detailed_result in self._runner.run_once():
            yield self._store_result(detailed_result)

    def _store_result(
        self, detailed_result: DetailedValidationResult[ValidationTarget]
    ) -> ValidationResult:
        """Store a single result to the database."""
        record = ValidationResultRecord.from_detailed_validation_result(detailed_result)

        with Session(self._engine) as session:
            tags = self._get_or_create_tags(session, record.target_tags)

            existing = session.get(ValidationResult, record.target_id)
            if existing:
                existing.update(record, tags)
                result = existing
            else:
                result = ValidationResult.from_record(record, tags)
                session.add(result)

            session.commit()
            session.refresh(result)
            return result

    def _get_or_create_tags(
        self, session: Session, tag_values: Iterable[str]
    ) -> list[TargetTag]:
        """Get existing tags or create new ones."""
        tags = []
        for value in tag_values:
            stmt = select(TargetTag).where(TargetTag.value == value)
            tag = session.exec(stmt).first()
            if not tag:
                tag = TargetTag(value=value)
                session.add(tag)
                session.flush()  # get the ID
            tags.append(tag)
        return tags
