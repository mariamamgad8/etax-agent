"""
Demo tax database — SQLite, synthetic data, deliberately separate from the
real Postgres auth database (which holds users/face_profiles only). This
exists purely to build and test the database_query branch (SQLDatabaseChain
experiment, then the controlled SQL subgraph) before the real schema is
available from the business team. Schema matches the shape specified in the
project roadmap.
"""

CREATE_TAXPAYERS = """
CREATE TABLE IF NOT EXISTS taxpayers (
    taxpayer_id INTEGER PRIMARY KEY,
    taxpayer_name TEXT NOT NULL,
    business_type TEXT NOT NULL,
    region TEXT NOT NULL,
    industry_risk TEXT NOT NULL,
    registration_date TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

CREATE_TAX_RETURNS = """
CREATE TABLE IF NOT EXISTS tax_returns (
    return_id INTEGER PRIMARY KEY AUTOINCREMENT,
    taxpayer_id INTEGER NOT NULL REFERENCES taxpayers(taxpayer_id),
    tax_year INTEGER NOT NULL,
    annual_revenue REAL NOT NULL,
    annual_expenses REAL NOT NULL,
    taxable_income REAL NOT NULL,
    expected_tax REAL NOT NULL,
    declared_tax REAL NOT NULL,
    tax_paid REAL NOT NULL,
    vat_collected REAL NOT NULL,
    vat_paid REAL NOT NULL,
    filing_date TEXT NOT NULL,
    late_payment INTEGER NOT NULL CHECK (late_payment IN (0, 1))
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_tax_returns_taxpayer_id ON tax_returns(taxpayer_id)",
    "CREATE INDEX IF NOT EXISTS idx_tax_returns_tax_year ON tax_returns(tax_year)",
    "CREATE INDEX IF NOT EXISTS idx_taxpayers_region ON taxpayers(region)",
]


def create_schema(conn) -> None:
    conn.execute(CREATE_TAXPAYERS)
    conn.execute(CREATE_TAX_RETURNS)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    conn.commit()
