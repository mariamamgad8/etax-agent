import datetime
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import EMBEDDING_DIM
from app.database.db import Base

AUTH_SCHEMA = "auth"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": AUTH_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # unique=True already creates a unique index in Postgres — no separate
    # index=True needed on top of it.
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Sliding-window session support: require_authenticated (app/auth/
    # dependencies.py) stamps this on every authenticated request and
    # rejects the request if it's been more than SESSION_INACTIVITY_TIMEOUT_
    # MINUTES since the last one — the JWT's own `exp` is deliberately a much
    # longer outer ceiling now, since a fixed-at-issuance JWT expiry can't
    # slide on its own. Nullable because pending_enrollment/face_required
    # users (and any row from before this column existed) never set it.
    last_active_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    face_profile: Mapped["FaceProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class FaceProfile(Base):
    """
    Kept separate from `users` so biometric data has its own lifecycle and
    access path rather than living alongside the password hash.
    """

    __tablename__ = "face_profiles"
    __table_args__ = {"schema": AUTH_SCHEMA}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{AUTH_SCHEMA}.users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    embedding: Mapped[list] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="face_profile")
