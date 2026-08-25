from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Request
    original_query: str
    normalized_query: str
    # Authoritative from the authenticated FastAPI session (see
    # app.chat.routes.send_message) — never trust a user_id/company_id/
    # ownership claim supplied by the LLM or the message text itself.
    user_id: str

    # Router
    intent: str
    intent_confidence: float
    clarification_question: str
    # Set exactly once per turn, in route_intent (the graph's entry node),
    # from the user's own message — "ar" | "en". Every response-producing
    # node reads this instead of re-detecting language itself, so a single
    # turn never answers in two different languages. See
    # app.chat.responses.detect_response_language.
    response_language: str

    # Fraud
    extracted_features: dict
    missing_features: list[str]
    confirmed_features: dict
    fraud_validation_errors: list[str]
    prediction_label: str
    prediction_probability: Optional[float]
    prediction_tier: str  # "Standard Assessment" | "Comprehensive Assessment" — see fraud/engine.py
    fields_provided: int
    fields_total: int

    # Database (wired up in a later milestone)
    db_question_en: str
    sql_result: Any
    sql_error: Optional[str]

    # Response
    response_payload: dict
    final_response: str
