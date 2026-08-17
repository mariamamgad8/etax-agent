"""
Deterministic synthetic data generator for the demo tax database. Reuses the
same categorical options as the fraud model (fraud/schema.py) so a taxpayer's
business_type/region/industry_risk here line up with what the fraud form
would show for the same kind of business.

Taxpayer IDs deliberately start at 1000 (not 1) so the examples used
throughout the project spec ("taxpayer 1002") resolve to real seeded rows.
"""
import random
from datetime import date, timedelta

from app.chat.fraud.schema import BUSINESS_TYPE_OPTIONS, INDUSTRY_RISK_OPTIONS, REGION_OPTIONS

_SEED = 20260817  # fixed seed: same synthetic data on every fresh build
_FIRST_TAXPAYER_ID = 1000
_TAXPAYER_COUNT = 60
_TAX_YEARS = [2022, 2023, 2024, 2025]
_STATUSES = ["Active", "Active", "Active", "Inactive", "Suspended"]

_NAME_TEMPLATES = [
    "{type} House", "{type} Group", "{region} {type} Co.", "Nile {type}",
    "{type} Solutions", "{region} {type} Trading", "Delta {type}",
    "{type} & Partners", "{region} {type} Ltd.", "Modern {type}",
]


def _generate_name(rng: random.Random, business_type: str, region: str) -> str:
    template = rng.choice(_NAME_TEMPLATES)
    return template.format(type=business_type, region=region)


def _generate_taxpayer(rng: random.Random, taxpayer_id: int) -> dict:
    business_type = rng.choice(BUSINESS_TYPE_OPTIONS)
    region = rng.choice(REGION_OPTIONS)
    registered = date(2026, 8, 17) - timedelta(days=rng.randint(200, 4000))
    return {
        "taxpayer_id": taxpayer_id,
        "taxpayer_name": _generate_name(rng, business_type, region),
        "business_type": business_type,
        "region": region,
        "industry_risk": rng.choice(INDUSTRY_RISK_OPTIONS),
        "registration_date": registered.isoformat(),
        "status": rng.choice(_STATUSES),
    }


def _generate_tax_return(rng: random.Random, taxpayer_id: int, tax_year: int) -> dict:
    revenue = round(rng.uniform(200_000, 12_000_000), 2)
    expenses = round(revenue * rng.uniform(0.45, 0.85), 2)
    taxable_income = round(revenue - expenses, 2)
    expected_tax = round(taxable_income * rng.uniform(0.18, 0.25), 2)

    # ~1 in 5 returns under-declare noticeably, so "declared < expected"
    # queries and the fraud narrative have real rows to find.
    if rng.random() < 0.2:
        declared_tax = round(expected_tax * rng.uniform(0.5, 0.85), 2)
    else:
        declared_tax = round(expected_tax * rng.uniform(0.92, 1.0), 2)

    late_payment = 1 if rng.random() < 0.15 else 0
    tax_paid = declared_tax if not late_payment else round(declared_tax * rng.uniform(0.6, 0.95), 2)

    vat_collected = round(revenue * rng.uniform(0.10, 0.14), 2)
    vat_paid = round(vat_collected * rng.uniform(0.85, 1.0), 2)

    filing_date = date(tax_year + 1, rng.randint(1, 4), rng.randint(1, 28))

    return {
        "taxpayer_id": taxpayer_id,
        "tax_year": tax_year,
        "annual_revenue": revenue,
        "annual_expenses": expenses,
        "taxable_income": taxable_income,
        "expected_tax": expected_tax,
        "declared_tax": declared_tax,
        "tax_paid": tax_paid,
        "vat_collected": vat_collected,
        "vat_paid": vat_paid,
        "filing_date": filing_date.isoformat(),
        "late_payment": late_payment,
    }


def is_seeded(conn) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM taxpayers").fetchone()
    return row[0] > 0


def seed(conn) -> None:
    """Idempotent: no-ops if the demo DB already has data."""
    if is_seeded(conn):
        return

    rng = random.Random(_SEED)
    taxpayer_rows = []
    return_rows = []

    for i in range(_TAXPAYER_COUNT):
        taxpayer_id = _FIRST_TAXPAYER_ID + i
        taxpayer_rows.append(_generate_taxpayer(rng, taxpayer_id))
        for tax_year in rng.sample(_TAX_YEARS, k=rng.randint(2, len(_TAX_YEARS))):
            return_rows.append(_generate_tax_return(rng, taxpayer_id, tax_year))

    conn.executemany(
        """INSERT INTO taxpayers
           (taxpayer_id, taxpayer_name, business_type, region, industry_risk, registration_date, status)
           VALUES (:taxpayer_id, :taxpayer_name, :business_type, :region, :industry_risk, :registration_date, :status)""",
        taxpayer_rows,
    )
    conn.executemany(
        """INSERT INTO tax_returns
           (taxpayer_id, tax_year, annual_revenue, annual_expenses, taxable_income, expected_tax,
            declared_tax, tax_paid, vat_collected, vat_paid, filing_date, late_payment)
           VALUES (:taxpayer_id, :tax_year, :annual_revenue, :annual_expenses, :taxable_income, :expected_tax,
                   :declared_tax, :tax_paid, :vat_collected, :vat_paid, :filing_date, :late_payment)""",
        return_rows,
    )
    conn.commit()
