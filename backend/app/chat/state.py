from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # Request
    original_query: str
    normalized_query: str

    # Router
    intent: str
    intent_confidence: float
    clarification_question: str

    # Fraud (wired up in a later milestone)
    extracted_features: dict
    missing_features: list[str]
    confirmed_features: dict
    fraud_validation_errors: list[str]
    prediction_label: str
    prediction_probability: Optional[float]

    # Database (wired up in a later milestone)
    db_question_en: str
    sql_result: Any
    sql_error: Optional[str]

    # Response
    response_payload: dict
    final_response: str
