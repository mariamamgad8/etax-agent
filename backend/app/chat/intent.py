from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat.providers.llm import call_llm_structured

# Reduced from an earlier 8-intent set: assistant_identity/tax_conversation/
# off_topic were collapsed into a single "other" — production logs showed
# the LLM classifier unreliably splitting those three apart, and worse,
# sometimes routing a real fraud_assessment or database_query request into
# tax_conversation/unclear instead (e.g. "عايز اشوف ورق الشركة بتاعتي سليم
# ولا في مشكلة" — obviously fraud_assessment — landed on database_query; a
# pasted feature dump with no framing sentence landed on the tax_conversation
# placeholder). See graph.py's route_intent for the deterministic pre-router
# that now catches the highest-confidence fraud signals (a pasted field:value
# dump, or an explicit fraud-leaning keyword) before ever calling this model.
Intent = Literal[
    "greeting",
    "fraud_assessment",
    "database_query",
    "other",
    "unclear",
    "multi_intent",
]

# The LLM only ever says which intent it thinks this is — routing to an
# actual node is a Python lookup, never left to the model's judgment.
INTENT_ROUTING: dict[str, str] = {
    "greeting": "greeting",
    "fraud_assessment": "load_fraud_record",
    "database_query": "prepare_db_question",
    "other": "other",
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

- greeting: a greeting, salutation, or simple conversation opener with NO substantive request attached \
(e.g. "Hi", "Hello", "Hey", "مرحبا", "أهلاً", "السلام عليكم") — nothing else is being asked for.
- fraud_assessment: the user wants a fraud/risk/suspicion check run on a taxpayer or business — \
including asking whether their own papers/records/filings are "fine", "correct", "clean", or "have a \
problem", asking to "verify"/"double-check" their tax situation, mentioning tax evasion, or pasting \
raw feature values (e.g. "Net_Profit: 50000 Tax_Gap: 3000 ...") with no other framing. \
Strong signal words/phrases (Arabic or English, in any mix): سليم, اوراق/أوراق, ورق الشركة, فحص, \
تهرب ضريبي, اتاكد من اوراقي, مشتبه, احتيال, مخاطر, assess, assessment, fraud, suspicious, risk, \
detect, sus. Treat these as strong evidence for fraud_assessment even if the sentence also mentions \
"tax" generically — do NOT downgrade this to database_query or a general/other question just because \
the word "tax" or "records" also appears; the ACTION being requested (a risk/soundness check) is what \
matters, not the noun it's attached to.
- database_query: the user wants to look up specific stored tax records/data already on file — \
payments, returns, income, ownership share, transactions, invoices, taxpayer/company info, item \
prices/quantities sold. Signal verbs (English): retrieve, query, get me, give me, show me, "how much", \
"what is my share". Signal verbs/phrases (Arabic — just as strong a signal as the English ones, do NOT \
require an English verb to be present): عايز اعرف, عايز اشوف, هاتلي, وريني, ابعتلي, كام, قد ايه. \
This is about reading back a stored fact, not judging whether something is correct/risky — an Arabic \
question naming an item/price/quantity/tax/company is database_query exactly like its English \
equivalent, never "other" just because it's phrased casually or in Arabic.
- other: anything that isn't one of the above and isn't ambiguous between them — the user is asking \
who/what the assistant is, asking something unrelated to tax/fraud/records, or asking a general tax \
question not tied to their own stored records or a risk check. When genuinely unsure whether a vague \
tax-adjacent question leans toward fraud_assessment or database_query, prefer unclear over other.
- unclear: names a taxpayer/company and asks to "look into" them with NO further detail on what kind \
of check, AND none of the fraud_assessment signal words above are present — this could equally mean \
"look up their records" or "assess their fraud risk".
- multi_intent: the message explicitly asks for two or more DIFFERENT actions in one message \
(e.g. both retrieving records AND running a fraud check) — not just one request with multiple details.

Key distinction: if the message only asks to retrieve/show/look up specific data (payments, returns, \
income, records), that is database_query even if it names a taxpayer — it is NOT unclear or other. \
Only classify as multi_intent when two distinct actions are both explicitly requested (e.g. one clause \
asks to show/retrieve something AND a separate clause asks to check for fraud/risk/suspicion).

Critical: a greeting attached to a substantive request is NOT greeting — classify by the request itself. \
Only classify as greeting when the ENTIRE message is just the opener, with nothing else being asked.

Examples:
- "Hi" / "Hello" / "مرحبا" / "السلام عليكم" -> greeting (nothing else requested)
- "Hi, show me my company's taxes." -> database_query (a substantive request follows the greeting — not greeting)
- "Hello, is this company suspicious?" -> fraud_assessment (same reasoning — the greeting is just an opener)
- "How much tax did taxpayer 1002 pay?" -> database_query (explicit retrieval verb)
- "I want to know how much share I have in my company." -> database_query (a stored ownership fact, not a risk judgment)
- "عايز اعرف سعر القطعة وكمية اللي اتباع منها في برايت فيوتشر" -> database_query (asking for a stored item price/quantity — NOT other, even with no English retrieval verb present)
- "عايز اشوف ضرايبي في شركاتي" -> database_query (asking to see stored tax data)
- "Is taxpayer 1002 suspicious?" -> fraud_assessment (explicit fraud verb)
- "want to assess my company" / "check fraud" -> fraud_assessment (explicit fraud-assessment verb)
- "عايز اعرف رأي سليم ولا محتاج أشوف متخصص يفحصه لي" -> fraud_assessment ("سليم"/"يفحصه" = a soundness/risk check, not a data lookup)
- "عايز اشوف ورق الشركة بتاعتي سليم ولا في مشكلة" -> fraud_assessment ("ورق الشركة" + "سليم" + "مشكلة" = asking whether their filings are sound, not asking to view stored records verbatim)
- "Net_Profit: 50000 Tax_Gap: 3000 Industry_Risk: High" (raw values, no other framing) -> fraud_assessment
- "Show taxpayer 1002's payments and check whether they are suspicious." -> multi_intent \
(both "show payments" and "check suspicious" are explicit, distinct actions)
- "Who are you? What can you do?" -> other
- "What's the weather like?" -> other

If a "Previous question" is given below for context: a short follow-up that only makes sense as \
continuing that same stored-data lookup (e.g. "what about the taxes" right after a question about sales \
for a specific company) is still database_query — classify by what the conversation is actually about, \
not just the new message in isolation. Only use the previous question to resolve an otherwise-ambiguous \
follow-up like this; if the new message stands on its own or is clearly a different kind of request, \
classify it normally and ignore the previous question.

Respond only with the classification — do not answer the user's underlying question here."""


def classify_intent(query: str, previous_db_question: str | None = None) -> IntentResult:
    user_prompt = query
    if previous_db_question:
        user_prompt = f'Previous question in this conversation (context only): "{previous_db_question}"\n\nNew message: {query}'
    return call_llm_structured(_SYSTEM_PROMPT, user_prompt, IntentResult)
