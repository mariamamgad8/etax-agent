"""
Reads/updates a user's linked tax.fraud_records row. Trusted first-party
Python only (never the LLM-driven SQL pipeline — see FraudRecord's
docstring) — user_id always comes from the authenticated session
(AgentState["user_id"]), never from message text.
"""
import uuid

from sqlalchemy.orm import Session

from app.chat.fraud.schema import ALL_FIELDS
from app.database.tax_models import FraudRecord


def get_user_fraud_record(db: Session, user_id: uuid.UUID) -> FraudRecord | None:
    return db.query(FraudRecord).filter(FraudRecord.user_id == user_id).one_or_none()


def record_to_fields(record: FraudRecord) -> dict:
    return {field: getattr(record, field) for field in ALL_FIELDS}


def request_review(db: Session, record: FraudRecord, flagged_fields: list[str]) -> None:
    record.review_status = "requested_review"
    record.flagged_fields = flagged_fields or None
    db.add(record)
    db.commit()
