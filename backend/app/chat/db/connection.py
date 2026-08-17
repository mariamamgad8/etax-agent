import sqlite3
from pathlib import Path

from app.chat.config import DEMO_DB_PATH
from app.chat.db.schema import create_schema
from app.chat.db.seed import seed


def get_connection() -> sqlite3.Connection:
    Path(DEMO_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DEMO_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_ready() -> None:
    """Creates the schema and seeds synthetic data if the demo DB is empty. Safe to call on every startup."""
    conn = get_connection()
    try:
        create_schema(conn)
        seed(conn)
    finally:
        conn.close()
