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
from app.chat.fraud.records import get_user_fraud_record, record_to_fields, request_review
from app.chat.fraud.schema import ALL_FIELDS, FRAUD_THRESHOLD
from app.chat.intent import INTENT_ROUTING, classify_intent
from app.chat.providers.llm import call_llm_text
from app.chat.responses import (
    CLARIFY_INTENT_TEMPLATES,
    GREETING_TEMPLATES,
    LANGUAGE_NAMES,
    MULTI_INTENT_TEMPLATES,
    NO_FRAUD_RECORD_TEMPLATES,
    OTHER_TEMPLATES,
    REVIEW_REQUESTED_TEMPLATES,
    build_fraud_result_text,
    build_fraud_status_text,
    detect_response_language,
    pick_template,
)
from app.chat.services.sql_runner import handle_user_database_query
from app.chat.state import AgentState
from app.database.db import SessionLocal
from app.database.db import engine as owner_engine
from app.database.tax_models import FraudRecord

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
    # Arabic-script transliteration of "risk score" — a real reported miss:
    # "مخاطر" (the Arabic word) was already covered, but a user typing the
    # English term in Arabic letters ("الريسك سكور") isn't the same substring
    # and fell through to the classifier, which read a half-finished
    # self-corrected sentence as "other" instead of reopening the review.
    "ريسك سكور", "ريسك",
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

    # Both return paths below also reset response_payload to {} — this is
    # the ONE node every turn always passes through, so it's the right place
    # to clear a stale table from a PREVIOUS turn. Now that the frontend
    # reuses one thread_id for the whole session (see ChatPage.jsx's
    # threadId state, for database_query memory), the checkpointer persists
    # AgentState across turns; a branch that never touches response_payload
    # itself (fraud_response, the templated greeting/other/clarify nodes)
    # would otherwise silently keep re-returning the LAST turn's table
    # forever — confirmed live: a fraud risk-score reply kept showing the
    # previous turn's company-ownership table underneath it.

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
        return {**state, "intent": intent, "intent_confidence": 1.0, "response_language": response_language, "response_payload": {}}

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

    result = classify_intent(query, state.get("last_db_question_en"))
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
        "response_payload": {},
    }


# --- fraud_assessment branch -------------------------------------------------
# load_fraud_record -> (no linked record) -> fraud_no_record_response
#                    -> review_form [interrupt: shows the linked DB record
#                       read-only] -> handle_fraud_review_action
#                          -> (user confirmed) -> predict_fraud -> fraud_response
#                          -> (user flagged fields) -> flagged_review_response
# Every field always comes from the user's own tax.fraud_records row (linked
# at signup via a 9-digit claim code — see app.auth.routes.signup), never
# typed/pasted into the chat.


def load_fraud_record(state: AgentState) -> AgentState:
    db = SessionLocal()
    try:
        record = get_user_fraud_record(db, uuid.UUID(state["user_id"]))
    finally:
        db.close()

    if record is None:
        logger.warning("[FRAUD] no linked fraud_records row for user_id=%s", state["user_id"])
        return {**state, "fraud_record_missing": True}

    return {
        **state,
        "fraud_record_missing": False,
        "fraud_record_id": record.id,
        "fraud_record_fields": record_to_fields(record),
        "fraud_review_status": record.review_status,
    }


def _fraud_record_found(state: AgentState) -> str:
    return "fraud_no_record_response" if state.get("fraud_record_missing") else "review_form"


def fraud_no_record_response(state: AgentState) -> AgentState:
    language = state.get("response_language", "en")
    return {**state, "final_response": pick_template(NO_FRAUD_RECORD_TEMPLATES[language])}


def review_form(state: AgentState) -> AgentState:
    """
    Shows the linked record's values read-only and pauses the graph (state is
    checkpointed) until the caller resumes with Command(resume=...). The
    resume value is either {"action": "confirm"} (run the risk assessment as
    stored) or {"action": "flag", "fields": [...]} (the user believes some of
    these values are wrong — never edited in place here, just flagged for the
    tax authority to review; see FraudRecord's docstring for why).
    """
    submitted = interrupt(
        {
            "type": "fraud_review",
            "record_id": state["fraud_record_id"],
            "record": state["fraud_record_fields"],
            "review_status": state["fraud_review_status"],
        }
    )
    return {**state, "fraud_review_action": submitted}


def handle_fraud_review_action(state: AgentState) -> AgentState:
    action = state.get("fraud_review_action") or {}
    if action.get("action") == "flag":
        db = SessionLocal()
        try:
            record = db.get(FraudRecord, state["fraud_record_id"])
            request_review(db, record, action.get("fields") or [])
        finally:
            db.close()
        logger.info("[FRAUD] user_id=%s flagged fields for review: %s", state["user_id"], action.get("fields"))
        return {**state, "fraud_flagged": True}
    return {**state, "fraud_flagged": False}


def _fraud_action_router(state: AgentState) -> str:
    return "flagged_review_response" if state.get("fraud_flagged") else "predict_fraud"


def flagged_review_response(state: AgentState) -> AgentState:
    language = state.get("response_language", "en")
    return {**state, "final_response": pick_template(REVIEW_REQUESTED_TEMPLATES[language])}


def predict_fraud(state: AgentState) -> AgentState:
    result = predict_fraud_model(state["fraud_record_fields"])
    logger.info(
        "[FRAUD] prediction: probability=%.4f threshold=%.3f is_high_risk=%s",
        result["probability"], FRAUD_THRESHOLD, result["is_high_risk"],
    )
    return {**state, "prediction_probability": result["probability"]}


def fraud_response(state: AgentState) -> AgentState:
    language = state.get("response_language", "en")
    text = build_fraud_result_text(language, state["prediction_probability"], FRAUD_THRESHOLD)
    return {**state, "final_response": text}


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

_DB_QUESTION_WITH_MEMORY_SYSTEM_PROMPT = _DB_QUESTION_SYSTEM_PROMPT + """

For context, the user's PREVIOUS question in this same conversation was: "{previous_question}"
If the new message is a follow-up that leaves something implied by that previous question unstated \
(e.g. the same company, a different metric — "what about the taxes" after "sales in Bright company"), \
resolve it into ONE single, fully self-contained question that repeats the implied detail explicitly. \
If the new message is unrelated to the previous one, ignore the previous question entirely and \
rephrase only the new message."""


def prepare_db_question(state: AgentState) -> AgentState:
    previous_question = state.get("last_db_question_en")
    prompt = (
        _DB_QUESTION_WITH_MEMORY_SYSTEM_PROMPT.format(previous_question=previous_question)
        if previous_question
        else _DB_QUESTION_SYSTEM_PROMPT
    )
    question_en = call_llm_text(prompt, state["normalized_query"]).strip()
    logger.info("[DB] rephrased question (en): %s%s", question_en, " (used memory)" if previous_question else "")
    return {**state, "db_question_en": question_en, "last_db_question_en": question_en}


def run_sql_query(state: AgentState) -> AgentState:
    user_id = uuid.UUID(state["user_id"])
    with owner_engine.connect() as conn:
        result = handle_user_database_query(user_id, state["db_question_en"], conn)
    return {**state, "sql_result": result, "sql_error": None if result["status"] in ("success", "direct_answer", "fraud_status") else result["status"]}


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
    return f"""You are the eTax assistant. Write a short (2-4 sentence) answer to the user's question, \
in {language} — respond in {language} regardless of what language this instruction or the records \
below are written in. Base the answer ONLY on the retrieved records given to you. Never state a \
number, name, or fact that is not literally present in those records — in particular, never compute, \
estimate, or state a percentage/rate/ratio yourself even if it seems obvious from two numbers you see; \
only state a percentage if a field already named as a rate/percentage (e.g. tax_rate) is literally \
present in the records — when it is, phrase that field's value as a plain percentage in the sentence \
(e.g. a tax_rate of 0.15 is "15%"), never as a raw decimal fraction with many digits, and phrase it \
the same way regardless of what language you're answering in. If the records include a company_name, \
mention which company each fact belongs \
to rather than presenting the numbers generically — a multi-company owner cannot otherwise tell which \
company the answer is even about. If there are many rows, summarize rather than listing each one — a \
table of the full records is shown separately, so you don't need to enumerate them. If an "Excluded \
companies" note is given below, add one short sentence naming them and saying that level of detail \
isn't available for them at the user's access level there."""


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

    if status == "fraud_status":
        text = build_fraud_status_text(state.get("response_language", "en"), detail.get("review_status"))
        return {**state, "final_response": text, "response_payload": {}}

    if status == "unclear":
        # Same deterministic, bilingual "which do you want" prompt the
        # unclear INTENT already uses (clarify_intent) — offering the two
        # real capabilities is more useful than a flat "couldn't understand",
        # and needs no LLM call since the wording never depends on the
        # specific question.
        text = pick_template(CLARIFY_INTENT_TEMPLATES[state.get("response_language", "en")])
        return {**state, "final_response": text, "response_payload": {}}

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
    excluded_companies = detail.get("excluded_companies") or []
    if excluded_companies:
        summary_user_prompt += f"\n\nExcluded companies (not authorized for this at the user's access level there): {', '.join(excluded_companies)}"
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

    graph.add_node("load_fraud_record", load_fraud_record)
    graph.add_node("fraud_no_record_response", fraud_no_record_response)
    graph.add_node("review_form", review_form)
    graph.add_node("handle_fraud_review_action", handle_fraud_review_action)
    graph.add_node("flagged_review_response", flagged_review_response)
    graph.add_node("predict_fraud", predict_fraud)
    graph.add_node("fraud_response", fraud_response)

    graph.add_conditional_edges(
        "load_fraud_record", _fraud_record_found, ["review_form", "fraud_no_record_response"]
    )
    graph.add_edge("fraud_no_record_response", END)
    graph.add_edge("review_form", "handle_fraud_review_action")
    graph.add_conditional_edges(
        "handle_fraud_review_action", _fraud_action_router, ["predict_fraud", "flagged_review_response"]
    )
    graph.add_edge("flagged_review_response", END)
    graph.add_edge("predict_fraud", "fraud_response")
    graph.add_edge("fraud_response", END)

    graph.add_node("prepare_db_question", prepare_db_question)
    graph.add_node("run_sql_query", run_sql_query)
    graph.add_node("db_response", db_response)

    graph.add_edge("prepare_db_question", "run_sql_query")
    graph.add_edge("run_sql_query", "db_response")
    graph.add_edge("db_response", END)

    graph.set_entry_point("route_intent")
    all_branches = [*_SIMPLE_BRANCH_NODES, "load_fraud_record", "prepare_db_question"]
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
