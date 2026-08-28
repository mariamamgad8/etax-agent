"""
Turns a database_query message into a structured, pre-authorized plan BEFORE
any SQL-generation LLM call — this is what lets the pipeline answer "my
share in Bright Future and City Medical" or reject "item_price for City
Medical Center" (a minority holding) without ever asking an LLM to write
SQL and hoping the views/AST validator catch the mistake afterward. Those
layers (RLS, security_invoker views, the AST allow-list in sql_runner.py)
remain the actual security backstop; this module exists to make the common
case *work correctly* and the forbidden case *fail immediately*, not to
replace them.

Two LLM-free, deterministic pieces do the security/business-logic-relevant
work, per this project's "LLMs interpret language, Python enforces
authorization" convention (see CLAUDE.md):
- resolve_company_mentions(): fuzzy-matches raw text company references
  against ONLY the authenticated user's own companies (from
  db.security.get_user_business_context) — never a global company search,
  so a non-match can never confirm or deny some other company's existence.
- authorize_plan(): checks each requested field/metric against the
  resolved companies' actual access_level, using the FIELDS/METRICS
  registries below — this is what makes forbidden_field immediate instead
  of "let the SQL LLM discover it".

One LLM call (extract_query_plan) does the genuinely language-dependent
part: figuring out which raw field/metric names and company mentions are
even present in free-form, possibly-Arabic, possibly-misspelled text. It is
constrained to a fixed vocabulary (the FIELDS/METRICS keys) and never
supplies a company_id, share, or access level itself — those always come
from get_user_business_context.
"""
import difflib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat.providers.llm import call_llm_structured

AccessLevel = Literal["majority", "minority"]

# --- business metrics / fields registry --------------------------------
# Every entry names which view/grain it lives in and the minimum access
# level a company must have for it to be queryable at all. "any" means both
# majority and minority owners may see it (e.g. taxes); "majority" means
# minority owners are always denied it (sales, anything item-level).

FIELDS: dict[str, dict] = {
    # ownership grain (tax.v_my_companies) — safe at any access level
    "company_name": {"grain": "ownership", "min_access": "any", "column": "company_name"},
    "company_activity": {"grain": "ownership", "min_access": "any", "column": "company_activity"},
    "share": {"grain": "ownership", "min_access": "any", "column": "share"},
    "access_level": {"grain": "ownership", "min_access": "any", "column": "access_level"},
    "taxpayer_name": {"grain": "ownership", "min_access": "any", "column": "taxpayer_name"},
    # transaction grain — taxes is available to both tiers, sales is majority-only
    "taxes": {"grain": "transactions", "min_access": "any", "column": "taxes"},
    "sales": {"grain": "transactions", "min_access": "majority", "column": "sales"},
    "transaction_id": {"grain": "transactions", "min_access": "any", "column": "transaction_id"},
    # Per-transaction tax rate — a derived ratio, not a literal view column
    # (see _sql_generation_prompt's handling of "derived_expr"). Requires
    # `sales`, which doesn't exist at all on the minority view, so this is
    # majority-only even though `taxes` alone is "any".
    "tax_rate": {
        "grain": "transactions",
        "min_access": "majority",
        "column": None,
        "derived_expr": "(taxes / NULLIF(sales, 0))",
    },
    # item grain — majority-only, full stop (no v_minority_items exists at all)
    "item_price": {"grain": "items", "min_access": "majority", "column": "item_price"},
    "quantity": {"grain": "items", "min_access": "majority", "column": "quantity"},
    "item_id": {"grain": "items", "min_access": "majority", "column": "item_id"},
}

METRICS: dict[str, dict] = {
    "total_sales": {"grain": "transactions", "min_access": "majority", "expr": "SUM(sales)"},
    "min_sale": {"grain": "transactions", "min_access": "majority", "expr": "MIN(sales)"},
    "max_sale": {"grain": "transactions", "min_access": "majority", "expr": "MAX(sales)"},
    "total_taxes": {"grain": "transactions", "min_access": "any", "expr": "SUM(taxes)"},
    "average_taxes": {"grain": "transactions", "min_access": "any", "expr": "AVG(taxes)"},
    "min_tax": {"grain": "transactions", "min_access": "any", "expr": "MIN(taxes)"},
    "max_tax": {"grain": "transactions", "min_access": "any", "expr": "MAX(taxes)"},
    "invoice_count": {"grain": "transactions", "min_access": "any", "expr": "COUNT(DISTINCT transaction_id)"},
    "units_sold": {"grain": "items", "min_access": "majority", "expr": "SUM(quantity)"},
    "average_item_price": {"grain": "items", "min_access": "majority", "expr": "AVG(item_price)"},
    "weighted_average_item_price": {
        "grain": "items",
        "min_access": "majority",
        "expr": "SUM(item_price * quantity) / NULLIF(SUM(quantity), 0)",
    },
}

# Fields whose value is computed, not a literal column on any view (see
# FIELDS["tax_rate"]) — _sql_generation_prompt lists these separately with
# their exact expression, since they won't appear in the reflected view
# columns the way ordinary fields do.
DERIVED_FIELDS = {name: spec for name, spec in FIELDS.items() if spec.get("derived_expr")}

# Which view backs each (grain, access_level) combination.
GRAIN_VIEWS: dict[tuple[str, AccessLevel], str] = {
    ("transactions", "majority"): "v_majority_transactions",
    ("transactions", "minority"): "v_minority_transactions",
    ("items", "majority"): "v_majority_items",
}
OWNERSHIP_VIEW = "v_my_companies"
OWNERSHIP_FIELDS = {name for name, spec in FIELDS.items() if spec["grain"] == "ownership"}


def _access_satisfies(access_level: AccessLevel, min_access: str) -> bool:
    if min_access == "any":
        return True
    return access_level == min_access  # only "majority" requires majority


# --- structured plan extraction (the one LLM call in this module) -------


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_mentions: list[str] = Field(
        default_factory=list,
        description="Raw text references to companies, exactly as the user wrote them (e.g. 'bright', "
        "'city medical center', 'Bright Futur Academy'). Empty if no specific company is named — "
        "the request then applies to every company the user owns shares in.",
    )
    wants_profile_info: bool = Field(
        default=False,
        description="True if the user is asking about their own taxpayer identity or an ownership "
        "summary (which companies they own, shares, activity, majority/minority) — nothing that "
        "requires transaction or item data.",
    )
    wants_fraud_status: bool = Field(
        default=False,
        description="True if the user is asking about the review status of their fraud-risk record "
        "(e.g. has it been checked, is it under review, was it confirmed) — not the risk score "
        "itself, just whether/how far along a human review of their data is.",
    )
    fields: list[str] = Field(
        default_factory=list,
        description=f"Requested raw fields, using ONLY these exact names: {', '.join(FIELDS)}.",
    )
    metrics: list[str] = Field(
        default_factory=list,
        description=f"Requested aggregate metrics, using ONLY these exact names: {', '.join(METRICS)}.",
    )


_PLAN_SYSTEM_PROMPT = f"""You extract a structured plan from a user's database question about their own \
tax/company records (the question may be in Arabic, English, or a mix, and may already be rephrased in \
English). You never decide access/authorization — only what the user is asking for.

company_mentions: copy the exact company name/reference text the user used, one entry per company \
mentioned. Leave empty if the user didn't name a specific company (e.g. "my total sales" with no \
company named).

fields — ONLY use names from this exact list: {', '.join(FIELDS)}
metrics — ONLY use names from this exact list: {', '.join(METRICS)}
Never invent a name outside those two lists. If the user's wording doesn't clearly map to one of them, \
leave it out rather than guessing.

wants_profile_info: true only if the user is asking about identity/ownership summary information \
(their taxpayer id/name, which companies they own, their shares, company activity, or which companies \
are majority vs minority) and nothing beyond that.

wants_fraud_status: true only if the user is asking whether/how far along their fraud-risk record has \
been reviewed (e.g. "has anyone checked my data", "is my review done yet") — not the risk score itself, \
and not a request to run a new assessment.

Examples:
- "get me each item sold, price, quantity for taxpayer id 2" -> fields: [item_id, item_price, quantity] \
(the "taxpayer id 2" mention is never trusted for authorization — see the caller)
- "i want to know the amount of shares i have in Bright future academy and city medical center" -> \
company_mentions: ["Bright future academy", "city medical center"], fields: [share]
- "i want to get the sales and item sold for bright future" -> company_mentions: ["bright future"], \
metrics: [total_sales, units_sold] ("item sold" asks how many units were sold — units_sold — not which \
item IDs exist; only use the item_id field when the user wants the identifiers themselves, e.g. "which items")
- "get me the avg taxes between both of my companies" -> metrics: [average_taxes]
- "which of my companies is majority" -> wants_profile_info: true, fields: [company_name, access_level]
- "what is my taxpayer id" -> wants_profile_info: true
- "has my tax record been reviewed yet" -> wants_fraud_status: true
- "what's the status of my fraud review" -> wants_fraud_status: true
- "get me the percentage of the taxes from every sale in bright future" / "هاتلي نسبة الضريبة لكل بيعة من \
سعرها في bright future" -> company_mentions: ["bright future"], fields: [tax_rate] (a per-sale ratio — use \
the tax_rate field, never compute or state a percentage yourself)
- "what about the minimum sale transaction" -> metrics: [min_sale]
- "get me the max tax" -> metrics: [max_tax]

Arabic examples (the same vocabulary applies regardless of language — never leave fields/metrics empty \
just because the question is in Arabic):
- "عايز اعرف سعر القطعة وكمية اللي اتباع منها في برايت فيوتشر" -> company_mentions: ["برايت فيوتشر"], \
fields: [item_price, quantity]
- "عايز اشوف ضرايبي" -> fields: [taxes]
- "عايز اشوف ضرايبي في شركاتي" -> fields: [taxes]
- "هاتلي نسبة الضريبة لكل بيعة من سعرها" -> fields: [tax_rate]

Respond only with the structured plan — do not answer the user's question here."""


def extract_query_plan(question_en: str) -> QueryPlan:
    return call_llm_structured(_PLAN_SYSTEM_PROMPT, question_en, QueryPlan)


# --- entity resolution (deterministic, never an LLM call) ---------------


def resolve_company_mentions(mentions: list[str], companies: list[dict]) -> dict:
    """
    Matches each raw text mention against ONLY `companies` (the
    authenticated user's own list from get_user_business_context) — never a
    global lookup, so an unresolved mention can never confirm or deny that
    some other company exists in the wider tax schema.

    Returns {
        "resolved": list[dict],                                   # unique company dicts, deduplicated
        "ambiguous": list[{"mention": str, "candidates": list[dict]}],
        "unresolved": list[str],
    }
    """
    resolved: list[dict] = []
    ambiguous: list[dict] = []
    unresolved: list[str] = []
    resolved_ids: set[int] = set()

    def _add(company: dict) -> None:
        if company["company_id"] not in resolved_ids:
            resolved.append(company)
            resolved_ids.add(company["company_id"])

    for mention in mentions:
        normalized = mention.strip().lower()
        if not normalized:
            continue

        exact = [c for c in companies if c["company_name"].strip().lower() == normalized]
        if len(exact) == 1:
            _add(exact[0])
            continue

        # Substring containment handles "bright" / "bright company" ->
        # "Bright Future Academy" — strip generic suffixes so "bright
        # company" still contains-matches even though the real name has no
        # "company" in it.
        cleaned = normalized
        for suffix in (" company", " corp", " corporation", " inc", " ltd"):
            cleaned = cleaned.replace(suffix, "")
        cleaned = cleaned.strip()
        contains = [
            c
            for c in companies
            if cleaned and (cleaned in c["company_name"].lower() or c["company_name"].lower() in normalized)
        ]
        if len(contains) == 1:
            _add(contains[0])
            continue
        if len(contains) > 1:
            ambiguous.append({"mention": mention, "candidates": contains})
            continue

        # Fuzzy match for misspellings (e.g. "Bright Futur Academy").
        scored = sorted(
            ((difflib.SequenceMatcher(None, normalized, c["company_name"].lower()).ratio(), c) for c in companies),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score = scored[0][0] if scored else 0.0
        if best_score >= 0.6:
            close = [c for score, c in scored if score >= best_score - 0.1]
            if len(close) == 1:
                _add(close[0])
                continue
            ambiguous.append({"mention": mention, "candidates": close})
            continue

        unresolved.append(mention)

    return {"resolved": resolved, "ambiguous": ambiguous, "unresolved": unresolved}


# --- authorization-before-SQL --------------------------------------------


def authorize_plan(plan: QueryPlan, context: dict) -> dict:
    """
    Resolves company_mentions and checks every requested field/metric
    against the resolved companies' actual access_level — all from
    `context` (get_user_business_context's output), never from the plan's
    own text. Returns one of:

        {"decision": "ambiguous_entity", "mention": str, "candidates": [...]}
        {"decision": "forbidden_entity", "mentions": [...]}
        {"decision": "forbidden_field", "field": str, "company_name": str, "access_level": str}
        {"decision": "empty_result"}   # nothing left to query (e.g. only
                                        # majority-only fields asked with no
                                        # majority company in context)
        {"decision": "direct_answer", "companies": [...]}   # answerable
                                        # from context alone, no SQL needed
        {"decision": "fraud_status", "review_status": str | None}   # answerable
                                        # from context alone, no SQL, and
                                        # entirely unrelated to companies
        {"decision": "unclear"}        # the plan captured nothing actionable
                                        # at all (no fields/metrics/profile/
                                        # fraud-status ask) — the wording
                                        # didn't map onto the fixed vocabulary
        {"decision": "proceed", "companies": [...], "fields": [...],
         "metrics": [...], "excluded_companies": [...]}  # ready for SQL
                                        # generation; excluded_companies lists
                                        # any of the user's OWN companies that
                                        # got silently dropped from an
                                        # implicit (no-company-named) request
                                        # because they don't meet the min
                                        # access level for what was asked —
                                        # empty unless that happened, so
                                        # db_response can tell the user rather
                                        # than answering as if they'd only
                                        # ever owned the companies that qualified
    """
    # fraud_review_status is a direct user_id link (see FraudRecord's
    # docstring), never scoped to a company — short-circuit before any
    # company resolution, same as the ownership-only "direct_answer" case.
    if plan.wants_fraud_status:
        return {"decision": "fraud_status", "review_status": context.get("fraud_review_status")}

    companies = context["companies"]
    requested_fields = [f for f in plan.fields if f in FIELDS]
    requested_metrics = [m for m in plan.metrics if m in METRICS]

    # The plan captured NOTHING actionable at all — not a profile/fraud-status
    # question, no fields, no metrics. This happens when the user's wording
    # (e.g. "avg taxes", before average_taxes existed in METRICS) doesn't map
    # onto the fixed vocabulary and extract_query_plan correctly declines to
    # guess. Must be caught here, BEFORE the ownership-fields check below —
    # `all(... for f in [])` is vacuously True on an empty list, which used to
    # silently misread "nothing requested" as "only asking about ownership
    # info" and answer with the ownership table instead of admitting it
    # didn't understand the request.
    if not requested_fields and not requested_metrics and not plan.wants_profile_info:
        return {"decision": "unclear"}

    explicit_targets = bool(plan.company_mentions)
    if explicit_targets:
        resolution = resolve_company_mentions(plan.company_mentions, companies)
        if resolution["ambiguous"]:
            first = resolution["ambiguous"][0]
            return {"decision": "ambiguous_entity", "mention": first["mention"], "candidates": first["candidates"]}
        if not resolution["resolved"]:
            return {"decision": "forbidden_entity", "mentions": resolution["unresolved"]}
        target_companies = resolution["resolved"]
    else:
        target_companies = companies

    if not target_companies:
        return {"decision": "empty_result"}

    # Nothing beyond company identity/ownership info requested -> answer
    # directly from context, never touch SQL generation at all. requested_fields
    # is guaranteed non-empty here whenever it's the deciding factor (the
    # all-empty case was already returned as "unclear" above), so this no
    # longer risks the vacuous-truth bug that used to treat "nothing asked"
    # as "only ownership info asked".
    only_ownership_fields = bool(requested_fields) and all(f in OWNERSHIP_FIELDS for f in requested_fields)
    if not requested_metrics and (plan.wants_profile_info or only_ownership_fields):
        return {"decision": "direct_answer", "companies": target_companies}

    if explicit_targets:
        # The user named specific companies — a field/metric forbidden for
        # any of them is answered immediately, never handed to the SQL LLM.
        for company in target_companies:
            for field in requested_fields:
                if not _access_satisfies(company["access_level"], FIELDS[field]["min_access"]):
                    return {
                        "decision": "forbidden_field",
                        "field": field,
                        "company_name": company["company_name"],
                        "access_level": company["access_level"],
                    }
            for metric in requested_metrics:
                if not _access_satisfies(company["access_level"], METRICS[metric]["min_access"]):
                    return {
                        "decision": "forbidden_field",
                        "field": metric,
                        "company_name": company["company_name"],
                        "access_level": company["access_level"],
                    }
        return {
            "decision": "proceed",
            "companies": target_companies,
            "fields": requested_fields,
            "metrics": requested_metrics,
            "excluded_companies": [],
        }

    # No company named — a portfolio-wide request silently scopes to
    # whichever owned companies actually qualify (e.g. "my total sales"
    # only ever applies to majority holdings) rather than erroring — but the
    # companies that got dropped are reported back so the caller can tell the
    # user, rather than silently answering as if those companies didn't exist.
    needed_levels = [FIELDS[f]["min_access"] for f in requested_fields] + [METRICS[m]["min_access"] for m in requested_metrics]
    excluded_companies: list[dict] = []
    if needed_levels and all(level == "majority" for level in needed_levels):
        excluded_companies = [c for c in target_companies if c["access_level"] != "majority"]
        target_companies = [c for c in target_companies if c["access_level"] == "majority"]
    if not target_companies:
        return {"decision": "empty_result"}

    return {
        "decision": "proceed",
        "companies": target_companies,
        "fields": requested_fields,
        "metrics": requested_metrics,
        "excluded_companies": excluded_companies,
    }
