from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import User


def get_user_by_username_or_email(db: Session, identifier: str) -> User | None:
    stmt = select(User).where((User.username == identifier) | (User.email == identifier))
    return db.execute(stmt).scalar_one_or_none()


def username_or_email_taken(db: Session, username: str, email: str) -> bool:
    stmt = select(User).where((User.username == username) | (User.email == email))
    return db.execute(stmt).scalar_one_or_none() is not None
