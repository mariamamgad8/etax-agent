"""
Python-side validation of the confirmed fraud-assessment form, run after
every submission (initial or corrected) before a prediction is allowed.
The LLM extraction step is a convenience for prefilling the form — it is
never trusted as validated input on its own.
"""
from app.chat.fraud.schema import (
    BUSINESS_TYPE_OPTIONS,
    CATEGORICAL_FIELDS,
    CORE_REQUIRED_FIELDS,
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

# Localized sentence templates — field names/option values (e.g. "Net_Profit",
# "Medium") stay as written regardless of language, since they're the
# technical identifiers the form/API actually uses, not prose (see
# CLAUDE.md's response-language feature: "preserve technical terms ... as
# written where appropriate"). Only the surrounding sentence is translated.
_MESSAGES = {
    "en": {
        "required": "{field} is required.",
        "categorical": "{field} must be one of: {options}.",
        "whole_number": "{field} must be a whole number.",
        "non_negative": "{field} cannot be negative.",
        "must_be_number": "{field} must be a number.",
        "percentage_range": "Cash_Transactions_Percentage must be between 0 and 100.",
    },
    "ar": {
        "required": "الحقل {field} مطلوب.",
        "categorical": "الحقل {field} يجب أن يكون واحدًا من: {options}.",
        "whole_number": "الحقل {field} يجب أن يكون رقمًا صحيحًا.",
        "non_negative": "الحقل {field} لا يمكن أن يكون بالسالب.",
        "must_be_number": "الحقل {field} يجب أن يكون رقمًا.",
        "percentage_range": "الحقل Cash_Transactions_Percentage يجب أن يكون بين 0 و100.",
    },
}


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float))


def validate_fraud_features(values: dict, language: str = "en") -> list[str]:
    """
    Returns a list of human-readable error strings (localized per
    `language`, "en" or "ar" — see app.chat.state.AgentState.response_language);
    empty means the form is ready to predict. Only the 8 core fields are
    required — the rest are optional but still validated (type/range/
    category) whenever provided, since a wrong value there is still wrong
    even if the field itself is optional. See fraud/schema.py's
    CORE_REQUIRED_FIELDS for why exactly these 8.
    """
    msg = _MESSAGES.get(language, _MESSAGES["en"])
    errors: list[str] = []

    for field in CORE_REQUIRED_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            errors.append(msg["required"].format(field=field))

    for field in CATEGORICAL_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            continue
        if value not in _CATEGORICAL_OPTIONS[field]:
            errors.append(msg["categorical"].format(field=field, options=", ".join(_CATEGORICAL_OPTIONS[field])))

    for field in INT_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            continue
        if not _is_number(value) or float(value) != int(value):
            errors.append(msg["whole_number"].format(field=field))
        elif value < 0:
            errors.append(msg["non_negative"].format(field=field))

    for field in FLOAT_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            continue
        if not _is_number(value):
            errors.append(msg["must_be_number"].format(field=field))

    percentage = values.get("Cash_Transactions_Percentage")
    if _is_number(percentage) and not (0 <= percentage <= 100):
        errors.append(msg["percentage_range"])

    return errors
