"""
SQLDatabaseChain experiment for the database_query branch — explicitly a
prototype step per the project roadmap, not the final architecture.

Live-tested (originally against the SQLite demo DB, now repointed at the
Postgres `tax` schema — see below) across several question shapes and found
too unreliable to wire into the actual graph: SQLDatabaseChain builds a
raw-completion-style prompt ("...Question: <q>\\nSQLQuery:") and asks the
chat model to continue it, which is not what chat-tuned models (like Groq's)
are trained to do reliably. Confirmed failure modes, same query/model/prompt
across separate runs:
  - "How much tax did taxpayer 1002 pay in 2025?" -> model returned a
    genuinely empty completion for the SQL, deterministically.
  - use_query_checker=True's self-correction follow-up call returned a
    conversational non-answer ("I'm ready to review the query, but I need
    the SQL statement first...") instead of corrected SQL, which then failed
    as SQL itself.
  - llama-3.3-70b-versatile additionally wrapped SQL in ```sql fences
    regardless of an explicit prompt instruction not to.
"How many taxpayers are in Cairo?" and "Show me all Cairo taxpayers." DID
work correctly. This isn't a config mistake — this specific approach is
just genuinely inconsistent with these providers, which is exactly the
concern the project roadmap raised about trusting this chain. Kept here as
the documented experiment (ask_database); the graph's live database_query
branch uses generate_and_run_sql below instead — same idea (LLM writes SQL,
Python executes it) but through call_llm_text's chat-style prompting, which
has been reliable for every other LLM task in this project. That function
is a deliberately minimal stand-in for the roadmap's controlled SQL
subgraph (no repair loop, no schema-inspection step yet) — enough to wire
the UI end-to-end now, not the final architecture either.

One safety measure applies to both: the connection used to execute generated
SQL is opened with the `postgresql_readonly` execution option (backed by
psycopg2's `connection.readonly`), so even a write statement that slipped
past the SELECT-only/keyword checks would be rejected at the database level
rather than mutate data — this replaces the old SQLite read-only-file-mode
equivalent now that the demo tax data lives in Postgres's `tax` schema
instead of a separate SQLite file.

*** NOT OWNERSHIP-AWARE — DO NOT WIRE THIS INTO THE LIVE GRAPH ***
Neither `ask_database` nor `generate_and_run_sql` in this module know
anything about which taxpayer/company an authenticated user is allowed to
see — they execute against the full `tax` schema via the table-owning
Postgres connection (`app.database.db.engine`), which also bypasses row-level
security entirely (that role is a superuser). The live `database_query`
graph node calls `app.chat.services.sql_runner.handle_user_database_query`
instead, which determines per-company majority/minority access from
`tax.company_owners`, restricts the LLM to the matching secure view(s), and
executes via the unprivileged `app_agent` role with RLS enforced. These
functions stay here only as the documented SQLDatabaseChain experiment.
"""
import logging
import re

from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import PromptTemplate
from langchain_experimental.sql import SQLDatabaseChain
from langchain_groq import ChatGroq
from sqlalchemy import text

from app.chat.config import GROQ_API_KEY, SQL_CHAIN_MODEL
from app.chat.db.sql_utils import clean_sql
from app.chat.providers.llm import call_llm_text
from app.database.db import engine
from app.database.tax_models import TAX_SCHEMA

logger = logging.getLogger(__name__)

_TAX_TABLES = ["taxpayers", "companies", "company_owners", "transactions", "items"]

# Same as the library's default SQLite prompt, plus one line forbidding
# markdown fences — SQL_CHAIN_MODEL's default (openai/gpt-oss-20b) respects
# this; llama-3.3-70b-versatile ignored it and wrapped SQL in ```sql fences
# that broke execution regardless, see app.chat.config.
_PROMPT_TEMPLATE = """Given an input question, first create a syntactically correct {dialect} query to run, then look at the results of the query and return the answer. Unless the user specifies in his question a specific number of examples he wishes to obtain, always limit your query to at most {top_k} results. You can order the results by a relevant column to return the most interesting examples in the database.

Never query for all the columns from a specific table, only ask for a few relevant columns given the question.

Pay attention to use only the column names that you can see in the schema description. Be careful to not query for columns that do not exist. Also, pay attention to which column is in which table.

Never wrap the SQL query in markdown code fences, backticks, or any other formatting — output it as plain text only, with no ``` anywhere in the response.

Use the following format:

Question: Question here
SQLQuery: SQL Query to run
SQLResult: Result of the SQLQuery
Answer: Final answer here

Only use the following tables:
{table_info}

Question: {input}"""

_PROMPT = PromptTemplate(
    input_variables=["input", "table_info", "dialect", "top_k"],
    template=_PROMPT_TEMPLATE,
)

_db = None
_chain = None


def _get_db() -> SQLDatabase:
    global _db
    if _db is None:
        _db = SQLDatabase(engine, schema=TAX_SCHEMA, include_tables=_TAX_TABLES)
    return _db


def _get_chain() -> SQLDatabaseChain:
    global _chain
    if _chain is None:
        llm = ChatGroq(model=SQL_CHAIN_MODEL, api_key=GROQ_API_KEY, temperature=0)
        _chain = SQLDatabaseChain.from_llm(
            llm=llm,
            db=_get_db(),
            prompt=_PROMPT,
            verbose=False,
            return_intermediate_steps=True,
            # use_query_checker=True adds a second LLM call to self-correct
            # the SQL, but that call sometimes returns a conversational
            # non-answer instead of corrected SQL ("I'm ready to review the
            # query, but I need..."), which then fails as SQL itself —
            # confirmed live, deterministic per-query. The model already
            # generates correct SQL directly without it in every test case.
            use_query_checker=False,
        )
    return _chain


def ask_database(question_en: str) -> dict:
    """
    Runs `question_en` (an English question about the schema) through the
    chain. Returns {"sql": str | None, "columns": list[str] | None,
    "rows": list[dict] | None, "answer": str, "error": str | None}.
    """
    try:
        result = _get_chain().invoke({"query": question_en})
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as sql_error
        return {"sql": None, "columns": None, "rows": None, "answer": "", "error": str(exc)}

    answer = result.get("result", "")
    sql = None
    columns = None
    rows = None

    for step in result.get("intermediate_steps", []):
        if isinstance(step, dict) and "sql_cmd" in step:
            sql = step["sql_cmd"].strip()

    if sql:
        try:
            columns, rows = _execute_readonly(sql)
        except Exception:  # noqa: BLE001 - fine to fall back to the chain's own text answer
            columns, rows = None, None

    return {"sql": sql, "columns": columns, "rows": rows, "answer": answer, "error": None}


def _execute_readonly(sql: str):
    """Re-runs the given SQL ourselves to get clean structured rows for the UI."""
    if not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT statements are re-executed for structured results.")
    with engine.connect().execution_options(postgresql_readonly=True) as conn:
        # Lets the LLM write unqualified table names (FROM taxpayers) and
        # still resolve correctly, rather than depending on it reliably
        # schema-qualifying every reference on its own.
        conn.execute(text(f"SET search_path TO {TAX_SCHEMA}, public"))
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return columns, rows


# --- Hand-rolled alternative to the chain above — NOT what the live graph
# calls (see module docstring); superseded by app.chat.services.sql_runner ---

_FORBIDDEN_SQL_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|REPLACE|VACUUM|TRUNCATE|GRANT|REVOKE|COPY)\b",
    re.IGNORECASE,
)


def _sql_generation_prompt() -> str:
    return f"""You write a single PostgreSQL SELECT query to answer a question about this schema (schema name: {TAX_SCHEMA}):

{_get_db().get_table_info()}

Rules:
- Output ONLY the raw SQL statement — no markdown code fences, no backticks, no explanation, no "SQLQuery:" label.
- Exactly one SELECT statement. Never write INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, or COPY.
- Only use the columns and tables shown above. Never invent a column or table name.
- Add "LIMIT 20" unless the question asks for a count, sum, average, or other single aggregate value.
"""


def generate_and_run_sql(question_en: str) -> dict:
    """
    LLM writes SQL via call_llm_text (chat-style prompting — reliable across
    this project, unlike SQLDatabaseChain's completion-style prompt), Python
    validates it's a single SELECT statement, then it's executed against a
    read-only connection. Returns {"sql", "columns", "rows", "error"}.
    """
    logger.info("[SQL] question (en): %s", question_en)
    try:
        raw = call_llm_text(_sql_generation_prompt(), question_en)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SQL] generation failed: %s", exc)
        return {"sql": None, "columns": None, "rows": None, "error": f"Could not generate a query: {exc}"}

    sql = clean_sql(raw)
    logger.info("[SQL] generated query: %s", sql)

    if not sql.lower().startswith("select"):
        logger.warning("[SQL] rejected — not a SELECT statement: %s", sql)
        return {"sql": sql, "columns": None, "rows": None, "error": "Generated statement was not a SELECT query."}
    if ";" in sql:
        logger.warning("[SQL] rejected — multiple statements: %s", sql)
        return {"sql": sql, "columns": None, "rows": None, "error": "Only a single SQL statement is allowed."}
    if _FORBIDDEN_SQL_KEYWORDS.search(sql):
        logger.warning("[SQL] rejected — forbidden keyword: %s", sql)
        return {"sql": sql, "columns": None, "rows": None, "error": "Generated statement contained a disallowed keyword."}

    try:
        columns, rows = _execute_readonly(sql)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[SQL] execution failed: %s", exc)
        return {"sql": sql, "columns": None, "rows": None, "error": str(exc)}

    logger.info("[SQL] executed OK — %d columns, %d rows", len(columns), len(rows))
    return {"sql": sql, "columns": columns, "rows": rows, "error": None}
