"""Manual smoke test for the intent classifier — not a pytest suite, just a
quick live-provider check to run during development:
    docker compose exec backend python -m app.chat._manual_test_intent

CASES below exercise classify_intent directly (the LLM prompt alone,
bypassing graph.route_intent's deterministic pre-router) — this is
deliberate: it verifies prompt quality independently of the pre-router
safety net. "Check taxpayer 1002." is expected "unclear" here because bare
"check" is intentionally NOT one of the prompt's LLM-level fraud signal
words (too generic to hand the model as a strong cue); in the real graph,
graph.route_intent's keyword pre-router catches it deterministically before
the classifier ever runs — see PREROUTER_CASES below, which exercises that
full path instead.
"""
from app.chat.graph import route_intent
from app.chat.intent import classify_intent

CASES = [
    ("Hi", "greeting"),
    ("Hello there!", "greeting"),
    ("مرحبا", "greeting"),
    ("السلام عليكم", "greeting"),
    ("Good morning, hope you're doing well today.", "greeting"),
    ("Hi, show me my company's taxes.", "database_query"),
    ("Hello, is this company suspicious?", "fraud_assessment"),
    ("Is taxpayer 1002 suspicious? Check them for fraud.", "fraud_assessment"),
    ("هل الممول ده safe ولا suspicious؟", "fraud_assessment"),
    ("want to assess my company", "fraud_assessment"),
    ("عايز اعرف رأي سليم ولا محتاج أشوف متخصص يفحصه لي، عشان أتأكد أمشي في الإجراءات ولا أراجع الورق.", "fraud_assessment"),
    ("عايز اشوف ورق الشركة بتاعتي سليم ولا في مشكلة", "fraud_assessment"),
    ("How much tax did taxpayer 1002 pay in 2025?", "database_query"),
    ("عايز أعرف الممول 1002 دفع ضرايب كام سنة 2025", "database_query"),
    ("Show me all Cairo taxpayers.", "database_query"),
    ("I want to know how much share I have in my company.", "database_query"),
    ("Who are you? What can you do?", "other"),
    ("انت بتعمل ايه؟", "other"),
    ("What is VAT?", "other"),
    ("Who won the football match yesterday?", "other"),
    ("Check taxpayer 1002.", "unclear"),
    ("Show taxpayer 1002's payments and check whether they are suspicious.", "multi_intent"),
]

# Real failures observed in production logs, now caught deterministically by
# graph.route_intent's pre-router before the classifier ever runs — see
# graph.py's route_intent / test_fraud_intent_prerouter.py for the full
# design. Exercised here via route_intent (not classify_intent) to prove the
# actual fix, since these previously landed on tax_conversation/
# database_query/unclear despite being unambiguous fraud requests.
PREROUTER_CASES = [
    ("check fraud", "fraud_assessment"),
    ("want to assess my company", "fraud_assessment"),
    ("عايز اشوف ورق الشلركة بتاعتي سليم ولا في مشكلة", "fraud_assessment"),
    (
        "اهلا عايز اشوف صحة ضرايبي Row 7: Net_Profit: 154864.67 Taxable_Income: 141487.4 "
        "Declared_Tax: 28708.52 Previous_Violations: 2 Cash_Transactions_Percentage: 40.34 "
        "Invoice_Mismatch: 0 Tax_Gap: 3126.15 Industry_Risk_ord: High",
        "fraud_assessment",
    ),
]

if __name__ == "__main__":
    passed = 0
    for query, expected in CASES:
        result = classify_intent(query)
        ok = result.intent == expected
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] expected={expected:<20} got={result.intent:<20} conf={result.confidence:.2f}  {query!r}")
        if not ok:
            print(f"         reasoning: {result.reasoning}")
    print(f"\n{passed}/{len(CASES)} passed (classify_intent only)")

    pre_passed = 0
    print("\n--- deterministic pre-router cases (via route_intent) ---")
    for query, expected in PREROUTER_CASES:
        state = route_intent({"normalized_query": query, "original_query": query})
        ok = state["intent"] == expected
        pre_passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] expected={expected:<20} got={state['intent']:<20}  {query!r}")
    print(f"\n{pre_passed}/{len(PREROUTER_CASES)} passed (pre-router)")
