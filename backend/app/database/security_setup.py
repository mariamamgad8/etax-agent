"""
Sets up the ownership-aware security layer on top of the `tax` schema:
- an unprivileged `app_agent` Postgres login role
- four secure views, split by grain (see below)
- row-level security policies on tax.company_owners/transactions/items

--- Why four views instead of two ---
The original two views (v_majority_companies / v_minority_companies) joined
companies -> transactions -> items in one row, so a company with N items
across its transactions produced N duplicate rows of the same `sales`/
`taxes` value — SUM(sales) on that join silently overcounts. Splitting by
grain fixes this at the schema level rather than trusting every generated
query to GROUP BY / DISTINCT correctly:
- v_my_companies: ownership-grain, ANY access level (majority or minority)
  — company_id/name/activity/taxpayer info/share/access_level only, never
  sales/taxes/items. Safe to query regardless of tier, since it's the
  taxpayer's own ownership record, not transaction data.
- v_majority_transactions: transaction-grain, majority-owned companies only.
- v_majority_items: item-grain, majority-owned companies only.
- v_minority_transactions: transaction-grain, minority-owned companies only
  — taxes but never sales (unchanged from the original minority restriction).
There is deliberately no v_minority_items — items stay majority-only by the
view simply not existing for minority access, the same "physically absent,
not filtered" principle the old minority view already used for its columns.

Called from app.database.db.init_db() on every startup — every statement
here is written to be safely re-runnable (CREATE ... IF NOT EXISTS / CREATE
OR REPLACE / DROP POLICY IF EXISTS before CREATE POLICY), matching this
repo's existing "no versioned migration tool, create_all()-style idempotent
setup" convention (see CLAUDE.md).

--- Why the views MUST be `security_invoker = true` (verified live, not
assumed) ---
The role that owns these views (whatever DATABASE_URL connects as, e.g.
`etax`) is a Postgres superuser — it's the POSTGRES_USER bootstrap role from
docker-compose. Superusers always bypass row-level security. A plain view
(the default, "security definer"-like behavior for permission checks) run by
an unprivileged querying role still has its underlying table access checked
against the OWNER's privileges — which means RLS on the underlying tables
would be silently bypassed entirely, because from Postgres's perspective the
owner (a superuser) is doing the reading. Confirmed with a throwaway
experiment: a plain view over an RLS-protected table returned ALL rows
regardless of the row security policy, while the same view created WITH
(security_invoker = true) correctly returned only the querying role's own
rows. So both views here are security_invoker — this is what makes them
"secure views" rather than an accidental RLS bypass hatch.

--- Why app_agent still needs SELECT on the base tax.* tables ---
security_invoker views check the QUERYING role's own table privileges, not
the owner's — confirmed live: revoking app_agent's SELECT on the underlying
table made the view raise "permission denied" instead of silently working
via the owner's grant. So app_agent does hold SELECT on tax.taxpayers/
companies/company_owners/transactions/items. This is NOT the same as "the
application can freely query those tables" — nothing in this codebase ever
sends unvalidated SQL to Postgres. The real access-control boundary is
app/chat/services/sql_runner.py's AST validator, which only ever allows
LLM-generated SQL to reference the views above, never the base tables
directly or the auth schema. The base-table SELECT grants combined with
FORCE ROW LEVEL SECURITY on company_owners/transactions/items exist purely
as a second, independent backstop: even a bug in that Python validator could
only ever surface rows the querying user has *some* ownership relationship
with — RLS restricts rows, the views restrict columns (physically omitting
sales/item_price/quantity from the minority view), and between the two,
neither layer alone has to be perfect.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import APP_AGENT_DB_PASSWORD, APP_AGENT_DB_USER

logger = logging.getLogger(__name__)

# Bind parameters can't be used inside a DO $$ ... $$ block's dollar-quoted
# body (it's just a string literal to the outer parser, not a parameter
# position), so role existence is checked in Python and CREATE/ALTER ROLE
# run as plain parameterized statements instead — confirmed live that a
# direct (non-DO-block) CREATE ROLE ... PASSWORD :password works correctly
# with SQLAlchemy/psycopg2 bind params; that's what's used below.
_ROLE_EXISTS = "SELECT 1 FROM pg_roles WHERE rolname = :role_name"
_CREATE_ROLE = (
    f"CREATE ROLE {APP_AGENT_DB_USER} LOGIN PASSWORD :password "
    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
)
# Re-applied every startup so a changed APP_AGENT_DB_PASSWORD env var takes
# effect on an already-created role, not just on first creation.
_SET_ROLE_PASSWORD = f"ALTER ROLE {APP_AGENT_DB_USER} WITH PASSWORD :password"

_VIEW_NAMES = ["v_my_companies", "v_majority_transactions", "v_majority_items", "v_minority_transactions"]

# The old two views had a different column shape than the four replacing
# them — CREATE OR REPLACE VIEW can only ever append trailing columns to an
# existing view, never remove/reorder them, so the old ones must be dropped
# first. Safe/idempotent either way: a fresh database has nothing to drop.
_DROP_OLD_VIEWS = "DROP VIEW IF EXISTS tax.v_majority_companies, tax.v_minority_companies CASCADE"

_GRANTS = [
    f"GRANT CONNECT ON DATABASE etax TO {APP_AGENT_DB_USER}",
    f"GRANT USAGE ON SCHEMA tax TO {APP_AGENT_DB_USER}",
    # Required for the security_invoker views below to work at all (see
    # module docstring) — the real access boundary is the Python SQL
    # validator plus RLS, not the absence of these grants.
    f"GRANT SELECT ON tax.taxpayers, tax.companies, tax.company_owners, "
    f"tax.transactions, tax.items TO {APP_AGENT_DB_USER}",
    f"GRANT SELECT ON {', '.join(f'tax.{v}' for v in _VIEW_NAMES)} TO {APP_AGENT_DB_USER}",
    # Defense in depth: app_agent must never see the auth schema (never
    # granted USAGE there — this alone blocks it) or the legacy orphaned
    # public.users/public.face_profiles tables from before the auth schema
    # migration, which still hold real password hashes.
    f"REVOKE ALL ON SCHEMA public FROM {APP_AGENT_DB_USER}",
    f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_AGENT_DB_USER}",
]

# Ownership-grain, ANY access level — company identity/activity/taxpayer
# info/share/access_level only, never a transaction or item column. Safe
# regardless of majority/minority since it's the taxpayer's own ownership
# record, not business data. This is what lets "my shares in Bright Future
# AND City Medical" (one majority, one minority) be answered from a SINGLE
# view instead of a UNION across two differently-shaped ones.
_MY_COMPANIES_VIEW = """
CREATE OR REPLACE VIEW tax.v_my_companies WITH (security_invoker = true) AS
SELECT
    c.id AS company_id,
    c.name AS company_name,
    c.activity AS company_activity,
    tp.id AS taxpayer_id,
    tp.name AS taxpayer_name,
    tp.phone_number,
    co.share,
    CASE WHEN co.share > 0.5 THEN 'majority' ELSE 'minority' END AS access_level
FROM tax.company_owners co
JOIN tax.companies c ON c.id = co.company_id
JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
WHERE tp.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
"""

# Transaction-grain, majority-owned companies only. No items join — a
# company with many items no longer produces duplicate transaction rows.
_MAJORITY_TRANSACTIONS_VIEW = """
CREATE OR REPLACE VIEW tax.v_majority_transactions WITH (security_invoker = true) AS
SELECT
    c.id AS company_id,
    c.name AS company_name,
    t.id AS transaction_id,
    t.sales,
    t.taxes
FROM tax.company_owners co
JOIN tax.companies c ON c.id = co.company_id
JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
JOIN tax.transactions t ON t.company_id = c.id
WHERE tp.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
  AND co.share > 0.5
"""

# Item-grain, majority-owned companies only — the only view items ever
# appear in at all; minority ownership never sees an item row, period.
_MAJORITY_ITEMS_VIEW = """
CREATE OR REPLACE VIEW tax.v_majority_items WITH (security_invoker = true) AS
SELECT
    c.id AS company_id,
    c.name AS company_name,
    t.id AS transaction_id,
    i.item_id,
    i.item_price,
    i.quantity
FROM tax.company_owners co
JOIN tax.companies c ON c.id = co.company_id
JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
JOIN tax.transactions t ON t.company_id = c.id
JOIN tax.items i ON i.invoice_id = t.id
WHERE tp.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
  AND co.share > 0.5
"""

# Transaction-grain, minority-owned companies only — taxes but never sales,
# unchanged from the original minority restriction; still no items at all.
_MINORITY_TRANSACTIONS_VIEW = """
CREATE OR REPLACE VIEW tax.v_minority_transactions WITH (security_invoker = true) AS
SELECT
    c.id AS company_id,
    c.name AS company_name,
    t.id AS transaction_id,
    t.taxes
FROM tax.company_owners co
JOIN tax.companies c ON c.id = co.company_id
JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
JOIN tax.transactions t ON t.company_id = c.id
WHERE tp.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
  AND co.share <= 0.5
"""

_VIEWS = [_MY_COMPANIES_VIEW, _MAJORITY_TRANSACTIONS_VIEW, _MAJORITY_ITEMS_VIEW, _MINORITY_TRANSACTIONS_VIEW]

# (table, policy_name, using_expression) — FOR SELECT only; this app never
# needs app_agent to write through these tables.
_RLS_POLICIES = [
    (
        "tax.company_owners",
        "company_owners_own_rows",
        """taxpayer_id IN (
            SELECT id FROM tax.taxpayers
            WHERE user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )""",
    ),
    (
        "tax.transactions",
        "transactions_owned_company",
        """company_id IN (
            SELECT co.company_id FROM tax.company_owners co
            JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
            WHERE tp.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )""",
    ),
    (
        "tax.items",
        "items_owned_company",
        """invoice_id IN (
            SELECT t.id FROM tax.transactions t
            JOIN tax.company_owners co ON co.company_id = t.company_id
            JOIN tax.taxpayers tp ON tp.id = co.taxpayer_id
            WHERE tp.user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )""",
    ),
]


def ensure_security_setup(engine: Engine) -> None:
    with engine.begin() as conn:
        role_exists = conn.execute(text(_ROLE_EXISTS), {"role_name": APP_AGENT_DB_USER}).first() is not None
        if not role_exists:
            conn.execute(text(_CREATE_ROLE), {"password": APP_AGENT_DB_PASSWORD})
        conn.execute(text(_SET_ROLE_PASSWORD), {"password": APP_AGENT_DB_PASSWORD})

        # Views must exist before granting SELECT on them. Old two-view
        # shape dropped first — see _DROP_OLD_VIEWS.
        conn.execute(text(_DROP_OLD_VIEWS))
        for view_ddl in _VIEWS:
            conn.execute(text(view_ddl))

        for stmt in _GRANTS:
            conn.execute(text(stmt))

        for table, policy_name, using_expr in _RLS_POLICIES:
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            conn.execute(text(f"DROP POLICY IF EXISTS {policy_name} ON {table}"))
            conn.execute(
                text(f"CREATE POLICY {policy_name} ON {table} FOR SELECT USING ({using_expr})")
            )

    logger.info("[STARTUP] app_agent role, secure tax views, and RLS policies are in place")
