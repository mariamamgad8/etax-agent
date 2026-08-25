"""Small helpers shared between query_chain.py and services/sql_runner.py."""
import re


def clean_sql(raw_sql: str) -> str:
    """Strips markdown code fences a model may add despite being told not to."""
    raw_sql = raw_sql.strip()
    raw_sql = re.sub(r"^```[a-zA-Z]*\n?", "", raw_sql)
    raw_sql = re.sub(r"\n?```$", "", raw_sql)
    return raw_sql.strip().rstrip(";")
