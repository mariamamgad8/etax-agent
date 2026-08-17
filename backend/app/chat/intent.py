from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat.providers.llm import call_llm_structured

Intent = Literal[
    "fraud_assessment",
    "database_query",
    "assistant_identity",
    "tax_conversation",
    "off_topic",
    "unclear",
    "multi_intent",
]

# The LLM only ever says which intent it thinks this is — routing to an
# actual node is a Python lookup, never left to the model's judgment.
INTENT_ROUTING: dict[str, str] = {
    "fraud_assessment": "extract_fraud_fields",
    "database_query": "prepare_db_question",
    "assistant_identity": "assistant_identity",
    "tax_conversation": "tax_conversation",
    "off_topic": "off_topic",
    "unclear": "clarify_intent",
    "multi_intent": "handle_multi_intent",
}


class IntentResult(BaseModel):
    # extra="forbid" makes Pydantic emit additionalProperties:false on the
    # generated JSON schema, which Groq's strict json_schema mode requires —
    # without it, every call falls through to a looser fallback model.
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(description="One short sentence on why this intent was chosen.")


_SYSTEM_PROMPT = """You are the intent router for eTax, a tax-authority assistant. \
The user's message may be in Arabic, English, or a mix of both. Classify it into exactly one intent:

- fraud_assessment: the user wants a fraud/risk check run on a taxpayer or business.
- database_query: the user wants to look up stored tax records/data (payments, returns, taxpayer info).
- assistant_identity: the user is asking who/what the assistant is or what it can do.
- tax_conversation: a general tax question (definitions, concepts, rules) not tied to a specific stored record or fraud check.
- off_topic: unrelated to tax, taxpayers, or this assistant's purpose.
- unclear: names a taxpayer/company and asks to "check" or "look into" them with NO further detail on \
what kind of check — this could equally mean "look up their records" (database_query) or "assess their \
fraud risk" (fraud_assessment), and nothing in the message favors one over the other.
- multi_intent: the message explicitly asks for two or more DIFFERENT actions in one message \
(e.g. both retrieving records AND running a fraud check) — not just one query with multiple details.

Key distinction: if the message only asks to retrieve/show/look up specific data (payments, returns, \
income, records), that is database_query even if it names a taxpayer — it is NOT unclear or multi_intent. \
Only classify as unclear when the requested ACTION itself is ambiguous (bare "check X" with no verb like \
"show"/"how much"/"suspicious"/"fraud"). Only classify as multi_intent when two distinct actions are both \
explicitly requested (e.g. one clause asks to show/retrieve something AND a separate clause asks to check \
for fraud/risk/suspicion).

Examples:
- "Check taxpayer 1002." -> unclear (no verb indicates whether this means records or fraud)
- "How much tax did taxpayer 1002 pay?" -> database_query (explicit retrieval verb)
- "Is taxpayer 1002 suspicious?" -> fraud_assessment (explicit fraud verb)
- "Show taxpayer 1002's payments and check whether they are suspicious." -> multi_intent \
(both "show payments" and "check suspicious" are explicit, distinct actions)

Respond only with the classification — do not answer the user's underlying question here."""


def classify_intent(query: str) -> IntentResult:
    return call_llm_structured(_SYSTEM_PROMPT, query, IntentResult)
