from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS auth"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS tax"))
        conn.commit()
    from app.database import models, tax_models  # noqa: F401  (register mappers before create_all)

    Base.metadata.create_all(engine)

    # create_all() only creates missing TABLES, never alters an existing
    # one — so a column added to a model after the table already exists on
    # a running database (like last_active_at here) needs its own idempotent
    # DDL, matching the pattern security_setup.py already uses for anything
    # create_all() can't handle.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ"))

    from app.database.security_setup import ensure_security_setup

    ensure_security_setup(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
