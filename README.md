# eTax — AI-Assisted Tax Platform

**Phase 1 (done):** Landing → Signup/Login → Face enrollment/verification →
authenticated Chatbot UI shell.

**Phase 2 (in progress) — chatbot agent.** Six intents total (`greeting`,
`fraud_assessment`, `database_query`, `other`, `unclear`, `multi_intent` —
cut down from an earlier 8-intent set after `assistant_identity`/
`tax_conversation`/`off_topic` proved unreliable to keep separate and were
collapsed into `other`; see `CLAUDE.md`). `fraud_assessment` and
`database_query` are fully real end to end (UI included); `greeting`/
`other`/`unclear`/`multi_intent` answer from curated deterministic templates
(no LLM call for the reply itself):
- **fraud_assessment** — LLM extracts whatever the message mentions → a
  LangGraph `interrupt()` always shows the 23-field form (prefilled, never
  auto-run even if every field was extracted), split into 8 required fields
  (enough on their own for a "Standard Assessment") and 15 optional ones
  (filling all of them unlocks a "Comprehensive Assessment") → Python
  validation requires only the 8, loops back to the same form on invalid
  input → one of two trained XGBoost models depending on exactly how many
  fields are present — never the full model with gaps filled by
  medians/modes → a plain-language result with the required hedging line.
  The user can also type/paste more feature text into the chat while the
  form is showing (`POST /chat/fraud/extract`) to fill it in without
  submitting.
- **database_query** — ownership-aware: a user with no company shares never
  reaches the SQL-generating LLM at all. Otherwise the message is translated
  to an internal English question → the LLM writes a single SQL `SELECT`
  restricted (by a real SQL parse tree, not a string check) to only the
  secure view(s) matching that user's per-company majority/minority holdings
  → executed as an unprivileged Postgres role with row-level security
  enforced → the LLM phrases a short factual answer in `state["response_language"]`
  (set once per turn from the user's own message, not re-detected/guessed
  per response), with the full result set also returned as a real data
  table. See `CLAUDE.md`'s "Ownership-aware SQL security" for the full design.
- **greeting / other / unclear / multi_intent** — a deterministic pre-router
  in `route_intent` catches, in order: an obvious standalone greeting ("Hi",
  "مرحبا"); a pasted `Field: value` fraud-feature dump; or an explicit
  fraud-leaning keyword ("سليم"/"فحص"/"check"/"assess" — unless a stronger
  database-retrieval verb is also present) — routing straight to
  `fraud_assessment` without ever calling the classifier for these. A
  greeting attached to a real request ("Hi, show my taxes.") still goes
  through the classifier. All four reply from curated bilingual template
  pools (`responses.py`) rather than a response-generation LLM call.

The chat UI (`/chat`) calls the real backend now — text messages, the fraud
form (dropdowns/inputs generated from the backend's schema, not
hand-duplicated), query result tables, a working mic (speech-to-text) and a
voice-replies toggle (text-to-speech) all work. The controlled SQL subgraph
(replacing today's minimal version) is not built yet — see `backend/app/chat/`
for what exists.

## Structure

```
backend/                 FastAPI API — auth, face enrollment/verification, chat agent, PostgreSQL+pgvector
frontend/                React (Vite) — ported eTax design system + the six product pages
docs/                    Deep-dive docs: chatbot flow, codebase review, debugging guide
ml_artifacts/            Source fraud-model artifacts (ML_inputs_details.txt, feature_importance_table.csv,
                          xgboost_8features_columns.txt + the 4 .joblib files) — the copies actually
                          used at runtime live in backend/app/chat/fraud/models/, baked into the backend image
system_design_UI.zip     Source design system this frontend was built from
docker-compose.yml       db + backend + frontend
.env.example             Template for all required API keys/config — copy to .env and fill in
```

## Sign-in flow

Password auth and face verification are two independent steps, enforced by
the backend on every request (not just hidden by frontend routing):

```
POST /auth/signup  → stage=pending_enrollment token
POST /face/enroll  → stage=authenticated token   (liveness-gated)
POST /auth/login   → stage=face_required token    (or pending_enrollment if never enrolled)
POST /face/verify  → stage=authenticated token   (liveness-gated, matched only against the token's own user)
GET  /auth/me      → requires stage=authenticated
```

Each stage token only unlocks its own next step — a `face_required` token
cannot call `/face/enroll`, and `/face/verify` never runs a nearest-neighbor
search across all enrolled users; it fetches the embedding belonging to the
`sub` user in the token and compares against that one record only.

## Running it

```bash
cp .env.example .env   # then set a real JWT_SECRET_KEY, and for the chatbot:
                        # COHERE_API_KEY, GROQ_API_KEY, GEMINI_API_KEY, ELEVENLABS_TTS_KEY
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend / Swagger docs: http://localhost:8000/docs
- Postgres: localhost:5432

First backend build takes a while — it bakes in both the InsightFace
(`buffalo_l`) and MiniFASNetV2 liveness models at build time. Camera access
requires `localhost` or HTTPS in the browser.

## Face recognition

`backend/app/face/face_engine.py` (InsightFace/ArcFace `buffalo_l`) and
`liveness_engine.py` (MiniFASNetV2 passive liveness) are a standalone
implementation — not a dependency on any external package. Liveness gates
both enrollment and verification: a spoofed/photo/screen capture never
reaches the embedding or matching step. This defends against presentation
attacks (photos, screens, replays) but not deep fakes or more sophisticated
spoofing — treat it as one layer, not a complete anti-fraud guarantee.

## Chatbot agent

`backend/app/chat/`:

```
config.py            STT/LLM provider order, models, cooldown — all env-driven
providers/llm.py      call_llm_text(...) / call_llm_structured(..., response_model=...)
                      with Groq → Gemini fallback + per-model cooldown on failure
providers/stt.py      transcribe_audio(...): Groq detects language -> Cohere transcribes with it
providers/tts.py      synthesize_speech(...) with ElevenLabs → Gemini fallback
intent.py             7-way intent classifier (structured output) + INTENT_ROUTING table
state.py              AgentState — the single TypedDict threaded through the graph
graph.py              LangGraph: route_intent -> branch; fraud_assessment is a real subgraph,
                      the other six are still placeholders
routes.py             POST /chat/message — requires stage=authenticated, handles
                      both starting a run and resuming an interrupted one
fraud/schema.py       FraudFeatures (all-Optional extraction model), option lists, the
                      8 required / 15 optional field split (CORE_REQUIRED_FIELDS/
                      OPTIONAL_FIELDS, read from xgboost_8features_columns.txt), exact
                      40-feature order confirmed from the live .joblib artifacts
fraud/extraction.py   LLM extraction — never guesses; unmentioned fields stay null
fraud/validation.py   Python validation — only the 8 core fields are required; the rest
                      are validated (type/range/category) only if provided
fraud/engine.py       Loads onehot/ordinal encoders + both XGBoost models, routes to
                      whichever matches exactly how many of the 23 fields are present
                      (never a partial run of the full model with gaps imputed)
fraud/models/         The four .joblib artifacts (source copies in ml_artifacts/ at repo root)
db/seed.py             ensure_ready() — loads the tax schema's example dataset (3
                       companies, 5 transactions, 5 items) if empty, idempotent,
                       called from main.py's startup hook
db/security.py          get_user_ownership_status(db_conn, user_id) — the only
                       source of truth for per-company majority/minority access
db/query_chain.py       The SQLDatabaseChain experiment (ask_database) + a
                       non-ownership-aware generate_and_run_sql — both kept as
                       documented, live-tested evidence; NEITHER is used by the
                       live graph (see the module's own docstring)
services/sql_runner.py  handle_user_database_query(...) — the ownership-aware
                       path database_query actually calls; see CLAUDE.md's
                       "Ownership-aware SQL security"
```

Tax data lives in the same Postgres database as auth data (`app.config.DATABASE_URL`), under a separate `tax` schema — see "One PostgreSQL database, two schemas" in `CLAUDE.md` for the full table layout (`taxpayers`, `companies`, `company_owners`, `transactions`, `items`). `db/seed.py` loads a small example dataset (Bright Future Academy / GlobalBuild Corp / City Medical Center, with a handful of transactions and items) so `database_query` has real rows to answer against — this is the literal sample data supplied for development, not generated business records; real seed/import data replaces it separately. There is no SQLite anywhere in the app anymore.

`POST /chat/message` (Bearer token) either starts a run (`{"message": "..."}`,
`thread_id` optional — server mints one) or resumes a paused one
(`{"thread_id": "...", "form_response": {...}}`). A response is either
`{"reply": "...", "intent": "..."}` or, when the fraud form is showing,
`{"awaiting": {"type": "fraud_form", "fields": {...prefilled...}, "errors": [...],
"schema": {...categorical options + which fields are integer-only...}}}`.
`thread_id` is prefixed with the owning user's id and checked on every
resume — one user can't submit into another user's paused conversation.
The graph uses `langgraph`'s `InMemorySaver` checkpointer, so paused
conversations don't survive a backend restart — fine for this stage, would
need a persistent (e.g. Postgres) checkpointer before this goes further.

A `database_query` response also carries `{"table": {"columns": [...], "rows": [[...], ...]}}`
alongside the natural-language `reply` when the query returned rows — the
full result set, not just a summary, per the roadmap's "show complete rows
in a nice format, not just an LLM summary" note.

Nodes never call Groq/Gemini/the model files directly — everything goes
through `call_llm_text`/`call_llm_structured`/`fraud/engine.predict` so
provider priority, fallback, and the feature-encoding pipeline stay in one
place each.

### The SQLDatabaseChain experiment

Tried it as the roadmap asked, live-tested it against the demo DB across
several question phrasings, and it's not reliable enough to wire into the
graph with these providers — kept as `db/query_chain.py`'s `ask_database`
for the record. `database_query` doesn't call `generate_and_run_sql` from
that module either (also kept only as a reference implementation, and
deliberately never wired in since it has no per-user authorization at all) —
it calls `services/sql_runner.py`'s ownership-aware `handle_user_database_query`
instead (same idea — LLM writes SQL, Python executes it — through `call_llm_text`'s
chat-style prompting, which has been reliable everywhere else in this
project). Confirmed failure modes, same query/model, deterministic across
repeated runs:
- `SQLDatabaseChain` builds a **completion-style** prompt (`"...Question: \
  <q>\nSQLQuery:"`) and asks a **chat-tuned** model to continue it. For
  "How much tax did taxpayer 1002 pay in 2025?" specifically, the model
  returned a genuinely empty completion, every time.
- `use_query_checker=True`'s self-correction follow-up call sometimes
  returned a conversational non-answer ("I'm ready to review the query, but
  I need the SQL statement first...") instead of corrected SQL, which then
  failed as SQL itself.
- `llama-3.3-70b-versatile` additionally wrapped SQL in ```` ```sql ```` fences
  regardless of an explicit prompt instruction not to; `openai/gpt-oss-20b`
  didn't.
- Some questions ("Show me all Cairo taxpayers.") worked fine — this isn't a
  config mistake, the approach is just inconsistent, which is exactly the
  concern the roadmap raised about trusting this chain.

(This investigation predates the PostgreSQL unification below — it ran
against the old SQLite demo DB and its `taxpayers`/`tax_returns` schema,
which no longer exists. The conclusion about `SQLDatabaseChain`'s
unreliability doesn't depend on which database backs it, so it's kept as-is;
`ask_database` itself has been repointed at the current Postgres `tax`
schema.)

Manual smoke tests (need real API keys in `.env`, run live provider calls):

```bash
docker compose exec backend python -m app.chat._manual_test_intent
```

Notable things found while validating this against live providers and the
real artifacts (see `.env`/`.env.example` for the resulting defaults):
- Groq's strict `json_schema` mode requires `additionalProperties: false` on
  every object (`model_config = ConfigDict(extra="forbid")`) **and** every
  property listed in `required`, even nullable ones — omitting an Optional
  field from `required` (Pydantic's default for fields with a default value)
  400s; fixed by rebuilding `required` as every property key before sending.
- Gemini's `response_schema` (SDK auto-derives from the Pydantic model) can't
  represent `additionalProperties` and 400s — worked around by using JSON
  mode with the schema spelled out in the prompt instead, same as the
  fallback path for Groq models without strict-mode support.
- `gemini-2.0-flash` is retired; use the `gemini-flash-latest` alias so this
  doesn't need chasing again on the next model turnover.
- Cohere Transcribe requires an explicit `language`; a mismatched hint (e.g.
  `ar` against English audio) produces fluent-looking but wrong text rather
  than an error — worth keeping in mind when debugging odd transcripts.
- A Pydantic field named the same as the type alias in its own annotation
  (`Region: Optional[Region]`) silently resolves to the field, not the
  alias — every value validated as if the field's type were `None`. Fixed by
  renaming the alias (`RegionValue`). Worth grep-ing for elsewhere before it
  recurs — nothing catches this at import time.
- The `.joblib` encoders were pickled with scikit-learn 1.3.2; a newer
  installed version (1.7.2) loads them with only a warning, but pinned to
  1.3.2 anyway to remove that drift risk rather than trust the warning is
  harmless.
- Installing `langchain-groq` downgraded `groq` from 1.6.0 to 0.37.1 as a
  transitive dependency — re-tested the whole existing provider layer
  (plain text calls and strict `json_schema` structured calls) against the
  older SDK before trusting it; both still worked unchanged.
- Asking an LLM to "respond in the same language as the user's message"
  is not reliable enough on its own — live-tested and caught one run that
  returned a fluent **Russian** answer to an Arabic question (correct data,
  wrong language entirely; the same inputs re-run came back correctly in
  Arabic). Fixed by detecting the language with a cheap Unicode-range check
  and naming it explicitly in the prompt ("respond in Arabic") instead of
  asking the model to infer and match it — confirmed reliable across
  repeated runs afterward.
- Docker environment variables are fixed at container **creation**, not
  read live from `.env`/`docker-compose.yml` on every `up` — after editing
  either, `docker compose up -d <service>` only picks up the change if it
  actually recreates the container (which it does on most edits, but not a
  plain `restart`). Caught this via a stale `GEMINI_LLM_MODELS` value
  surviving a config fix until the container was explicitly recreated.
- **Cohere Transcribe has no auto-detect mode.** Live-tested by calling its
  REST endpoint directly (bypassing the SDK's typed wrapper, which forces a
  `language` argument): omitting `language` 400s ("missing required field
  'language'"), and `language="auto"` 400s too ("Unsupported language:
  'auto'. Must be one of ['en','fr','de','es','pt','it','nl','pl','el','ar',
  'ko','ja','vi','zh']"). A wrong/fixed language hint doesn't error at all —
  it silently produces fluent-looking wrong text (reproduced again live:
  English audio transcribed with `language=ar` came back as unrelated
  Arabic words). Since the platform needs to handle English, Arabic, or a
  user switching between them, `backend/app/chat/providers/stt.py` now runs
  Groq Whisper first with `response_format="verbose_json"` (which reliably
  auto-detects and names the spoken language) purely to pick the language,
  then calls Cohere with that language for the transcript actually used —
  falling back to Groq's own transcript if Cohere is unavailable.
- **MediaRecorder's browser output isn't what Cohere accepts.** Chrome/Edge
  only offer `audio/webm` recording; Cohere's supported extensions are
  `flac, mp3, mpeg, mpga, ogg, wav` — confirmed live via a 400 ("unsupported
  file extension ... got: webm"). Recording straight to webm made the
  Cohere-first behavior silently no-op every time (always falling to Groq).
  Fixed by decoding the recording and re-encoding it to WAV client-side
  (`frontend/src/hooks/useVoiceRecorder.js`) before upload.
- **The configured ElevenLabs key can't serve TTS as-is** — live-tested:
  `GET /v1/voices` and `GET /v1/user` both 401 ("missing the permission
  voices_read/user_read"), and `POST /v1/text-to-speech/{voice_id}` against
  a stock library voice 402s ("Free users cannot use library voices via the
  API. Please upgrade your subscription"). ElevenLabs is still tried first
  (`TTS_PROVIDER_ORDER=elevenlabs,gemini`) per the project's stated
  preference — it'll start working the moment the account has an eligible
  voice/plan — but Gemini is what actually serves voice replies today.
- **Gemini's TTS models return raw 16-bit PCM, not a playable file** —
  confirmed live (`mime type: audio/L16;codec=pcm;rate=24000` from
  `gemini-2.5-flash-preview-tts`). `providers/tts.py` wraps the raw bytes in
  a WAV header (Python's `wave` module) before returning them; both English
  and Arabic input were tested and produced correct, clearly audible speech
  without needing a separate language parameter.

## Frontend chat integration

`/chat` (`frontend/src/pages/ChatPage.jsx`) calls `POST /chat/message` for
real now instead of echoing a placeholder:

- Plain messages render as chat bubbles; a `database_query` response with a
  `table` payload renders the design system's `DataTable` under the
  assistant's text summary.
- A `fraud_assessment` response with `awaiting.type === "fraud_form"` renders
  `components/chat/FraudForm.jsx` inline in the message list instead of
  plain text — categorical dropdowns and numeric fields are generated
  entirely from `awaiting.schema` (the same option lists `fraud/schema.py`
  uses), so the frontend never hand-duplicates the model's valid categories.
  Submitting calls back with `{thread_id, form_response}`; a validation
  failure re-renders the same form with the errors and last-submitted
  values, exactly mirroring the backend's loop-back state.
- The composer is disabled while a form is pending or a request is in
  flight, so a stray message can't be sent mid-form.

`frontend/Dockerfile`'s `npm run dev` container now also bind-mounts
`frontend/src`/`public`/`index.html` (matching the backend's existing
`--reload` setup) so edits take effect via Vite's HMR without a rebuild —
see the `frontend` service in `docker-compose.yml`.
