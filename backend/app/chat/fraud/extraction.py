from app.chat.fraud.schema import (
    BUSINESS_TYPE_OPTIONS,
    FraudFeatures,
    INDUSTRY_RISK_OPTIONS,
    REGION_OPTIONS,
)
from app.chat.providers.llm import call_llm_structured

_SYSTEM_PROMPT = f"""You extract fraud-risk-assessment inputs from a user's message (which may be in \
Arabic, English, or a mix). Fill in ONLY the fields the user actually stated or clearly implied — \
leave every other field null. Never guess, never estimate, never fill in a "reasonable default". \
Missing means null, not 0 and not "Unknown" — those are different things from "not mentioned".

Business_Type must be exactly one of: {", ".join(BUSINESS_TYPE_OPTIONS)} (or null).
Region must be exactly one of: {", ".join(REGION_OPTIONS)} (or null).
Industry_Risk must be exactly one of: {", ".join(INDUSTRY_RISK_OPTIONS)} (or null).
Only set these if the user's wording maps unambiguously onto one of the listed options — \
if they mention a place or business type not on the list, leave it null rather than picking the closest one.

All other fields are plain numbers (counts, amounts, percentages) — extract them only if a number for \
that specific concept is actually present in the message."""


def extract_fraud_features(query: str) -> FraudFeatures:
    return call_llm_structured(_SYSTEM_PROMPT, query, FraudFeatures)
