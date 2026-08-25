"""
Deterministic (non-LLM) response templates, plus the single deterministic
per-turn language detector every node reads from (never recomputed
mid-turn — see graph.py's route_intent, which is the only place
detect_response_language is called for a live request).

Language codes are short ("en"/"ar") to match AgentState.response_language
exactly; LANGUAGE_NAMES maps them to the human-readable name the
LLM-generated-prose prompts in graph.py need (e.g. "Write ... in Arabic").
"""
import random
import re

# Arabic Unicode block — same range used to detect "does this text contain
# Arabic script" throughout the project (previously graph.py's db_response
# used a presence check; this module upgrades that to a dominant-language
# count so a handful of embedded Arabic/English technical terms — company
# names, VAT, taxpayer IDs — don't flip the whole reply's language).
_ARABIC_CHARS = re.compile(r"[؀-ۿ]")
_LATIN_CHARS = re.compile(r"[A-Za-z]")

LANGUAGE_NAMES = {"en": "English", "ar": "Arabic"}


def detect_response_language(text: str) -> str:
    """
    Returns 'ar' or 'en' — the dominant natural language by script character
    count, not mere presence. A message that's mostly English with one Arabic
    company name stays English; a mostly-Arabic message with "VAT"/"SQL"-style
    English technical terms stays Arabic. Ties and scripts we don't
    distinguish (pure numbers/IDs) default to English.
    """
    arabic_count = len(_ARABIC_CHARS.findall(text))
    latin_count = len(_LATIN_CHARS.findall(text))
    return "ar" if arabic_count > latin_count else "en"


def pick_template(pool: list[str]) -> str:
    return random.choice(pool)


GREETING_TEMPLATES: dict[str, list[str]] = {
    "en": [
        "Hi! I can look up tax and company records you're authorized to access, or run a "
        "fraud-risk assessment on a business. Which would you like to do?",
        "Hello there. I'm the eTax assistant — I can pull up authorized tax/company records for "
        "you, or assess a company for fraud risk. What can I help with?",
        "Hey! Happy to help — I can either retrieve tax records you have access to, or run a "
        "fraud-risk check on a company. Which one do you need?",
        "Hi, welcome. I handle two things here: looking up tax/company data you're authorized "
        "for, and fraud-risk assessments. Just let me know which one you're after.",
    ],
    "ar": [
        "أهلاً! أقدر أطلعلك على بيانات الضرائب والشركات اللي عندك صلاحية عليها، أو أعمل تقييم "
        "لمخاطر الاحتيال لشركة معينة. تحب تبدأ بإيه؟",
        "مرحباً بيك. أنا مساعد eTax — أقدر أساعدك في استرجاع سجلات ضريبية مصرح لك بيها، أو "
        "تقييم مخاطر احتيال لشركة. إزاي أقدر أساعدك؟",
        "أهلاً وسهلاً! ممكن أجيبلك بيانات ضريبية أنت مصرح ليك بيها، أو أعمل فحص لمخاطر الاحتيال "
        "لشركة. أي واحدة محتاجها؟",
        "السلام عليكم! أقدر أساعدك في حاجتين: عرض بيانات ضريبية أنت مسموحلك بيها، أو تقييم "
        "مخاطر احتيال لشركة. قولّي تحب أبدأ بإيه.",
    ],
}

# Catch-all for assistant_identity + off_topic + general tax conversation —
# collapsed into one intent (see intent.py) after production logs showed the
# LLM classifier unreliably splitting these three apart and, worse,
# sometimes using one of them to swallow a real fraud_assessment/
# database_query request. A single neutral "here's what I actually do"
# reply works for "who are you", an off-topic question, and a vague/general
# tax question alike, and never pretends to answer something out of scope.
OTHER_TEMPLATES: dict[str, list[str]] = {
    "en": [
        "I'm the eTax assistant. I can retrieve tax and company records you're authorized to "
        "access, and run a fraud-risk assessment on a business — let me know which one you need.",
        "I'm eTax's assistant — I handle two things: authorized tax/company record lookups and "
        "fraud-risk assessments. What would you like to do?",
        "That's outside what I can answer directly, but I can look up tax records you're "
        "authorized to access or run a fraud-risk assessment on a company. Which one do you need?",
        "I help with two things: looking up tax records you have access to, and assessing "
        "companies for fraud risk. Ask me for either whenever you need.",
    ],
    "ar": [
        "أنا مساعد eTax. بقدر أطلعلك على بيانات الضرائب والشركات اللي عندك صلاحية عليها، وكمان "
        "أعمل تقييم لمخاطر الاحتيال لأي شركة — قولّي محتاج إيه منهم.",
        "أنا المساعد الخاص بمنصة eTax — شغلي الأساسي إني أجيب بيانات ضريبية أنت مصرح بيها، "
        "وأعمل تقييمات لمخاطر الاحتيال للشركات. تحب تبدأ بإيه؟",
        "ده مش من ضمن اللي أقدر أجاوب عليه مباشرة، بس أقدر أطلعلك على بيانات ضريبية أنت مصرح "
        "بيها، أو أعمل تقييم مخاطر احتيال لشركة. أي واحدة محتاجها؟",
        "بساعدك في حاجتين رئيسيتين: عرض السجلات الضريبية اللي عندك صلاحية عليها، وتقييم مخاطر "
        "الاحتيال للشركات. اطلب أي واحدة تحتاجها.",
    ],
}

CLARIFY_INTENT_TEMPLATES: dict[str, list[str]] = {
    "en": [
        "Could you clarify what you'd like — retrieving tax information, or a fraud-risk check?",
    ],
    "ar": [
        "ممكن توضح أكتر إيه اللي محتاجه — استرجاع بيانات ضريبية، ولا تقييم مخاطر احتيال؟",
    ],
}

MULTI_INTENT_TEMPLATES: dict[str, list[str]] = {
    "en": [
        "That looks like more than one request. Which would you like first: "
        "1) retrieve tax information, or 2) a fraud-risk assessment?",
    ],
    "ar": [
        "يبدو إن ده أكتر من طلب. تحب تبدأ بإيه الأول: 1) استرجاع بيانات ضريبية، "
        "ولا 2) تقييم مخاطر احتيال؟",
    ],
}


# --- fraud result text (see fraud/engine.py's tier/label vocabulary) --------

FRAUD_TIER_NAMES = {
    "en": {"Standard Assessment": "Standard Assessment", "Comprehensive Assessment": "Comprehensive Assessment"},
    "ar": {"Standard Assessment": "التقييم القياسي", "Comprehensive Assessment": "التقييم الشامل"},
}
FRAUD_LABEL_NAMES = {
    "en": {"Suspicious": "Suspicious", "Not suspicious": "Not suspicious"},
    "ar": {"Suspicious": "مشتبه به", "Not suspicious": "غير مشتبه به"},
}


def build_fraud_result_text(
    language: str,
    tier: str,
    fields_provided: int,
    fields_total: int,
    label: str,
    probability: float,
    threshold: float,
) -> str:
    """
    Localizes the fraud-assessment result sentence. `tier`/`label` are the
    fixed English tokens fraud/engine.py returns internally (its own
    contract is untouched — see fraud/engine.py's STANDARD_TIER/
    COMPREHENSIVE_TIER and predict()'s "label" field) — only the final
    user-facing sentence is translated here.
    """
    tier_name = FRAUD_TIER_NAMES[language][tier]
    label_name = FRAUD_LABEL_NAMES[language][label]
    if language == "ar":
        return (
            f"اكتمل {tier_name} بناءً على {fields_provided} من {fields_total} حقلًا — النتيجة: "
            f"\"{label_name}\" (الدرجة {probability:.2f} من مقياس 0.00 إلى 1.00، حد المراجعة "
            f"{threshold:.2f}). الدرجة الأعلى من حد المراجعة لا تؤكد وجود احتيال — يُرجى إحالة "
            "الحالة للمراجعة اليدوية قبل اتخاذ أي إجراء."
        )
    return (
        f"{tier_name} complete, based on {fields_provided} of {fields_total} fields provided — result: "
        f"\"{label_name}\" (score {probability:.2f} on a 0.00-1.00 scale, review threshold {threshold:.2f}). "
        "A score above the review threshold does not confirm fraud — refer the case for manual "
        "review before taking any action."
    )
