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

### No formal test suite or linter configured

There's no pytest/eslint config in this repo yet. `backend/app/chat/_manual_test_intent.py` (see above) is the only automated check that exists, and it's a live-API smoke test, not a unit test suite.

## Architecture

### Two databases, deliberately separate

- **Postgres + pgvector** (`backend/app/database/`) — the real auth data: `users`, `face_profiles` (512-d ArcFace embeddings, compared via pgvector cosine distance).
- **SQLite demo tax DB** (`backend/app/chat/db/`) — synthetic `taxpayers`/`tax_returns` data for the chatbot's `database_query` intent. Seeded automatically and idempotently on backend startup (`ensure_ready()`, called from `main.py`'s startup hook), path via `DEMO_DB_PATH` (named volume `demo_tax_db`). Never touches the Postgres DB. Taxpayer IDs start at 1000.

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

A LangGraph state machine (`graph.py`) behind `POST /chat/message`, using a single `AgentState` TypedDict (`state.py`). `route_intent` classifies the message into one of 7 intents via structured LLM output (`intent.py`'s `INTENT_ROUTING` table — the LLM only names the intent; a Python dict decides which node runs, never the model). Two branches are fully implemented:

- **`fraud_assessment`**: LLM extraction (`fraud/extraction.py`, an all-`Optional` Pydantic model — never guesses a value the user didn't state) → `review_form` node calls `langgraph.types.interrupt()` to pause the graph and show/collect the full 23-field form, always shown even if every field was already extracted → `validate_fraud_form` (`fraud/validation.py`) loops back to the same interrupt on invalid input, prefilled with the last submission plus the errors → `predict_fraud` runs the trained XGBoost model (`fraud/engine.py`, loads the 3 `.joblib` artifacts under `fraud/models/`; the exact 40-feature order/categories were confirmed by inspecting the artifacts directly, not assumed from docs).
- **`database_query`**: `prepare_db_question` translates the message to an internal English question → `run_sql_query` calls `generate_and_run_sql` in `db/query_chain.py` (LLM writes SQL through the shared `call_llm_text`, Python enforces a single SELECT statement with a keyword blocklist before executing against a read-only SQLite connection) → `db_response` phrases the answer in the *detected* original language (a cheap Arabic-Unicode-range regex, not "ask the model to match the language" — that was tried and found unreliable) and attaches the full result set as a `table` payload.
- The other 5 intents (`assistant_identity`, `tax_conversation`, `off_topic`, `clarify_intent`, `handle_multi_intent`) are placeholder nodes; `assistant_identity`/`off_topic` are hardcoded text, not LLM calls, by design.

Interrupt/resume uses `langgraph`'s `InMemorySaver` checkpointer plus a `thread_id` of the form `{user_id}:{uuid}` — ownership is checked on every resume in `routes.py` so one user can't submit into another's paused conversation. This checkpointer is **not durable across a backend restart**.

Nodes never call an LLM/STT/TTS provider SDK directly — always go through `providers/llm.py`'s `call_llm_text(...)` / `call_llm_structured(..., response_model=SomePydanticModel)`, `providers/stt.py`'s `transcribe_audio(...)`, or `providers/tts.py`'s `synthesize_speech(...)`. These handle provider/model fallback and per-model cooldown after a failure, driven entirely by env vars (`LLM_PROVIDER_ORDER`, `GROQ_LLM_MODELS`, `GEMINI_LLM_MODELS`, `STT_DETECT_PROVIDER`, `STT_TRANSCRIBE_PROVIDER`, `TTS_PROVIDER_ORDER`, `MODEL_COOLDOWN_SECONDS`, etc. — see `backend/app/chat/config.py` and `.env.example`), never hardcoded in node logic.

Speech is not a graph node — voice input/output is a presentation-layer add-on around the always-text agent, wired at `POST /chat/transcribe` and `POST /chat/speak`:
- **STT is a two-role pipeline, not a simple fallback list.** Cohere Transcribe has no auto-detect mode (confirmed live: omitting `language` 400s, and `language="auto"` 400s too — it only accepts one of 14 fixed ISO-639-1 codes). Groq Whisper reliably auto-detects the spoken language via `response_format="verbose_json"`. So every `/chat/transcribe` call runs Groq first (`STT_DETECT_PROVIDER`) purely to find the language, then Cohere (`STT_TRANSCRIBE_PROVIDER`) transcribes with that language — falling back to Groq's own transcript if Cohere is unavailable. This is what actually lets a user speak English, Arabic, or switch between them across messages and still get an accurate transcript.
- **TTS (`POST /chat/speak`) is entirely separate from `/chat/message`.** The agent always replies in text first; the frontend calls `/chat/speak` afterward only if the user has voice replies toggled on, so a TTS failure never blocks or alters the text already shown. ElevenLabs is tried first (`TTS_PROVIDER_ORDER`), Gemini (`gemini-2.5-flash-preview-tts` by default) as fallback — both accept plain multilingual text with no separate language parameter, inferring the spoken language from the text itself. Gemini's TTS returns raw 16-bit PCM audio, not a playable container, so `providers/tts.py` wraps it in a WAV header before returning it.

`db/query_chain.py` also contains a deliberately-unused `SQLDatabaseChain` experiment (`ask_database`) — kept as documented, live-tested evidence that it's unreliable with these Groq models (see the module docstring and `README.md`'s "SQLDatabaseChain experiment" section), not wired into the graph.

### Frontend (`frontend/src/`)

React + Vite, plain JS (no TypeScript). The design system was ported from `system_design_UI.zip` into `components/{core,forms,feedback,navigation,overlay,chat,data,auth,face}/` — reuse these primitives (`Button`, `TextField`, `Select`, `Alert`, `DataTable`, etc.) rather than hand-rolling new ones; they follow shared style tokens in `styles/tokens/*.css`.

`pages/ChatPage.jsx` calls `POST /chat/message` for real: plain replies render as chat bubbles, a `table` payload renders `components/data/DataTable.jsx` under the assistant's text, and a response with `awaiting.type === "fraud_form"` renders `components/chat/FraudForm.jsx` inline — its dropdowns/fields are built entirely from the backend-supplied `awaiting.schema` (categorical options, which fields are integer-only), never hand-duplicated on the frontend.

## Key conventions to preserve

- All chatbot config (provider order, model names, thresholds, DB path) lives in env vars, never hardcoded in route/node logic.
- The LLM never decides a fact: fraud risk comes from XGBoost's prediction, database answers are grounded in rows actually returned by SQL (the summarization prompt explicitly forbids stating anything not literally present in the retrieved records).
- When adding a new LLM call, go through `call_llm_text`/`call_llm_structured` — don't instantiate a Groq/Gemini client directly in a node.
