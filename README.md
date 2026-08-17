# eTax — AI-Assisted Tax Platform

**Phase 1 (done):** Landing → Signup/Login → Face enrollment/verification →
authenticated Chatbot UI shell.

**Phase 2 (in progress) — chatbot agent.** Two of the seven intents are fully
real end to end (UI included), the other five are still routing
placeholders:
- **fraud_assessment** — LLM extracts whatever the message mentions → a
  LangGraph `interrupt()` always shows the full 23-field form (prefilled,
  never auto-run even if every field was extracted) → Python validation
  loops back to the same form on invalid input → the trained XGBoost model
  → a plain-language result with the required hedging line.
- **database_query** — the message is translated to an internal English
  question → the LLM writes a single SQL `SELECT` against the synthetic demo
  DB → Python enforces SELECT-only before executing → the LLM phrases a
  short factual answer **in the user's original language** (detected, not
  guessed), with the full result set also returned as a real data table.

The chat UI (`/chat`) calls the real backend now — text messages, the fraud
form (dropdowns/inputs generated from the backend's schema, not
hand-duplicated), query result tables, a working mic (speech-to-text) and a
voice-replies toggle (text-to-speech) all work. The controlled SQL subgraph
(replacing today's minimal version) and `unclear`/`multi_intent` interrupts
are not built yet — see `backend/app/chat/` for what exists.

## Structure

```
backend/                 FastAPI API — auth, face enrollment/verification, chat agent, PostgreSQL+pgvector
frontend/                React (Vite) — ported eTax design system + the six product pages
docs/                    Deep-dive docs: chatbot flow, codebase review, debugging guide
ml_artifacts/            Source fraud-model artifacts (ML_inputs_details.txt + the 3 .joblib
                          files) — the copies actually used at runtime live in
                          backend/app/chat/fraud/models/, baked into the backend image
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
fraud/schema.py       FraudFeatures (all-Optional extraction model), option lists,
                      exact 40-feature order confirmed from the live .joblib artifacts
fraud/extraction.py   LLM extraction — never guesses; unmentioned fields stay null
fraud/validation.py   Python validation of the confirmed form (required, types, ranges)
fraud/engine.py       Loads onehot/ordinal encoders + XGBoost model, runs the prediction
fraud/models/         The three .joblib artifacts (source copies in ml_artifacts/ at repo root)
db/schema.py           taxpayers + tax_returns CREATE TABLE statements
db/seed.py             Deterministic synthetic data generator (fixed seed — same
                       data on every fresh build), reuses the fraud module's
                       Business_Type/Region/Industry_Risk options for consistency
db/connection.py        get_connection() / ensure_ready() — creates + seeds on
                       first use, idempotent (checked: identical row counts
                       across a restart), called from main.py's startup hook
db/query_chain.py       The SQLDatabaseChain experiment (ask_database — kept as
                       documented, live-tested evidence, not used by the graph)
                       + generate_and_run_sql, the reliable hand-rolled path the
                       live database_query branch actually calls
```

The demo DB lives at `DEMO_DB_PATH` (default `/workspace/data/demo_tax.db`,
a named Docker volume — `demo_tax_db` — so it survives restarts) and is
purely synthetic: 60 taxpayers (IDs starting at 1000, so "taxpayer 1002"
from the project examples resolves to a real row), 2-4 tax returns each
across 2022-2025, with a real proportion of returns having declared_tax
below expected_tax so the roadmap's example query ("who has declared tax
less than expected tax") has genuine rows to find. Nothing here touches the
real Postgres auth database.

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
for the record, but `database_query` calls `generate_and_run_sql` instead
(same idea — LLM writes SQL, Python executes it — through `call_llm_text`'s
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
