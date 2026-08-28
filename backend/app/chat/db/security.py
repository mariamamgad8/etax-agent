"""
Determines what tax-schema data an authenticated user is allowed to see,
straight from tax.company_owners — never from a company_id/taxpayer_id/share
claim supplied by the LLM or the user's own message text. Permissions are
per company, not a single global tier: the same user can hold majority in
one company and minority in another simultaneously, and both must be
represented, never collapsed into one flag.
"""
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

_OWNERSHIP_QUERY = """
SELECT co.company_id, co.share
FROM tax.company_owners co
JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
WHERE tp.user_id = :user_id
"""


def get_user_ownership_status(db_conn: Connection, user_id: uuid.UUID) -> dict:
    """
    Returns {
        "has_ownership": bool,
        "majority_company_ids": list[int],   # share > 0.5
        "minority_company_ids": list[int],   # share <= 0.5
    }
    """
    rows = db_conn.execute(text(_OWNERSHIP_QUERY), {"user_id": str(user_id)}).fetchall()

    majority_ids = [row.company_id for row in rows if row.share > 0.5]
    minority_ids = [row.company_id for row in rows if row.share <= 0.5]

    return {
        "has_ownership": bool(rows),
        "majority_company_ids": majority_ids,
        "minority_company_ids": minority_ids,
    }


_FRAUD_STATUS_QUERY = "SELECT review_status FROM tax.fraud_records WHERE user_id = :user_id"


def get_user_fraud_status(db_conn: Connection, user_id: uuid.UUID) -> str | None:
    """
    review_status of the user's linked tax.fraud_records row, or None if
    they have no linked record. Independent of tax.taxpayers/company_owners
    — see FraudRecord's docstring: this is a separate, direct user_id link,
    not tied to ownership tier at all.
    """
    row = db_conn.execute(text(_FRAUD_STATUS_QUERY), {"user_id": str(user_id)}).first()
    return row.review_status if row else None


_BUSINESS_CONTEXT_QUERY = """
SELECT
    tp.id AS taxpayer_id,
    tp.name AS taxpayer_name,
    c.id AS company_id,
    c.name AS company_name,
    c.activity AS company_activity,
    co.share
FROM tax.taxpayers tp
LEFT JOIN tax.company_owners co ON co.taxpayer_id = tp.id
LEFT JOIN tax.companies c ON c.id = co.company_id
WHERE tp.user_id = :user_id
"""


def get_user_business_context(db_conn: Connection, user_id: uuid.UUID) -> dict:
    """
    Everything the SQL-generation pipeline is allowed to know about the
    authenticated user's own tax identity and ownership, loaded straight
    from Postgres — the entity-resolution/authorization-before-SQL steps in
    services/query_planning.py work against exactly this, never against a
    company_id/name/share the LLM or the user's message text asserts.

    Returns {
        "taxpayer_id": int | None,
        "taxpayer_name": str | None,
        "companies": [
            {"company_id": int, "company_name": str, "company_activity": str | None,
             "share": float, "access_level": "majority" | "minority"},
            ...
        ],
        "fraud_review_status": str | None,   # see get_user_fraud_status — independent of ownership
    }
    A taxpayer with no company_owners rows at all gets an empty "companies"
    list (the LEFT JOINs still return the taxpayer's own row with NULL
    company columns, filtered out below) rather than no row at all.
    """
    rows = db_conn.execute(text(_BUSINESS_CONTEXT_QUERY), {"user_id": str(user_id)}).fetchall()
    fraud_review_status = get_user_fraud_status(db_conn, user_id)

    if not rows:
        return {
            "taxpayer_id": None,
            "taxpayer_name": None,
            "companies": [],
            "fraud_review_status": fraud_review_status,
        }

    taxpayer_id = rows[0].taxpayer_id
    taxpayer_name = rows[0].taxpayer_name
    companies = [
        {
            "company_id": row.company_id,
            "company_name": row.company_name,
            "company_activity": row.company_activity,
            "share": float(row.share),
            "access_level": "majority" if row.share > 0.5 else "minority",
        }
        for row in rows
        if row.company_id is not None
    ]

    return {
        "taxpayer_id": taxpayer_id,
        "taxpayer_name": taxpayer_name,
        "companies": companies,
        "fraud_review_status": fraud_review_status,
    }
