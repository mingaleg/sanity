import pytest
from sqlmodel import Session, SQLModel, create_engine

from sanity.db import TargetTag, TargetTagLink, ValidationResult  # noqa: F401


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session
