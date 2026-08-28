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


@pytest.fixture()
def next_fraud_code(db):
    """
    Every /auth/signup call now requires a valid, unclaimed 9-digit
    tax_record_code (see app.database.tax_models.FraudRecord) — this hands
    out one fresh code per call, for tests that only care about the auth
    flow itself, not the fraud-linking feature. Each call re-queries fresh
    (a separate request's own DB session claims the code it's handed), so
    calling this more than once in a test yields a different code each time.
    """
    from app.chat.db.seed import seed
    from app.database.tax_models import FraudRecord

    seed(db)

    def _get() -> str:
        record = db.query(FraudRecord).filter(FraudRecord.user_id.is_(None)).first()
        return record.claim_code

    return _get
