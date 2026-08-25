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

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
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
