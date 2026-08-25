"""
Covers Feature 1 (unify SQLite + Postgres into etax_db with auth/tax
schemas): schema-qualified tables exist, cross-schema FK works, and the
company_owners.share CHECK constraint enforces the 0..1 fraction range.
"""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.database.db import engine
from app.database.tax_models import Company, CompanyOwner, Taxpayer


def test_auth_and_tax_schemas_exist():
    with engine.connect() as conn:
        schemas = {row[0] for row in conn.execute(text("SELECT schema_name FROM information_schema.schemata"))}
    assert {"auth", "tax"} <= schemas


def test_expected_tables_are_schema_qualified():
    inspector = inspect(engine)
    assert set(inspector.get_table_names(schema="auth")) == {"users", "face_profiles"}
    assert set(inspector.get_table_names(schema="tax")) == {
        "taxpayers",
        "companies",
        "company_owners",
        "transactions",
        "items",
    }


def test_taxpayer_user_id_references_auth_users(db):
    """A taxpayer with a bogus user_id must be rejected by the cross-schema FK."""
    bogus_user_id = uuid.uuid4()
    db.add(Taxpayer(name="FK Test Taxpayer", user_id=bogus_user_id))
    with pytest.raises(IntegrityError):
        db.commit()


def test_taxpayer_user_id_is_nullable(db):
    """A taxpayer may exist without an application login."""
    taxpayer = Taxpayer(name="No-login Taxpayer")
    db.add(taxpayer)
    db.commit()
    assert taxpayer.user_id is None
    db.delete(taxpayer)
    db.commit()


@pytest.mark.parametrize("share", [-0.1, 1.5])
def test_company_owner_share_out_of_range_rejected(db, share):
    taxpayer = Taxpayer(name="Share Range Test Taxpayer")
    company = Company(name="Share Range Test Co")
    db.add_all([taxpayer, company])
    db.flush()

    db.add(CompanyOwner(company_id=company.id, taxpayer_id=taxpayer.id, share=share))
    with pytest.raises(IntegrityError):
        db.commit()
    # The failed commit rolls back the whole transaction, including the
    # taxpayer/company inserts flushed above — nothing was actually
    # persisted, so there's nothing left to clean up.
    db.rollback()


def test_company_owner_share_within_range_accepted(db):
    taxpayer = Taxpayer(name="Share OK Test Taxpayer")
    company = Company(name="Share OK Test Co")
    db.add_all([taxpayer, company])
    db.flush()

    db.add(CompanyOwner(company_id=company.id, taxpayer_id=taxpayer.id, share=0.5))
    db.commit()

    db.query(CompanyOwner).filter_by(company_id=company.id, taxpayer_id=taxpayer.id).delete()
    db.delete(taxpayer)
    db.delete(company)
    db.commit()


def test_one_taxpayer_can_own_shares_in_multiple_companies(db):
    """company_owners must be many-to-many, not a single field on either side."""
    taxpayer = Taxpayer(name="Multi-Owner Test Taxpayer")
    company_a = Company(name="Multi-Owner Test Co A")
    company_b = Company(name="Multi-Owner Test Co B")
    db.add_all([taxpayer, company_a, company_b])
    db.flush()

    db.add_all(
        [
            CompanyOwner(company_id=company_a.id, taxpayer_id=taxpayer.id, share=0.3),
            CompanyOwner(company_id=company_b.id, taxpayer_id=taxpayer.id, share=0.6),
        ]
    )
    db.commit()

    count = (
        db.query(CompanyOwner)
        .filter_by(taxpayer_id=taxpayer.id)
        .count()
    )
    assert count == 2

    db.query(CompanyOwner).filter_by(taxpayer_id=taxpayer.id).delete()
    db.delete(taxpayer)
    db.delete(company_a)
    db.delete(company_b)
    db.commit()
