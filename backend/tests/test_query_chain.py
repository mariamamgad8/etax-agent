"""
Covers the database_query branch's move off SQLite: execution now goes
through the shared Postgres engine (app.database.db.engine), enforced
read-only via the postgresql_readonly execution option, with the tax schema
resolved via SET search_path rather than requiring the LLM to always
schema-qualify table names correctly.
"""
import pytest
from sqlalchemy import text

from app.chat.db import query_chain
from app.database.db import engine


def test_execute_readonly_resolves_unqualified_table_names_via_search_path():
    """The LLM may write `FROM companies` without the `tax.` prefix — search_path must still resolve it."""
    columns, rows = query_chain._execute_readonly("SELECT COUNT(*) AS n FROM companies")
    assert columns == ["n"]
    assert rows[0]["n"] >= 0


def test_execute_readonly_rejects_non_select():
    with pytest.raises(ValueError):
        query_chain._execute_readonly("UPDATE companies SET name = name")


def test_read_only_connection_blocks_writes_at_the_database_level():
    """
    Defense-in-depth: even a write that slipped past the app-level SELECT-only
    check must still be rejected by Postgres itself, replacing the old SQLite
    read-only-file-mode guarantee.
    """
    with pytest.raises(Exception) as exc_info:
        with engine.connect().execution_options(postgresql_readonly=True) as conn:
            conn.execute(text("UPDATE tax.companies SET name = name"))
    assert "read-only" in str(exc_info.value).lower()


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE tax.companies",
        "DELETE FROM tax.companies",
        "TRUNCATE tax.companies",
        "GRANT ALL ON tax.companies TO public",
    ],
)
def test_forbidden_sql_keywords_cover_destructive_statements(sql):
    assert query_chain._FORBIDDEN_SQL_KEYWORDS.search(sql) is not None


def test_generate_and_run_sql_rejects_llm_output_that_is_not_select(monkeypatch):
    monkeypatch.setattr(query_chain, "call_llm_text", lambda system, user: "DELETE FROM tax.companies")
    result = query_chain.generate_and_run_sql("delete everything")
    assert result["error"] is not None
    assert result["rows"] is None


def test_generate_and_run_sql_happy_path_against_seeded_data(db):
    """One live LLM call — confirms the whole generate -> validate -> execute path works against Postgres."""
    from app.chat.db.seed import seed

    seed(db)
    result = query_chain.generate_and_run_sql("How many companies are there in total?")
    assert result["error"] is None
    assert result["rows"] is not None
    assert len(result["rows"]) >= 1
