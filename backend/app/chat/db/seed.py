"""
Loads the example dataset for the `tax` schema, used to exercise the
chatbot's database_query intent in development. Each section below is
idempotent on its OWN existence check (not one global gate) — this is
deliberate: an earlier version of this module only seeded companies/
transactions/items, gated by a single is_seeded() check on tax.companies;
when taxpayers/company_owners/demo accounts were added later, they silently
never ran on an already-seeded database, since the single gate short-
circuited before reaching them. Per-section gating means new seed data added
in the future will actually run on next startup, even on a database that
already has companies.

This is intentionally the literal sample dataset supplied for this purpose
(and the taxpayer/ownership story from the project's own ER-diagram
reference), not invented/generated business records; real seed/import data
replaces this separately.
"""
import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.database.db import SessionLocal
from app.database.models import FaceProfile, User
from app.database.tax_models import Company, CompanyOwner, Item, Taxpayer, Transaction

logger = logging.getLogger(__name__)

_COMPANIES = [
    (1, "Bright Future Academy", "educational"),
    (2, "GlobalBuild Corp", "construction"),
    (3, "City Medical Center", "medical"),
]

_TRANSACTIONS = [
    (1, 1, "1000.00", "150.00"),
    (2, 1, "2500.00", "375.00"),
    (3, 2, "500.00", "75.00"),
    (4, 2, "12000.00", "1800.00"),
    (5, 3, "3000.00", "450.00"),
]

_ITEMS = [
    (1, 101, "500.00", 2),
    (2, 102, "2500.00", 1),
    (3, 103, "125.00", 4),
    (4, 104, "3000.00", 4),
    (5, 105, "1000.00", 3),
]

_TAXPAYERS = [
    (1, "Ahmed Ali", "010-111-1111"),
    (2, "Sara Mohamed", "010-222-2222"),
    (3, "Omar Hassan", "010-333-3333"),
]

# (company_id, taxpayer_id, share) — Ahmed 60% / Sara 40% of Bright Future,
# Omar 100% of GlobalBuild, Sara 70% / Ahmed 30% of City Medical.
_COMPANY_OWNERS = [
    (1, 1, "0.60"),
    (1, 2, "0.40"),
    (2, 3, "1.00"),
    (3, 2, "0.70"),
    (3, 1, "0.30"),
]

# Demo login accounts for the seeded taxpayers above, so the ownership-aware
# database_query flow (majority/minority/mixed) can be exercised end-to-end
# through the real signup/face flow — never because a user is allowed to
# self-declare ownership at signup (see CLAUDE.md's "Ownership-aware SQL
# security": share is never user-asserted). Deliberately simple/uniform
# credentials since these are dev-only demo accounts, not real ones.
# (taxpayer_id, full_name, username, email, password)
_DEMO_ACCOUNTS = [
    (1, "Ahmed Ali", "ahmed", "ahmed@example.com", "password123"),
    (2, "Sara Mohamed", "sara", "sara@example.com", "password123"),
    (3, "Omar Hassan", "omar", "omar@example.com", "password123"),
]


def is_seeded(db: Session) -> bool:
    return db.execute(select(Company.id).limit(1)).first() is not None


def _seed_companies_transactions_items(db: Session) -> None:
    if is_seeded(db):
        return

    db.add_all(Company(id=i, name=name, activity=activity) for i, name, activity in _COMPANIES)
    db.flush()
    db.add_all(
        Transaction(id=i, company_id=company_id, sales=sales, taxes=taxes)
        for i, company_id, sales, taxes in _TRANSACTIONS
    )
    db.flush()
    db.add_all(
        Item(invoice_id=invoice_id, item_id=item_id, item_price=item_price, quantity=quantity)
        for invoice_id, item_id, item_price, quantity in _ITEMS
    )
    db.flush()

    # Explicit ids above don't advance the SERIAL sequences backing them —
    # without this, the next auto-generated id collides with one already
    # used here (confirmed live: a later plain INSERT INTO tax.companies
    # (name, activity) VALUES (...) failed with a duplicate-key error on
    # id=3). Mirrors the setval() calls in the reference seeding script this
    # dataset was supplied from.
    db.execute(text("SELECT setval('tax.companies_id_seq', (SELECT MAX(id) FROM tax.companies))"))
    db.execute(text("SELECT setval('tax.transactions_id_seq', (SELECT MAX(id) FROM tax.transactions))"))
    db.commit()


def _seed_taxpayers_and_ownership(db: Session) -> None:
    if db.execute(select(Taxpayer.id).limit(1)).first() is None:
        db.add_all(Taxpayer(id=i, name=name, phone_number=phone) for i, name, phone in _TAXPAYERS)
        db.flush()
        db.execute(text("SELECT setval('tax.taxpayers_id_seq', (SELECT MAX(id) FROM tax.taxpayers))"))
        db.commit()

    if db.execute(select(CompanyOwner.company_id).limit(1)).first() is None:
        db.add_all(
            CompanyOwner(company_id=company_id, taxpayer_id=taxpayer_id, share=share)
            for company_id, taxpayer_id, share in _COMPANY_OWNERS
        )
        db.commit()


def _seed_demo_accounts(db: Session) -> None:
    """
    Creates a login account for each seeded taxpayer above and links
    taxpayers.user_id, so a real signed-in session (not a raw DB row) can
    exercise the ownership-aware database_query flow. Also duplicates
    whatever face embedding already exists on this database (from a real
    enrollment) onto each new account, so that same real face can complete
    face verification as any of them — this step only has an embedding to
    copy once at least one real user has enrolled here; until then it
    creates the accounts (password-loginable, stage=pending_enrollment) but
    logs that face profiles were skipped, rather than failing.
    """
    first_username = _DEMO_ACCOUNTS[0][2]
    if db.execute(select(User.id).where(User.username == first_username)).first() is not None:
        return

    existing_embedding = db.execute(select(FaceProfile.embedding).limit(1)).scalars().first()
    if existing_embedding is None:
        logger.info(
            "[SEED] no enrolled face exists on this database yet — demo accounts will be "
            "created without a face profile (password login only) until re-seeded later."
        )

    for taxpayer_id, full_name, username, email, password in _DEMO_ACCOUNTS:
        user = User(full_name=full_name, username=username, email=email, password_hash=hash_password(password))
        db.add(user)
        db.flush()

        taxpayer = db.get(Taxpayer, taxpayer_id)
        taxpayer.user_id = user.id

        if existing_embedding is not None:
            db.add(FaceProfile(user_id=user.id, embedding=existing_embedding))

    db.commit()
    logger.info("[SEED] created %d demo accounts linked to seeded taxpayers.", len(_DEMO_ACCOUNTS))


def seed(db: Session) -> None:
    """Idempotent per-section (see module docstring) — safe to call repeatedly."""
    _seed_companies_transactions_items(db)
    _seed_taxpayers_and_ownership(db)
    _seed_demo_accounts(db)


def ensure_ready() -> None:
    """Seeds the tax schema with the example dataset if empty. Safe to call on every startup."""
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
