"""
LangGraph: route_intent classifies the message, then a conditional edge sends
it to a branch per INTENT_ROUTING. fraud_assessment and database_query are
real; the remaining four are still placeholders for a later milestone.

fraud_assessment: extract_fraud_fields -> review_form -> validate_fraud_form
-> predict_fraud -> fraud_response. review_form interrupts to collect the
user-confirmed form (see app.chat.routes for how a request resumes it).

database_query: prepare_db_question -> run_sql_query -> db_response.
"""
import json
import logging
import re

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app.chat.fraud.engine import predict as predict_fraud_model
from app.chat.fraud.extraction import extract_fraud_features
from app.chat.fraud.schema import (
    BUSINESS_TYPE_OPTIONS,
    FRAUD_THRESHOLD,
    INDUSTRY_RISK_OPTIONS,
    INT_FIELDS,
    NUMERIC_FIELD_ORDER,
    REGION_OPTIONS,
)
from app.chat.fraud.validation import validate_fraud_features
from app.chat.intent import INTENT_ROUTING, classify_intent
from app.chat.providers.llm import call_llm_text
from app.chat.db.query_chain import generate_and_run_sql
from app.chat.state import AgentState

logger = logging.getLogger(__name__)


def route_intent(state: AgentState) -> AgentState:
    result = classify_intent(state["normalized_query"])
    logger.info(
        "[INTENT] %r -> intent=%s confidence=%.2f reasoning=%s",
        state["normalized_query"],
        result.intent,
        result.confidence,
        result.reasoning,
    )
    return {**state, "intent": result.intent, "intent_confidence": result.confidence}


# --- fraud_assessment branch -------------------------------------------------


def extract_fraud_fields(state: AgentState) -> AgentState:
    features = extract_fraud_features(state["normalized_query"])
    extracted = features.model_dump(exclude_none=True)
    logger.info("[FRAUD] extracted fields from message: %s", extracted)
    return {**state, "extracted_features": extracted}


_FRAUD_FORM_SCHEMA = {
    "numeric_fields": NUMERIC_FIELD_ORDER,
    "integer_fields": INT_FIELDS,
    "categorical_fields": {
        "Business_Type": BUSINESS_TYPE_OPTIONS,
        "Region": REGION_OPTIONS,
        "Industry_Risk": INDUSTRY_RISK_OPTIONS,
    },
}


def review_form(state: AgentState) -> AgentState:
    """
    Always shown, even if extraction already filled every field — the user
    reviews/corrects before anything runs. Interrupting here pauses the graph
    (state is checkpointed) until the caller resumes with Command(resume=...).
    On a validation-failure loop-back, this re-shows the last submitted
    values plus the errors, not the original extraction.
    """
    prefill = state.get("confirmed_features") or state.get("extracted_features") or {}
    submitted = interrupt(
        {
            "type": "fraud_form",
            "fields": prefill,
            "errors": state.get("fraud_validation_errors") or [],
            "schema": _FRAUD_FORM_SCHEMA,
        }
    )
    return {**state, "confirmed_features": submitted}


def validate_fraud_form(state: AgentState) -> AgentState:
    errors = validate_fraud_features(state.get("confirmed_features") or {})
    if errors:
        logger.info("[FRAUD] form validation failed, looping back to review_form: %s", errors)
    else:
        logger.info("[FRAUD] form validation passed")
    return {**state, "fraud_validation_errors": errors}


def predict_fraud(state: AgentState) -> AgentState:
    label, probability = predict_fraud_model(state["confirmed_features"])
    logger.info("[FRAUD] XGBoost prediction: label=%s probability=%.4f threshold=%.3f", label, probability, FRAUD_THRESHOLD)
    return {**state, "prediction_label": label, "prediction_probability": probability}


def fraud_response(state: AgentState) -> AgentState:
    label = state["prediction_label"]
    probability = state["prediction_probability"]
    text = (
        f"The model returned a result of \"{label}\" for this input "
        f"(score {probability:.2f} on a 0.00-1.00 scale, review threshold {FRAUD_THRESHOLD:.2f}). "
        "A score above the review threshold does not confirm fraud — refer the case for manual "
        "review before taking any action."
    )
    return {**state, "final_response": text}


def _fraud_form_valid(state: AgentState) -> str:
    return "predict_fraud" if not state.get("fraud_validation_errors") else "review_form"


# --- database_query branch ---------------------------------------------------
# See app.chat.db.query_chain's module docstring for why this hand-rolled
# path is used instead of the SQLDatabaseChain experiment (also in that
# module) — SQLDatabaseChain proved unreliable with these providers.

_ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")


def _detect_language_name(text: str) -> str:
    """
    Cheap Unicode-range heuristic rather than asking the LLM to infer and
    match "the same language" implicitly — live-tested and found that
    instruction alone occasionally produces a wrong-language response (one
    run returned Russian for an Arabic query, with correct data otherwise;
    same inputs run again came back correctly in Arabic). Naming the target
    language explicitly is far more reliable than asking a model to match it.
    """
    return "Arabic" if _ARABIC_SCRIPT.search(text) else "English"


_DB_QUESTION_SYSTEM_PROMPT = """Rephrase the user's message as a single, clear English question about \
a tax database (tables: taxpayers, tax_returns). The message may be in Arabic, English, or a mix.

Preserve every specific detail exactly — taxpayer IDs, years, amounts, names. Never change a number \
or invent one that wasn't in the original message. Output ONLY the rephrased English question, \
nothing else (no preamble, no quotes)."""


def prepare_db_question(state: AgentState) -> AgentState:
    question_en = call_llm_text(_DB_QUESTION_SYSTEM_PROMPT, state["normalized_query"]).strip()
    logger.info("[DB] rephrased question (en): %s", question_en)
    return {**state, "db_question_en": question_en}


def run_sql_query(state: AgentState) -> AgentState:
    result = generate_and_run_sql(state["db_question_en"])
    return {**state, "sql_result": result, "sql_error": result.get("error")}


def _no_result_prompt(language: str) -> str:
    return f"""The user's question could not be answered from the authorized tax records (either no \
matching rows, or the request couldn't be understood as a database lookup). Write one short, plain \
sentence saying so, in {language} — respond in {language} regardless of what language this instruction \
is written in. Do not mention SQL, databases, columns, or any technical detail — just say the \
information wasn't found and suggest including a specific taxpayer ID or year."""


def _summary_prompt(language: str) -> str:
    return f"""You are the eTax assistant. Write a short (1-3 sentence) answer to the user's question, \
in {language} — respond in {language} regardless of what language this instruction or the records \
below are written in. Base the answer ONLY on the retrieved records given to you. Never state a \
number, name, or fact that is not literally present in those records. If there are many rows, \
summarize rather than listing each one — a table of the full records is shown separately, so you \
don't need to enumerate them."""


def db_response(state: AgentState) -> AgentState:
    sql_result = state.get("sql_result") or {}
    language = _detect_language_name(state["original_query"])
    logger.info("[DB] response language: %s", language)

    if sql_result.get("error") or not sql_result.get("rows"):
        text = call_llm_text(_no_result_prompt(language), state["original_query"])
        return {**state, "final_response": text.strip(), "response_payload": {}}

    columns = sql_result["columns"]
    rows = sql_result["rows"]

    summary_user_prompt = (
        f"User's original question: {state['original_query']}\n\n"
        f"Retrieved records (JSON): {json.dumps(rows[:20], default=str)}"
    )
    summary = call_llm_text(_summary_prompt(language), summary_user_prompt).strip()

    table = {
        "columns": [c.replace("_", " ").title() for c in columns],
        "rows": [[row.get(c) for c in columns] for row in rows],
    }
    return {**state, "final_response": summary, "response_payload": {"table": table}}


# --- remaining placeholder branches (later milestones) -----------------------


def _placeholder_node(message: str):
    def node(state: AgentState) -> AgentState:
        return {**state, "final_response": message}

    return node


assistant_identity = _placeholder_node(
    "I am the eTax assistant. I can help retrieve authorized tax information, "
    "perform tax fraud-risk assessment, and answer supported tax questions."
)
tax_conversation = _placeholder_node(
    "General tax conversation is being wired up next — this confirms routing works for now."
)
off_topic = _placeholder_node(
    "I specialize in tax-related assistance. I can help you retrieve tax information, "
    "perform fraud-risk assessment, or answer supported tax questions."
)
clarify_intent = _placeholder_node(
    "Could you clarify what you'd like — retrieving tax information, or a fraud-risk check?"
)
handle_multi_intent = _placeholder_node(
    "That looks like more than one request. Which would you like first: "
    "1) retrieve tax information, or 2) a fraud-risk assessment?"
)

_SIMPLE_BRANCH_NODES = {
    "assistant_identity": assistant_identity,
    "tax_conversation": tax_conversation,
    "off_topic": off_topic,
    "clarify_intent": clarify_intent,
    "handle_multi_intent": handle_multi_intent,
}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("route_intent", route_intent)

    for name, node in _SIMPLE_BRANCH_NODES.items():
        graph.add_node(name, node)
        graph.add_edge(name, END)

    graph.add_node("extract_fraud_fields", extract_fraud_fields)
    graph.add_node("review_form", review_form)
    graph.add_node("validate_fraud_form", validate_fraud_form)
    graph.add_node("predict_fraud", predict_fraud)
    graph.add_node("fraud_response", fraud_response)

    graph.add_edge("extract_fraud_fields", "review_form")
    graph.add_edge("review_form", "validate_fraud_form")
    graph.add_conditional_edges(
        "validate_fraud_form", _fraud_form_valid, ["predict_fraud", "review_form"]
    )
    graph.add_edge("predict_fraud", "fraud_response")
    graph.add_edge("fraud_response", END)

    graph.add_node("prepare_db_question", prepare_db_question)
    graph.add_node("run_sql_query", run_sql_query)
    graph.add_node("db_response", db_response)

    graph.add_edge("prepare_db_question", "run_sql_query")
    graph.add_edge("run_sql_query", "db_response")
    graph.add_edge("db_response", END)

    graph.set_entry_point("route_intent")
    all_branches = [*_SIMPLE_BRANCH_NODES, "extract_fraud_fields", "prepare_db_question"]
    graph.add_conditional_edges("route_intent", lambda s: INTENT_ROUTING.get(s.get("intent", ""), "clarify_intent"), all_branches)

    return graph.compile(checkpointer=InMemorySaver())


_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def _extract_interrupt(result: dict):
    """
    If the graph paused on an interrupt(), returns its payload; otherwise
    None. `result` is whatever graph.invoke(...) returned — on a pause that
    includes a "__interrupt__" key alongside the partial state.
    """
    pending = result.get("__interrupt__")
    if not pending:
        return None
    return pending[0].value


def run_chat(query: str, thread_id: str):
    """Starts a fresh graph run on `thread_id`. Returns (state, interrupt_payload_or_None)."""
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: AgentState = {"original_query": query, "normalized_query": query.strip()}
    result = get_graph().invoke(initial_state, config=config)
    return result, _extract_interrupt(result)


def resume_chat(resume_value, thread_id: str):
    """Resumes a paused run on `thread_id`. Returns (state, interrupt_payload_or_None)."""
    config = {"configurable": {"thread_id": thread_id}}
    result = get_graph().invoke(Command(resume=resume_value), config=config)
    return result, _extract_interrupt(result)
