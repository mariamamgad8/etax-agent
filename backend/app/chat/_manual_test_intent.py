"""Manual smoke test for the intent classifier — not a pytest suite, just a
quick live-provider check to run during milestone-1 development:
    docker compose exec backend python -m app.chat._manual_test_intent
"""
from app.chat.intent import classify_intent

CASES = [
    ("Is taxpayer 1002 suspicious? Check them for fraud.", "fraud_assessment"),
    ("هل الممول ده safe ولا suspicious؟", "fraud_assessment"),
    ("How much tax did taxpayer 1002 pay in 2025?", "database_query"),
    ("عايز أعرف الممول 1002 دفع ضرايب كام سنة 2025", "database_query"),
    ("Show me all Cairo taxpayers.", "database_query"),
    ("Who are you? What can you do?", "assistant_identity"),
    ("انت بتعمل ايه؟", "assistant_identity"),
    ("What is VAT?", "tax_conversation"),
    ("اشرحلي الفرق بين expected tax و declared tax", "tax_conversation"),
    ("Who won the football match yesterday?", "off_topic"),
    ("What's the best pizza topping?", "off_topic"),
    ("Check taxpayer 1002.", "unclear"),
    ("Show taxpayer 1002's payments and check whether they are suspicious.", "multi_intent"),
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
    print(f"\n{passed}/{len(CASES)} passed")
