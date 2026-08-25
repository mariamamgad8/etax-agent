"""
A separate SQLAlchemy engine authenticated as the unprivileged `app_agent`
Postgres role (see security_setup.py), distinct from the table-owning
`engine` in db.py. Only app/chat/services/sql_runner.py should execute
LLM-generated SQL through this engine — everything else in the app (auth,
face profiles, seeding, migrations) keeps using the owner-role engine.

This is what makes the ownership/RLS security model real rather than
advisory: app_agent has no grants beyond SELECT on tax.* (needed for the
security-invoker views to function — see security_setup.py's module
docstring) and no access to auth.* at all, so even a bug in the Python-side
SQL validator can't turn into unrestricted data access — Postgres itself
still enforces it.
"""
from sqlalchemy import create_engine

from app.config import APP_AGENT_DATABASE_URL

agent_engine = create_engine(APP_AGENT_DATABASE_URL, future=True)
