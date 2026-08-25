"""
LangGraph: route_intent classifies the message, then a conditional edge sends
it to a branch per INTENT_ROUTING. fraud_assessment and database_query are
fully implemented; greeting/other/clarify_intent/handle_multi_intent answer
from curated bilingual deterministic templates (app.chat.responses, no LLM
call).

Every response-producing node answers in state["response_language"] ("ar" |
"en"), set exactly once per turn in route_intent from the user's own message
— never re-detected mid-turn, so one turn never mixes languages. Internal-only
text (e.g. prepare_db_question's English SQL-generation question) is exempt:
it never reaches the user.

fraud_assessment: extract_fraud_fields -> review_form -> validate_fraud_form
-> predict_fraud -> fraud_response. review_form interrupts to collect the
user-confirmed form (see app.chat.routes for how a request resumes it).

database_query: prepare_db_question -> run_sql_query -> db_response.
"""
import json
import logging
import re
import uuid

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command, interrupt

from app.chat.fraud.engine import predict as predict_fraud_model
from app.chat.fraud.extraction import extract_fraud_features
from app.chat.fraud.schema import (
    ALL_FIELDS,
    BUSINESS_TYPE_OPTIONS,
    CORE_REQUIRED_FIELDS,
    FRAUD_THRESHOLD,
    INDUSTRY_RISK_OPTIONS,
    INT_FIELDS,
    NUMERIC_FIELD_ORDER,
    OPTIONAL_FIELDS,
    REGION_OPTIONS,
)
from app.chat.fraud.validation import validate_fraud_features
from app.chat.intent import INTENT_ROUTING, classify_intent
from app.chat.providers.llm import call_llm_text
from app.chat.responses import (
    CLARIFY_INTENT_TEMPLATES,
    GREETING_TEMPLATES,
    LANGUAGE_NAMES,
    MULTI_INTENT_TEMPLATES,
    OTHER_TEMPLATES,
    build_fraud_result_text,
    detect_response_language,
    pick_template,
)
from app.chat.services.sql_runner import handle_user_database_query
from app.chat.state import AgentState
from app.database.db import engine as owner_engine

logger = logging.getLogger(__name__)

# Whole-message allow-list for a deterministic greeting pre-router — matched
# only after stripping punctuation and lowercasing, and only against the
# ENTIRE normalized message. This intentionally avoids substring/startswith
# matching: "Hi, show me my company's taxes." normalizes to "hi show me my
# companys taxes", which is not in this set, so it still falls through to
# the LLM classifier rather than being misclassified as a pure greeting.
_GREETING_PHRASES = [
    "hi", "hello", "hey", "hiya", "yo", "hi there", "hello there", "hey there",
    "good morning", "good afternoon", "good evening",
    "مرحبا", "أهلا", "اهلا",
    "السلام عليكم", "سلام", "سلام عليكم", "صباح الخير", "مساء الخير",
]
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_for_greeting_match(text: str) -> str:
    return _PUNCTUATION.sub("", text).strip().lower()


# Phrases are normalized through the same function used on incoming
# messages, so a diacritic/punctuation variant of a listed phrase (e.g.
# "مرحبًا") still matches without needing its own separate entry.
_PURE_GREETINGS = {_normalize_for_greeting_match(p) for p in _GREETING_PHRASES}


def _pure_greeting_match(text: str) -> bool:
    return _normalize_for_greeting_match(text) in _PURE_GREETINGS


# --- deterministic fraud_assessment pre-router --------------------------
# Added after production logs showed the LLM classifier repeatedly losing
# real fraud requests to tax_conversation/database_query/unclear — most
# visibly on Arabic phrasing like "عايز اشوف ورق الشركة بتاعتي سليم ولا في
# مشكلة" (obviously fraud_assessment, classified as database_query) and on a
# pasted feature dump with no framing sentence (classified as the
# tax_conversation placeholder). Two tiers, both bypassing the LLM entirely:

# Tier 1 — a raw "Field: value" dump (e.g. copy-pasted from a test/extraction
# run) is an unambiguous structural signal: if the message names several of
# the model's own known fraud fields as field:value pairs, it's a fraud
# request, full stop. "Industry_Risk_ord" is the engine's internal
# ordinal-encoded column name (see fraud/engine.py) — included here only so
# a pasted debug/engineered-feature dump still matches, even though the
# model never asks the user for that name directly.
_FRAUD_FIELD_NAMES = set(ALL_FIELDS) | {"Industry_Risk_ord"}
_FIELD_DUMP_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in _FRAUD_FIELD_NAMES) + r")\s*:\s*\S+",
    re.IGNORECASE,
)
_FIELD_DUMP_MIN_MATCHES = 3


def _looks_like_fraud_field_dump(text: str) -> bool:
    matches = {m.group(1) for m in _FIELD_DUMP_PATTERN.finditer(text)}
    return len(matches) >= _FIELD_DUMP_MIN_MATCHES


# Tier 2 — an explicit fraud-leaning keyword/phrase, in Arabic or English.
# Deliberately broad (e.g. bare "check"/"فحص" would previously have been
# "unclear") per direct instruction after reviewing real misclassifications
# ("check fraud" and "want to assess my company" both landed on unclear).
# Skipped if the message ALSO contains an explicit database-retrieval verb,
# so a message that's genuinely about pulling stored data still reaches the
# classifier (which can weigh both signals, including multi_intent).
_FRAUD_TRIGGER_PHRASES = [
    "سليم", "اوراق", "أوراق", "ورق الشركة", "فحص", "تهرب ضريبي",
    "اتاكد من اوراقي", "أتأكد من أوراقي", "مشتبه", "احتيال", "مخاطر",
    "detect", "sus", "check", "assess", "assessment", "fraud", "suspicious", "risk",
]
_DB_QUERY_OVERRIDE_PHRASES = ["retrieve", "query", "get me", "give me", "show me"]


def _contains_fraud_trigger(text: str) -> bool:
    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in _FRAUD_TRIGGER_PHRASES)


def _contains_db_query_override(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _DB_QUERY_OVERRIDE_PHRASES)


def route_intent(state: AgentState) -> AgentState:
    query = state["normalized_query"]

    # The one and only per-turn language detection — every response-producing
    # node below reads state["response_language"] instead of recomputing it,
    # so a single turn can never answer in two different languages even
    # though several nodes may run before a reply is produced. Plain-text
    # turns each start a fresh graph run (see run_chat), so this naturally
    # re-detects on every new message — a user switching from Arabic to
    # English (or back) gets the new language on their very next turn.
    response_language = detect_response_language(state["original_query"])

    def _deterministic(intent: str, reason: str) -> AgentState:
        logger.info(
            "[INTENT] %r -> intent=%s confidence=1.00 language=%s (deterministic pre-router: %s, classifier skipped)",
            query, intent, response_language, reason,
        )
        return {**state, "intent": intent, "intent_confidence": 1.0, "response_language": response_language}

    # Deterministic fast paths — see the two tiers documented above. Order
    # matters: an obvious greeting never needs a classifier call at all (only
    # fires on a full-message allow-list match, never a prefix/substring
    # check, so "Hi, show my taxes." still falls through). The fraud
    # field-dump check is the next-highest-confidence signal, then the
    # keyword trigger (unless a stronger retrieval verb is also present).
    if _pure_greeting_match(query):
        return _deterministic("greeting", "pure greeting")
    if _looks_like_fraud_field_dump(query):
        return _deterministic("fraud_assessment", "pasted feature field:value dump")
    if _contains_fraud_trigger(query) and not _contains_db_query_override(query):
        return _deterministic("fraud_assessment", "fraud-leaning keyword")

    result = classify_intent(query)
    logger.info(
        "[INTENT] %r -> intent=%s confidence=%.2f language=%s reasoning=%s",
        query,
        result.intent,
        result.confidence,
        response_language,
        result.reasoning,
    )
    return {
        **state,
        "intent": result.intent,
        "intent_confidence": result.confidence,
        "response_language": response_language,
    }


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
    # Drives the frontend's two-tier layout (required "standard assessment"
    # section vs. optional "comprehensive assessment" section) — never
    # exposed to the user as "8-feature"/"23-feature", just which fields are
    # required vs. optional.
    "required_fields": CORE_REQUIRED_FIELDS,
    "optional_fields": OPTIONAL_FIELDS,
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
    language = state.get("response_language", "en")
    errors = validate_fraud_features(state.get("confirmed_features") or {}, language)
    if errors:
        logger.info("[FRAUD] form validation failed, looping back to review_form: %s", errors)
    else:
        logger.info("[FRAUD] form validation passed")
    return {**state, "fraud_validation_errors": errors}


def predict_fraud(state: AgentState) -> AgentState:
    result = predict_fraud_model(state["confirmed_features"])
    logger.info(
        "[FRAUD] prediction: label=%s probability=%.4f tier=%s fields=%d/%d threshold=%.3f",
        result["label"],
        result["probability"],
        result["tier"],
        result["fields_provided"],
        result["fields_total"],
        FRAUD_THRESHOLD,
    )
    return {
        **state,
        "prediction_label": result["label"],
        "prediction_probability": result["probability"],
        "prediction_tier": result["tier"],
        "fields_provided": result["fields_provided"],
        "fields_total": result["fields_total"],
    }


def fraud_response(state: AgentState) -> AgentState:
    language = state.get("response_language", "en")
    text = build_fraud_result_text(
        language,
        state["prediction_tier"],
        state["fields_provided"],
        state["fields_total"],
        state["prediction_label"],
        state["prediction_probability"],
        FRAUD_THRESHOLD,
    )
    return {**state, "final_response": text}


def _fraud_form_valid(state: AgentState) -> str:
    return "predict_fraud" if not state.get("fraud_validation_errors") else "review_form"


# --- database_query branch ---------------------------------------------------
# run_sql_query delegates to app.chat.services.sql_runner.handle_user_database_query,
# which determines the authenticated user's per-company ownership from
# Postgres, restricts the LLM to the matching secure view(s), and executes as
# the unprivileged app_agent role with RLS enforced. See that module and
# app.database.security_setup for the full design. (query_chain.py's
# generate_and_run_sql/ask_database are a different, non-ownership-aware
# experiment kept only for the record — see that module's docstring.)

_DB_QUESTION_SYSTEM_PROMPT = """Rephrase the user's message as a single, clear English question about \
a tax database (tables: taxpayers, companies, company_owners, transactions, items). The message may be in Arabic, English, or a mix.

Preserve every specific detail exactly — taxpayer IDs, years, amounts, names. Never change a number \
or invent one that wasn't in the original message. Output ONLY the rephrased English question, \
nothing else (no preamble, no quotes)."""


def prepare_db_question(state: AgentState) -> AgentState:
    question_en = call_llm_text(_DB_QUESTION_SYSTEM_PROMPT, state["normalized_query"]).strip()
    logger.info("[DB] rephrased question (en): %s", question_en)
    return {**state, "db_question_en": question_en}


def run_sql_query(state: AgentState) -> AgentState:
    user_id = uuid.UUID(state["user_id"])
    with owner_engine.connect() as conn:
        result = handle_user_database_query(user_id, state["db_question_en"], conn)
    return {**state, "sql_result": result, "sql_error": None if result["status"] in ("success", "direct_answer") else result["status"]}


# Each of these builds an LLM prompt for a specific, typed outcome from
# sql_runner.handle_user_database_query (see that module's STATUS list) —
# replacing a single "no result" bucket that made a genuine security denial
# and a plain empty query result read identically to the user. The LLM's
# job here is still only phrasing/language, never deciding what happened —
# the facts (which field, which company, which candidates) are already
# fixed by the deterministic authorization step before this ever runs.


def _no_result_prompt(language: str) -> str:
    return f"""The user's question could not be understood as a database lookup at all. Write one \
short, plain sentence saying so, in {language} — respond in {language} regardless of what language \
this instruction is written in. Do not mention SQL, databases, columns, or any technical detail."""


def _empty_result_prompt(language: str) -> str:
    return f"""The user's question WAS understood and a valid, authorized lookup was run, but it \
returned no matching records. Write one short, plain, neutral sentence saying so, in {language} — \
respond in {language} regardless of what language this instruction is written in. Do not imply a \
permissions problem or suggest they lack access — just say nothing matched, and suggest checking the \
details (e.g. a specific year or ID) if relevant. Do not mention SQL, databases, or columns."""


def _unauthorized_prompt(language: str) -> str:
    return f"""The user asked to look up company/tax records, but they don't own shares in any \
company, so they aren't authorized to query company tax records at all. Write one short, plain, \
polite sentence explaining this, in {language} — respond in {language} regardless of what language \
this instruction is written in. Mention that they can still use the fraud-risk assessment feature or \
ask general tax questions instead. Do not mention SQL, databases, ownership shares, or any technical \
detail."""


def _forbidden_entity_prompt(language: str, mentions: list[str]) -> str:
    named = ", ".join(mentions) or "that company"
    return f"""The user asked about a company ("{named}") that does not match any company they own \
shares in. Write one short, polite sentence in {language} — respond in {language} regardless of what \
language this instruction is written in — saying it doesn't match any company they have access to, and \
suggesting they check the name or ask "which companies do I own" to see the exact names. Do NOT confirm \
or deny whether a company by that name exists elsewhere — only that it isn't among theirs. Do not \
mention SQL, databases, or any technical detail."""


def _forbidden_field_prompt(language: str, field: str, company_name: str, access_level: str) -> str:
    field_label = field.replace("_", " ")
    return f"""The user asked for "{field_label}" for a company they own ({company_name!r}), but their \
ownership share there ({access_level}) does not grant access to that specific information — minority \
owners cannot see sales, item prices, quantities, or item-level detail. Write one short, polite \
sentence in {language} — respond in {language} regardless of what language this instruction is written \
in — explaining that this specific detail isn't available at their ownership level for that company. \
Do not mention SQL, databases, or any other technical detail, and do not suggest the restriction can be \
worked around."""


def _ambiguous_entity_prompt(language: str, mention: str, candidate_names: list[str]) -> str:
    options = ", ".join(candidate_names)
    return f"""The user referred to a company as "{mention}", which matches more than one of their own \
companies: {options}. Write one short, polite sentence in {language} — respond in {language} regardless \
of what language this instruction is written in — asking them to specify which one they meant, naming \
the options. Do not mention SQL, databases, or any technical detail."""


def _summary_prompt(language: str) -> str:
    return f"""You are the eTax assistant. Write a short (1-3 sentence) answer to the user's question, \
in {language} — respond in {language} regardless of what language this instruction or the records \
below are written in. Base the answer ONLY on the retrieved records given to you. Never state a \
number, name, or fact that is not literally present in those records. If there are many rows, \
summarize rather than listing each one — a table of the full records is shown separately, so you \
don't need to enumerate them."""


def db_response(state: AgentState) -> AgentState:
    sql_result = state.get("sql_result") or {}
    language = LANGUAGE_NAMES[state.get("response_language", "en")]
    status = sql_result.get("status")
    detail = sql_result.get("detail") or {}
    logger.info("[DB] response language: %s, status: %s", language, status)

    if status == "no_ownership":
        text = call_llm_text(_unauthorized_prompt(language), state["original_query"])
        return {**state, "final_response": text.strip(), "response_payload": {}}

    if status == "forbidden_entity":
        text = call_llm_text(_forbidden_entity_prompt(language, detail.get("mentions", [])), state["original_query"])
        return {**state, "final_response": text.strip(), "response_payload": {}}

    if status == "forbidden_field":
        text = call_llm_text(
            _forbidden_field_prompt(language, detail["field"], detail["company_name"], detail["access_level"]),
            state["original_query"],
        )
        return {**state, "final_response": text.strip(), "response_payload": {}}

    if status == "ambiguous_entity":
        candidate_names = [c["company_name"] for c in detail.get("candidates", [])]
        text = call_llm_text(_ambiguous_entity_prompt(language, detail.get("mention", ""), candidate_names), state["original_query"])
        return {**state, "final_response": text.strip(), "response_payload": {}}

    if status in ("sql_validation_failed", "sql_execution_failed"):
        text = call_llm_text(_no_result_prompt(language), state["original_query"])
        return {**state, "final_response": text.strip(), "response_payload": {}}

    if status == "empty_result" or not sql_result.get("rows"):
        text = call_llm_text(_empty_result_prompt(language), state["original_query"])
        return {**state, "final_response": text.strip(), "response_payload": {}}

    # status in ("success", "direct_answer") — both are a real, authorized
    # set of rows (either from SQL or straight from trusted context), so
    # they're phrased and tabled identically from here on.
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


# --- deterministic-template branches ------------------------------------
# No response-generation LLM call for any of these — a curated bilingual
# template pool (app.chat.responses) is picked from directly, keyed off
# state["response_language"] (set once in route_intent, never recomputed
# here — see that function's docstring for why).


def _templated_node(template_pool: dict[str, list[str]], log_tag: str):
    def node(state: AgentState) -> AgentState:
        language = state.get("response_language", "en")
        text = pick_template(template_pool[language])
        logger.info("[RESPONSE] %s -> language=%s reply=%r", log_tag, language, text)
        return {**state, "final_response": text}

    return node


greeting = _templated_node(GREETING_TEMPLATES, "greeting")
other = _templated_node(OTHER_TEMPLATES, "other")
clarify_intent = _templated_node(CLARIFY_INTENT_TEMPLATES, "clarify_intent")
handle_multi_intent = _templated_node(MULTI_INTENT_TEMPLATES, "handle_multi_intent")

_SIMPLE_BRANCH_NODES = {
    "greeting": greeting,
    "other": other,
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


def run_chat(query: str, thread_id: str, user_id: str):
    """Starts a fresh graph run on `thread_id`. Returns (state, interrupt_payload_or_None)."""
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: AgentState = {
        "original_query": query,
        "normalized_query": query.strip(),
        "user_id": user_id,
    }
    result = get_graph().invoke(initial_state, config=config)
    return result, _extract_interrupt(result)


def resume_chat(resume_value, thread_id: str):
    """Resumes a paused run on `thread_id`. Returns (state, interrupt_payload_or_None)."""
    config = {"configurable": {"thread_id": thread_id}}
    result = get_graph().invoke(Command(resume=resume_value), config=config)
    return result, _extract_interrupt(result)
