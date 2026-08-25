# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

eTax is an AI-assisted tax platform: users sign up, verify with face biometrics, then use a chatbot to query tax records, run fraud-risk assessment, and ask general tax questions. Backend is FastAPI (`backend/`), frontend is React+Vite (`frontend/`), primary datastore is PostgreSQL+pgvector, orchestrated via Docker Compose. `backend/app/face/` (InsightFace/ArcFace `buffalo_l` + MiniFASNetV2 liveness) is a standalone face-recognition implementation with no external package dependency. `system_design_UI.zip` is the source design system the frontend was ported from.

## Commands

### Run everything

```bash
cp .env.example .env   # then set a real JWT_SECRET_KEY, and for the chatbot: COHERE_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, ELEVENLABS_TTS_KEY
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend / Swagger docs: http://localhost:8000/docs
- Postgres: localhost:5432
- pgAdmin: http://localhost:5050 (admin@etax.com / admin123)

First backend build takes a while — it bakes in the InsightFace and MiniFASNetV2 models at build time.

### Dev loop

- The `backend` and `frontend` services bind-mount their source (`backend/app`, `frontend/src`/`public`/`index.html`) and run with hot-reload (`uvicorn --reload`, Vite dev server), so most code edits take effect without a rebuild — just save the file.
- To add a new Python dependency: `docker compose exec backend pip install --no-cache-dir <pkg>` for fast iteration, then add the exact resolved version to `backend/requirements.txt` and run `docker compose build backend` once to confirm a clean rebuild reproduces it.
- **Docker env vars are fixed at container creation**, not read live from `.env`/`docker-compose.yml`. After editing either, run `docker compose up -d <service>` (recreates the container when the resolved config changed) — `docker compose restart <service>` does **not** pick up the change.
- Manual live-provider smoke test (needs real API keys in `.env`, makes real Groq/Gemini calls, not mocked):
  ```bash
  docker compose exec backend python -m app.chat._manual_test_intent
  ```

### Frontend only

```bash
cd frontend && npm install
npm run dev       # Vite dev server
npm run build     # production build
npm run preview
```

### Tests

`backend/tests/` (pytest) runs against the real Postgres container — there's no separate test database or mocking layer for the DB yet, so `db` must be up first:

```bash
docker compose exec backend pytest
```

`backend/app/chat/_manual_test_intent.py` is a separate, older live-API smoke test (not part of the pytest suite): `docker compose exec backend python -m app.chat._manual_test_intent`. No frontend test suite or linter is configured yet.

`tests/test_sql_security.py` is the adversarial suite for the ownership-aware SQL security layer (no-owner/minority/majority/mixed access, prompt-injection resistance, RLS row leakage, transaction-local identity) — most of it monkeypatches `call_llm_text` with hand-crafted "what a malicious/incorrect LLM output would look like" SQL strings rather than depending on real LLM behavior, since the whole point is that these defenses hold regardless of what the model produces.

`tests/test_fraud_model_routing.py` covers the 8-feature/23-feature model routing (exact field count, never partial+imputed), the required/optional field split, `/chat/fraud/extract`'s merge behavior, and that a missing required field raises rather than silently defaults.

## Architecture

### One PostgreSQL database, two schemas

Everything lives in a single Postgres+pgvector database (`app.config.DATABASE_URL` / `app.chat.config`'s tax-schema code share the same connection — see `backend/app/database/db.py`'s `engine`). There is no SQLite anywhere in the runtime path anymore.

- **`auth` schema** (`backend/app/database/models.py`) — `users`, `face_profiles` (512-d ArcFace embeddings, compared via pgvector cosine distance).
- **`tax` schema** (`backend/app/database/tax_models.py`) — `taxpayers`, `companies`, `company_owners` (many-to-many ownership, `share` a 0..1 fraction, `CHECK (share >= 0 AND share <= 1)`), `transactions`, `items`. `taxpayers.user_id` is nullable — a taxpayer can exist without ever signing up — and FKs to `auth.users.id` are schema-qualified (e.g. `ForeignKey("auth.users.id")`), which SQLAlchemy resolves fine across schemas in the same database.
- **Ownership-aware authorization is real, not advisory** — see "Ownership-aware SQL security" below. Permission is per company (`company_owners.share`), never a single global tier: the same user can hold majority in one company and minority in another at once.
- Both schemas (and the `vector` extension) are created idempotently by `init_db()` in `backend/app/database/db.py` — there's no Alembic/versioned migration tool; `Base.metadata.create_all()` is the whole "migration mechanism," consistent with how this repo already worked before the schema split.
- The chatbot's demo/example tax data is loaded by `backend/app/chat/db/seed.py`'s `ensure_ready()` (called from `main.py`'s startup hook, idempotent — no-ops once `tax.companies` has rows). It's the literal small sample dataset (3 companies, 5 transactions, 5 items) supplied for development, not generated/invented records — real seed/import data replaces it separately. Note: rows are inserted with explicit ids, which does **not** advance the underlying `SERIAL` sequence, so `seed()` resets it via `setval()` after inserting — omitting that step causes the next auto-generated id to collide with an already-used one (hit this live once).

### Staged authentication (JWT `stage` claim)

Password login and face verification are two independent steps enforced by the backend on every request — not just hidden by frontend routing:

```
POST /auth/signup  → stage=pending_enrollment token
POST /face/enroll  → stage=authenticated token   (liveness-gated)
POST /auth/login   → stage=face_required token   (or pending_enrollment if never enrolled)
POST /face/verify  → stage=authenticated token   (liveness-gated, matched only against the token's own user)
GET  /auth/me      → requires stage=authenticated
```

Each stage token only unlocks its matching endpoint — see `backend/app/auth/dependencies.py`'s `require_stage`/`require_pending_enrollment`/`require_face_required`/`require_authenticated`. `/face/verify` never runs a nearest-neighbor search across all enrolled users; it fetches only the embedding belonging to the `sub` user in the token and compares against that one record.

Frontend mirrors this in `auth/AuthContext.jsx` (stores the stage) and `auth/ProtectedRoute.jsx` (gates routes by stage), but that's UX only — the backend enforces the same staging independently.

### Chatbot agent (`backend/app/chat/`)

A LangGraph state machine (`graph.py`) behind `POST /chat/message`, using a single `AgentState` TypedDict (`state.py`). `route_intent` classifies the message into one of **6** intents (`greeting`, `fraud_assessment`, `database_query`, `other`, `unclear`, `multi_intent` — `intent.py`'s `INTENT_ROUTING` table; the LLM only names the intent, a Python dict decides which node runs, never the model). This was cut down from an earlier 8-intent set (`assistant_identity`/`tax_conversation`/`off_topic` collapsed into `other`) after production logs showed the classifier unreliably splitting those three apart and — worse — sometimes using one of them to swallow a real `fraud_assessment`/`database_query` request (e.g. a pasted feature dump landing on the `tax_conversation` placeholder). `route_intent` also runs a **deterministic pre-router** before ever calling the LLM, in priority order: (1) an obvious standalone greeting (exact match against a normalized allow-list, e.g. "Hi"/"مرحبا" — never a prefix/substring check, so "Hi, show my taxes." still goes to the classifier); (2) a pasted `Field: value` dump naming ≥3 of the model's own fraud-feature field names (`fraud/schema.py`'s `ALL_FIELDS`) — an unambiguous structural signal, routed straight to `fraud_assessment`; (3) an explicit fraud-leaning keyword/phrase in Arabic or English (`graph.py`'s `_FRAUD_TRIGGER_PHRASES`, e.g. "سليم"/"فحص"/"check"/"assess") **unless** the message also contains a stronger database-retrieval verb (`_DB_QUERY_OVERRIDE_PHRASES`, e.g. "retrieve"/"show me"), in which case it still falls through to the classifier. Only once none of these match does the LLM (`classify_intent`) ever run. `route_intent` also sets `state["response_language"]` (`"ar"` | `"en"`) exactly once per turn from the user's own message — every response-producing node below reads that instead of re-detecting language mid-turn. Two branches are fully implemented:

- **`fraud_assessment`**: LLM extraction (`fraud/extraction.py`, an all-`Optional` Pydantic model — never guesses a value the user didn't state) → `review_form` node calls `langgraph.types.interrupt()` to pause the graph and show/collect the 23-field form (always shown, even if every field was already extracted), split into 8 **required** fields and 15 **optional** ones (`fraud/schema.py`'s `CORE_REQUIRED_FIELDS`/`OPTIONAL_FIELDS` — read directly from `ml_artifacts/xgboost_8features_columns.txt`, not guessed) → `validate_fraud_form` (`fraud/validation.py`) only requires the 8 core fields, loops back to the same interrupt on invalid input, prefilled with the last submission plus the errors (localized per `state["response_language"]`, field identifiers like `Net_Profit` left as-is) → `predict_fraud` runs one of **two** trained XGBoost models (`fraud/engine.py`, loads 4 `.joblib` artifacts under `fraud/models/`): all 23 fields present → the full/"Comprehensive Assessment" model (40 engineered features); anything less (but always at least the 8 required) → the dedicated 8-feature/"Standard Assessment" model, using only its 8 inputs — **never** the full model with the gap filled by medians/modes (benchmarked and found worse: PR-AUC 0.8259 vs. 0.8305 for the dedicated model). Which model backs which tier is never surfaced to the user — only the tier name and how many of the 23 fields were provided. `POST /chat/fraud/extract` (stateless, no thread_id) lets the user type/paste more feature text into the chat *while the form is showing* — extracted values are merged into the form's current values (a field the new text doesn't mention keeps its existing value) without submitting or touching the graph checkpoint; the frontend re-renders the form with the merge result.
- **`database_query`**: `prepare_db_question` translates the message to an internal English question (this internal translation never changes `state["response_language"]`) → `run_sql_query` calls `services/sql_runner.py`'s `handle_user_database_query(user_id, question_en, db_conn)` (see "Ownership-aware SQL security" below for the full context-aware planning/authorization/SQL-generation design — the LLM only ever writes SQL restricted to the caller's authorized secure view(s), never the raw `tax.*` tables) → `db_response` phrases the answer in `state["response_language"]`, branching on the result's typed `status` (`no_ownership`/`forbidden_entity`/`forbidden_field`/`ambiguous_entity`/`empty_result`/etc. each get a distinct, correctly localized message) and attaching a `table` payload for `success`/`direct_answer`. `AgentState.user_id` (set from the authenticated FastAPI user in `routes.py`, never from the message) is what makes this ownership-aware.
- **`greeting`**, **`other`**, `unclear` → `clarify_intent`, and `multi_intent` → `handle_multi_intent` all answer from curated bilingual (English/Arabic) template pools in `responses.py` (`GREETING_TEMPLATES`/`OTHER_TEMPLATES`/`CLARIFY_INTENT_TEMPLATES`/`MULTI_INTENT_TEMPLATES`) — a deliberate choice to avoid a response-generation LLM call for prose this simple; each reads `state["response_language"]` rather than re-detecting it. `OTHER_TEMPLATES` only describes capabilities that actually exist today (authorized record lookups, fraud-risk assessment) — general free-form tax conversation is not implemented, so `other` never pretends to answer one.

Interrupt/resume uses `langgraph`'s `InMemorySaver` checkpointer plus a `thread_id` of the form `{user_id}:{uuid}` — ownership is checked on every resume in `routes.py` so one user can't submit into another's paused conversation. This checkpointer is **not durable across a backend restart**.

Nodes never call an LLM/STT/TTS provider SDK directly — always go through `providers/llm.py`'s `call_llm_text(...)` / `call_llm_structured(..., response_model=SomePydanticModel)`, `providers/stt.py`'s `transcribe_audio(...)`, or `providers/tts.py`'s `synthesize_speech(...)`. These handle provider/model fallback and per-model cooldown after a failure, driven entirely by env vars (`LLM_PROVIDER_ORDER`, `GROQ_LLM_MODELS`, `GEMINI_LLM_MODELS`, `STT_DETECT_PROVIDER`, `STT_TRANSCRIBE_PROVIDER`, `TTS_PROVIDER_ORDER`, `MODEL_COOLDOWN_SECONDS`, etc. — see `backend/app/chat/config.py` and `.env.example`), never hardcoded in node logic.

Speech is not a graph node — voice input/output is a presentation-layer add-on around the always-text agent, wired at `POST /chat/transcribe` and `POST /chat/speak`:
- **STT is a two-role pipeline, not a simple fallback list.** Cohere Transcribe has no auto-detect mode (confirmed live: omitting `language` 400s, and `language="auto"` 400s too — it only accepts one of 14 fixed ISO-639-1 codes). Groq Whisper reliably auto-detects the spoken language via `response_format="verbose_json"`. So every `/chat/transcribe` call runs Groq first (`STT_DETECT_PROVIDER`) purely to find the language, then Cohere (`STT_TRANSCRIBE_PROVIDER`) transcribes with that language — falling back to Groq's own transcript if Cohere is unavailable. This is what actually lets a user speak English, Arabic, or switch between them across messages and still get an accurate transcript.
- **TTS (`POST /chat/speak`) is entirely separate from `/chat/message`.** The agent always replies in text first; the frontend calls `/chat/speak` afterward only if the user has voice replies toggled on, so a TTS failure never blocks or alters the text already shown. ElevenLabs is tried first (`TTS_PROVIDER_ORDER`), Gemini (`gemini-2.5-flash-preview-tts` by default) as fallback — both accept plain multilingual text with no separate language parameter, inferring the spoken language from the text itself. Gemini's TTS returns raw 16-bit PCM audio, not a playable container, so `providers/tts.py` wraps it in a WAV header before returning it.

`db/query_chain.py` also contains a deliberately-unused `SQLDatabaseChain` experiment (`ask_database`) and a non-ownership-aware `generate_and_run_sql` — kept as documented, live-tested evidence (see the module's own docstring, which explicitly says not to wire either into the live graph), not used for real requests. Both execute against the full `tax` schema via the table-owning Postgres role, which is a superuser and bypasses RLS — fine for the historical experiment, but never acceptable for a real user request.

### Ownership-aware SQL security (`backend/app/database/security_setup.py`, `backend/app/chat/services/{sql_runner,query_planning}.py`)

Real per-company authorization, enforced by Postgres itself, not just Python — security holds even if any LLM in the pipeline generates malicious or incorrect output. The pipeline is context-aware and plans/authorizes BEFORE ever generating SQL, not after:

```
database_query → load business context → extract plan (LLM, field/metric names + raw company mentions only)
→ resolve company mentions (Python, fuzzy match against the user's OWN companies only)
→ authorize every requested field/metric against each resolved company's access_level (Python)
→ answer directly from context when possible (no SQL) → else generate SQL from the resolved plan
→ AST validate → execute as app_agent with RLS → typed status → response
```

- **`app_agent`** — an unprivileged Postgres LOGIN role (`app.config.APP_AGENT_DATABASE_URL`, a separate SQLAlchemy engine in `app/database/agent_db.py`) that all LLM-generated SQL executes as. Not superuser, not a table owner, not `BYPASSRLS`. The table-owning role (`DATABASE_URL` connects as, e.g. `etax`) is a Postgres superuser and always bypasses RLS — confirmed live with a throwaway experiment before writing any of this — so it's never used to run generated SQL.
- **Four secure views, split by grain** (not two views mixing transaction and item grain, which duplicated `sales`/`taxes` per item row and made `SUM()` overcount — confirmed as a real bug and fixed by the split, not just a style choice): `tax.v_my_companies` (company identity/activity/taxpayer info/share/access_level, ANY access level — safe regardless of tier since it's the taxpayer's own ownership record, not business data), `tax.v_majority_transactions` / `tax.v_minority_transactions` (transaction-grain; `sales` only exists in the majority view, `taxes` exists in both), `tax.v_majority_items` (item-grain; **no minority items view exists at all** — items are majority-only by the view simply not being there, the same "physically absent, not filtered" principle the old minority view already used). All four filter on `current_setting('app.current_user_id', true)` and are created `WITH (security_invoker = true)` — **this is mandatory, not stylistic**: confirmed live that a plain view owned by the superuser role silently bypasses RLS entirely, while the same view with `security_invoker = true` correctly restricts to the querying role's own rows. `security_invoker` views check the *querying* role's own table grants, which is why `app_agent` still holds `SELECT` on the base `tax.*` tables — a precondition for the views to work at all, not a way for the application to query those tables directly.
- **RLS**, enabled and forced on `tax.company_owners`/`transactions`/`items`, policies restricting rows to companies the session's `app.current_user_id` has any ownership relationship with. This is the backstop: it restricts *rows*, the views restrict *columns/grain* — neither layer alone has to be perfect.
- **`app/chat/db/security.py`'s `get_user_business_context(db_conn, user_id)`** is the only source of truth for what a user owns and at what tier — returns `{"taxpayer_id", "taxpayer_name", "companies": [{"company_id", "company_name", "company_activity", "share", "access_level"}, ...]}` straight from Postgres, never collapsed into one global tier. (`get_user_ownership_status` still exists alongside it for the simpler `{"has_ownership", "majority_company_ids", "minority_company_ids"}` shape a few call sites use.)
- **`app/chat/services/query_planning.py`** does the two LLM-free, deterministic pieces: `resolve_company_mentions(mentions, companies)` fuzzy-matches raw text ("bright", "bright company", "Bright Futur Academy") against ONLY the caller's own companies (exact match → substring/contains → `difflib` ratio ≥0.6 in that order; never a global company search, so a non-match can't confirm or deny some other company's existence) and returns `resolved`/`ambiguous`/`unresolved`; `authorize_plan(plan, context)` checks every requested field/metric (from the fixed `FIELDS`/`METRICS` registries, each tagged with a `min_access` of `"any"` or `"majority"`) against the resolved companies' real `access_level` and returns one typed decision (`ambiguous_entity`/`forbidden_entity`/`forbidden_field`/`direct_answer`/`proceed`) — this is what makes a request like `item_price` for a minority-owned company fail immediately, before any SQL-generating LLM call, rather than "let the SQL LLM discover it and hope the AST validator/views catch the mistake." The one LLM call in this module, `extract_query_plan`, is constrained to that same fixed field/metric vocabulary and never supplies a company_id, share, or access level itself.
- **`app/chat/services/sql_runner.py`'s `handle_user_database_query(user_id, question_en, db_conn)`** orchestrates the above, then (only on `authorize_plan`'s `"proceed"` decision) builds a prompt naming only the view(s) the resolved plan actually needs (columns reflected live from Postgres via `sqlalchemy.inspect`) and the exact authorized `company_id`s, gets SQL from `call_llm_text`, validates it with `sqlglot` (`_validate_sql_ast` — a real parse tree, not a `.startswith("select")` string check, accepting a plain `SELECT` **or a `UNION`/`EXCEPT`/`INTERSECT` of `SELECT`s** since `find_all()` already walks the whole tree regardless of the root node's shape, so broadening the root-type check doesn't weaken relation checking at all), then executes on the `app_agent` engine with `SELECT set_config('app.current_user_id', :uid, true)` (**`is_local=true`/transaction-local** — confirmed live the setting reverts at `COMMIT`, so a pooled connection can never inherit a previous request's identity). A genuine Postgres **execution** failure (e.g. a UNION column type mismatch) gets exactly **one repair attempt** — regenerated from scratch with the error fed back, then re-validated and re-executed through the full pipeline again, never patched in place; an **AST validation** failure (forbidden relation, mutating statement, multiple statements) is never repaired, since that's security-relevant, not a syntax slip.
- **Typed `status`**, not a single loose "error" string: `success` / `empty_result` / `no_ownership` / `forbidden_entity` / `forbidden_field` / `ambiguous_entity` / `sql_validation_failed` / `sql_execution_failed` / `direct_answer`. `graph.py`'s `db_response` branches on this to give a distinct, correctly localized message per case (e.g. a real security denial and a query that legitimately found nothing no longer read as the same vague "please provide a specific taxpayer ID or year").
- `init_db()` calls `security_setup.ensure_security_setup(engine)` on every startup — idempotent (role creation checked in Python first since bind parameters don't work inside a `DO $$...$$` block's dollar-quoted body; `DROP VIEW IF EXISTS` for the old two-view shape before `CREATE OR REPLACE VIEW`, since a view's column set can only ever grow via `CREATE OR REPLACE`, never shrink/reorder; `DROP POLICY IF EXISTS` before `CREATE POLICY`). `APP_AGENT_DB_PASSWORD` has a dev-only default (`app_agent_pw`, matching this repo's existing `POSTGRES_PASSWORD`/`JWT_SECRET_KEY` dev-default convention) — override it for any real deployment.

### Frontend (`frontend/src/`)

React + Vite, plain JS (no TypeScript). The design system was ported from `system_design_UI.zip` into `components/{core,forms,feedback,navigation,overlay,chat,data,auth,face}/` — reuse these primitives (`Button`, `TextField`, `Select`, `Alert`, `DataTable`, etc.) rather than hand-rolling new ones; they follow shared style tokens in `styles/tokens/*.css`.

`pages/ChatPage.jsx` calls `POST /chat/message` for real: plain replies render as chat bubbles, a `table` payload renders `components/data/DataTable.jsx` under the assistant's text, and a response with `awaiting.type === "fraud_form"` renders `components/chat/FraudForm.jsx` inline — its dropdowns/fields, and which fields are in the "Required Assessment Fields" section vs. "Advanced Optional Fields", are built entirely from the backend-supplied `awaiting.schema` (`required_fields`/`optional_fields`, categorical options, which fields are integer-only), never hand-duplicated on the frontend. While that form is showing, the composer stays enabled and routes to `POST /chat/fraud/extract` instead of `/chat/message` — see `ChatPage.jsx`'s `extractIntoForm`.

## Key conventions to preserve

- All chatbot config (provider order, model names, thresholds) lives in env vars, never hardcoded in route/node logic.
- Never impute a missing fraud-assessment field (no medians/modes/zeros) — `fraud/engine.py`'s model selection is exact field count for this reason; a partial form always runs the dedicated 8-feature model on exactly its 8 inputs, never the full model with gaps filled in.
- Identity is authoritative from the authenticated FastAPI user resolved via `require_stage`/`require_authenticated` — never trust a `user_id`/`taxpayer_id`/`company_id`/ownership claim supplied by the LLM or the user's message itself.
- Never wire `query_chain.py`'s `generate_and_run_sql`/`ask_database` into the live graph — they execute unrestricted against the full `tax` schema via the superuser role. `database_query` must always go through `services/sql_runner.py`'s `handle_user_database_query`.
- The LLM never decides a fact: fraud risk comes from XGBoost's prediction, database answers are grounded in rows actually returned by SQL (the summarization prompt explicitly forbids stating anything not literally present in the retrieved records).
- When adding a new LLM call, go through `call_llm_text`/`call_llm_structured` — don't instantiate a Groq/Gemini client directly in a node.
- Simple, non-substantive replies (greeting, assistant identity, off-topic redirects) come from `responses.py`'s curated template pools, never a response-generation LLM call — reserve the LLM for intent classification, extraction, SQL generation, and grounded summarization.
