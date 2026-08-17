"""
Python-side validation of the confirmed fraud-assessment form, run after
every submission (initial or corrected) before a prediction is allowed.
The LLM extraction step is a convenience for prefilling the form — it is
never trusted as validated input on its own.
"""
from app.chat.fraud.schema import (
    ALL_FIELDS,
    BUSINESS_TYPE_OPTIONS,
    CATEGORICAL_FIELDS,
    FLOAT_FIELDS,
    INDUSTRY_RISK_OPTIONS,
    INT_FIELDS,
    REGION_OPTIONS,
)

_CATEGORICAL_OPTIONS = {
    "Business_Type": BUSINESS_TYPE_OPTIONS,
    "Region": REGION_OPTIONS,
    "Industry_Risk": INDUSTRY_RISK_OPTIONS,
}


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def validate_fraud_features(values: dict) -> list[str]:
    """Returns a list of human-readable error strings; empty means the form is ready to predict."""
    errors: list[str] = []

    for field in ALL_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            errors.append(f"{field} is required.")

    for field in CATEGORICAL_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            continue
        if value not in _CATEGORICAL_OPTIONS[field]:
            errors.append(f"{field} must be one of: {', '.join(_CATEGORICAL_OPTIONS[field])}.")

    for field in INT_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            continue
        if not _is_number(value) or float(value) != int(value):
            errors.append(f"{field} must be a whole number.")
        elif value < 0:
            errors.append(f"{field} cannot be negative.")

    for field in FLOAT_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            continue
        if not _is_number(value):
            errors.append(f"{field} must be a number.")

    percentage = values.get("Cash_Transactions_Percentage")
    if _is_number(percentage) and not (0 <= percentage <= 100):
        errors.append("Cash_Transactions_Percentage must be between 0 and 100.")

    return errors
