"""
Tax-domain tables (schema `tax`) — real/importable business data, distinct
from the `auth` schema's login/biometric data. `Taxpayer.user_id` is nullable
because a taxpayer can exist in tax records without ever having an
application login (e.g. imported from the business dataset before that
person signs up). Ownership is a many-to-many relationship (`CompanyOwner`),
never a single field on `Taxpayer`/`Company` — a taxpayer can hold shares in
multiple companies, and a company can have multiple owners.

This module intentionally does not implement ownership-based row-level
authorization (which company/taxpayer records a given signed-in user is
allowed to see) — that is a separate, later feature. These models only
establish the schema so that feature can be layered on cleanly.
"""
import decimal
import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base
from app.database.models import AUTH_SCHEMA

TAX_SCHEMA = "tax"


class Taxpayer(Base):
    __tablename__ = "taxpayers"
    __table_args__ = {"schema": TAX_SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable + unique: a taxpayer may exist without an application login,
    # but if one is linked it's a strict one-to-one match.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{AUTH_SCHEMA}.users.id"), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = {"schema": TAX_SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    activity: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CompanyOwner(Base):
    """Many-to-many: a taxpayer can own shares in multiple companies."""

    __tablename__ = "company_owners"
    __table_args__ = (
        # Fractional share (0.5 = 50%), matching the majority-threshold
        # convention used elsewhere in the ownership/authorization spec.
        CheckConstraint("share >= 0 AND share <= 1", name="ck_company_owners_share_fraction"),
        {"schema": TAX_SCHEMA},
    )

    company_id: Mapped[int] = mapped_column(ForeignKey(f"{TAX_SCHEMA}.companies.id"), primary_key=True)
    # The composite PK (company_id, taxpayer_id) already serves "owners of
    # company X" lookups via its leading column, but not "companies owned by
    # taxpayer Y" — that's exactly what the ownership-authorization feature
    # will need, so taxpayer_id gets its own explicit index.
    taxpayer_id: Mapped[int] = mapped_column(
        ForeignKey(f"{TAX_SCHEMA}.taxpayers.id"), primary_key=True, index=True
    )
    share: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 4), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = {"schema": TAX_SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey(f"{TAX_SCHEMA}.companies.id"), nullable=False, index=True)
    sales: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    taxes: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = {"schema": TAX_SCHEMA}

    # Composite PK per the supplied dataset — item_id is only unique within
    # its invoice, not globally, so no surrogate key is invented here. The
    # PK's leading column (invoice_id) already indexes "items for invoice X"
    # lookups, so no separate index is added on invoice_id alone.
    invoice_id: Mapped[int] = mapped_column(ForeignKey(f"{TAX_SCHEMA}.transactions.id"), primary_key=True)
    item_id: Mapped[int] = mapped_column(primary_key=True)
    item_price: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)


# Review workflow for FraudRecord.review_status — set by the (not-yet-built)
# tax-authority admin side, never by the app or its users; the app only ever
# reads it (to answer "what's my status") or writes "requested_review" (when
# a user flags a value as wrong). "pending" is the seed-time default.
FRAUD_REVIEW_STATUSES = ["pending", "requested_review", "under_review", "reviewed"]


class FraudRecord(Base):
    """
    One row per record in the fraud-risk training dataset (ml_artifacts/
    tax_fraud_dataset_cleaned.xlsx, Fraud label column dropped — the model
    computes its own probability at prediction time, so the training answer
    is never stored here). `id` is the dataset's own original Taxpayer_ID
    (100000-149999), kept as-is rather than inventing a surrogate key, so it
    stays traceable back to the source file.

    Linking to an application user is a THIRD, independent identity mapping
    — unrelated to tax.taxpayers/company_owners (ownership tiers). Every
    signed-up user (majority owner, minority owner, or plain user) links to
    exactly one row here via the 9-digit `claim_code` entered at signup (see
    app.auth.routes.signup) — never a company/share claim. Deliberately
    reads/writes only through trusted first-party Python (this table has no
    RLS/secure view/app_agent grant, unlike tax.taxpayers/companies/etc. —
    the LLM-driven SQL-generation pipeline in services/sql_runner.py never
    references it at all, the same trust boundary auth.users already has).
    """

    __tablename__ = "fraud_records"
    __table_args__ = (
        CheckConstraint(
            f"review_status IN ({', '.join(repr(s) for s in FRAUD_REVIEW_STATUSES)})",
            name="ck_fraud_records_review_status",
        ),
        {"schema": TAX_SCHEMA},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    claim_code: Mapped[str] = mapped_column(String(9), unique=True, nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{AUTH_SCHEMA}.users.id"), unique=True, nullable=True
    )
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    # Which of the 23 fields below the user flagged as wrong on their last
    # "request review" action — informational for whoever reviews it later,
    # never read back by the app itself. Null until first flagged.
    flagged_fields: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    Business_Type: Mapped[str] = mapped_column(String(50), nullable=False)
    Region: Mapped[str] = mapped_column(String(50), nullable=False)
    Industry_Risk: Mapped[str] = mapped_column(String(20), nullable=False)

    Years_in_Business: Mapped[float] = mapped_column(Float, nullable=False)
    Employee_Count: Mapped[float] = mapped_column(Float, nullable=False)
    Annual_Revenue: Mapped[float] = mapped_column(Float, nullable=False)
    Annual_Expenses: Mapped[float] = mapped_column(Float, nullable=False)
    Net_Profit: Mapped[float] = mapped_column(Float, nullable=False)
    Taxable_Income: Mapped[float] = mapped_column(Float, nullable=False)
    Expected_Tax: Mapped[float] = mapped_column(Float, nullable=False)
    Declared_Tax: Mapped[float] = mapped_column(Float, nullable=False)
    VAT_Collected: Mapped[float] = mapped_column(Float, nullable=False)
    VAT_Paid: Mapped[float] = mapped_column(Float, nullable=False)
    Previous_Audits: Mapped[float] = mapped_column(Float, nullable=False)
    Previous_Violations: Mapped[float] = mapped_column(Float, nullable=False)
    Late_Payments: Mapped[float] = mapped_column(Float, nullable=False)
    Cash_Transactions_Percentage: Mapped[float] = mapped_column(Float, nullable=False)
    Missing_Documents: Mapped[float] = mapped_column(Float, nullable=False)
    Invoice_Mismatch: Mapped[float] = mapped_column(Float, nullable=False)
    Expense_Ratio: Mapped[float] = mapped_column(Float, nullable=False)
    Profit_Margin: Mapped[float] = mapped_column(Float, nullable=False)
    Revenue_per_Employee: Mapped[float] = mapped_column(Float, nullable=False)
    Tax_Gap: Mapped[float] = mapped_column(Float, nullable=False)
