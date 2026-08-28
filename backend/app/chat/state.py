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

    # Fraud — every field comes from the user's linked tax.fraud_records row
    # (see app.chat.fraud.records), never typed/pasted by the user.
    fraud_record_missing: bool
    fraud_record_id: int
    fraud_record_fields: dict
    fraud_review_status: str
    fraud_review_action: dict  # the review_form interrupt's resume value
    fraud_flagged: bool
    prediction_probability: Optional[float]

    # Database
    db_question_en: str
    sql_result: Any
    sql_error: Optional[str]
    # Short-term memory across turns ON THE SAME thread_id: the last
    # resolved English question from a database_query turn, so a follow-up
    # like "what about the taxes" can be resolved against "sales in Bright
    # company" without the user repeating themselves. Only prepare_db_question
    # reads/writes this — untouched by every other branch, so it simply sits
    # unused (not stale-dangerous) across a greeting/fraud_assessment turn in
    # between. See graph.py's prepare_db_question.
    last_db_question_en: Optional[str]

    # Response
    response_payload: dict
    final_response: str
