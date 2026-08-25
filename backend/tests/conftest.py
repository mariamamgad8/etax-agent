"""
Runs against the real Postgres container (DATABASE_URL) — there is no
separate test database or mocking layer for the DB yet. Each test that
writes data is responsible for cleaning up after itself; fixtures here only
guarantee the schema exists and hand out a session.
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.database.db import SessionLocal, init_db


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    init_db()


@pytest.fixture()
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]
