"""
The tax schema's demo/example dataset (backend/app/chat/db/seed.py) must
load exactly once and never duplicate rows on repeated startups. Each
section (companies/transactions/items, taxpayers/ownership, demo accounts)
is idempotent on its own existence check — not one global gate — so these
tests exercise each section independently, not just the top-level seed().
"""
from app.auth.security import verify_password
from app.chat.db.seed import _DEMO_ACCOUNTS, _DEMO_FRAUD_LINKS, is_seeded, seed
from app.database.models import FaceProfile, User
from app.database.tax_models import FRAUD_REVIEW_STATUSES, Company, CompanyOwner, FraudRecord, Taxpayer


def test_seed_is_idempotent(db):
    seed(db)
    assert is_seeded(db)
    count_after_first = db.query(Company).count()

    seed(db)
    count_after_second = db.query(Company).count()

    assert count_after_first == count_after_second


def test_seed_loads_the_supplied_sample_companies(db):
    seed(db)
    names = {c.name for c in db.query(Company).all()}
    assert {"Bright Future Academy", "GlobalBuild Corp", "City Medical Center"} <= names


def test_seed_loads_taxpayers_and_phone_numbers(db):
    seed(db)
    by_name = {t.name: t.phone_number for t in db.query(Taxpayer).all()}
    assert by_name["Ahmed Ali"] == "010-111-1111"
    assert by_name["Sara Mohamed"] == "010-222-2222"
    assert by_name["Omar Hassan"] == "010-333-3333"


def test_seed_loads_exact_company_owner_shares(db):
    seed(db)
    shares = {(co.company_id, co.taxpayer_id): float(co.share) for co in db.query(CompanyOwner).all()}
    assert shares[(1, 1)] == 0.60  # Ahmed owns 60% of Bright Future
    assert shares[(1, 2)] == 0.40  # Sara owns 40% of Bright Future
    assert shares[(2, 3)] == 1.00  # Omar owns 100% of GlobalBuild
    assert shares[(3, 2)] == 0.70  # Sara owns 70% of City Medical
    assert shares[(3, 1)] == 0.30  # Ahmed owns 30% of City Medical


def test_taxpayers_and_ownership_seeding_is_idempotent(db):
    seed(db)
    taxpayer_count_1 = db.query(Taxpayer).count()
    owner_count_1 = db.query(CompanyOwner).count()

    seed(db)
    assert db.query(Taxpayer).count() == taxpayer_count_1
    assert db.query(CompanyOwner).count() == owner_count_1


def test_seed_creates_demo_accounts_linked_to_their_taxpayer(db):
    seed(db)
    for taxpayer_id, full_name, username, email, password in _DEMO_ACCOUNTS:
        user = db.query(User).filter_by(username=username).first()
        assert user is not None
        assert user.full_name == full_name
        assert user.email == email
        assert verify_password(password, user.password_hash)

        taxpayer = db.get(Taxpayer, taxpayer_id)
        assert taxpayer.user_id == user.id


def test_demo_accounts_seeding_is_idempotent(db):
    seed(db)
    user_count_1 = db.query(User).filter(User.username.in_([a[2] for a in _DEMO_ACCOUNTS])).count()

    seed(db)
    user_count_2 = db.query(User).filter(User.username.in_([a[2] for a in _DEMO_ACCOUNTS])).count()

    assert user_count_1 == user_count_2 == len(_DEMO_ACCOUNTS)


def test_seed_loads_all_fraud_dataset_rows_with_unique_9_digit_codes(db):
    seed(db)
    count = db.query(FraudRecord).count()
    assert count == 50_000

    codes = [r.claim_code for r in db.query(FraudRecord.claim_code).all()]
    assert len(set(codes)) == 50_000  # every code is unique
    assert all(len(c) == 9 and c.isdigit() and c[0] != "0" for c in codes)


def test_fraud_records_never_store_the_training_label():
    """The Fraud (training-target) column must never make it into the DB row —
    the model computes its own probability at prediction time; storing the
    answer next to the input would defeat the point of a review step."""
    assert not hasattr(FraudRecord, "Fraud")


def test_fraud_records_seeding_is_idempotent(db):
    seed(db)
    count_1 = db.query(FraudRecord).count()

    seed(db)
    count_2 = db.query(FraudRecord).count()

    assert count_1 == count_2 == 50_000


def test_demo_accounts_are_linked_to_their_fraud_records(db):
    """
    review_status is deliberately NOT asserted to be "pending" here — seeding
    only ever sets that as the INITIAL value and, being idempotent, never
    resets it afterward. On a real dev database these demo accounts are also
    the ones actually used interactively (e.g. requesting a review through
    the live chat UI), so their current status is real, mutable app state by
    the time this test runs — only the *link itself* is what seeding
    guarantees, and is what's actually under test here.
    """
    seed(db)
    for taxpayer_id, fraud_record_id in _DEMO_FRAUD_LINKS:
        taxpayer = db.get(Taxpayer, taxpayer_id)
        record = db.get(FraudRecord, fraud_record_id)
        assert record.user_id == taxpayer.user_id
        assert record.review_status in FRAUD_REVIEW_STATUSES


def test_demo_accounts_get_a_face_profile_when_a_real_embedding_already_exists(db):
    """
    On this project's dev database an enrolled face already exists (the
    developer's own), so seeding must have copied that embedding onto each
    demo account — this is what lets face verification succeed for any of
    them using that same real face. See seed.py's _seed_demo_accounts.
    """
    any_embedding = db.query(FaceProfile).first()
    if any_embedding is None:
        return  # nothing enrolled yet on this database — the skip path isn't exercised here

    seed(db)
    for _taxpayer_id, _full_name, username, _email, _password in _DEMO_ACCOUNTS:
        user = db.query(User).filter_by(username=username).first()
        face_profile = db.query(FaceProfile).filter_by(user_id=user.id).first()
        assert face_profile is not None
        assert list(face_profile.embedding) == list(any_embedding.embedding)
