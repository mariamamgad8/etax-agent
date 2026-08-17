# eTax Platform - Complete Codebase Review

## Project Overview

**eTax** is an AI-assisted tax platform enabling users to:
- Sign up and authenticate with password + face biometrics (staged authentication)
- Query tax records via an intelligent chatbot
- Run fraud-risk assessments on taxpayers/businesses
- Ask general tax questions

**Stack:** FastAPI (backend) + React+Vite (frontend) + PostgreSQL+pgvector (auth/biometrics) + SQLite (demo tax DB) + Docker Compose (orchestration)

---

## Architecture Overview

### High-Level Flow
```
User → Frontend (React) → Backend API (FastAPI) → 
  ├─ Auth Service (PostgreSQL + JWT)
  ├─ Face Recognition (InsightFace + pgvector)
  ├─ Chat Agent (LangGraph state machine)
  │  ├─ Fraud Assessment (XGBoost model)
  │  └─ Database Query (SQL generation + SQLite)
  └─ Health checks
```

### Two Separate Databases (By Design)
1. **PostgreSQL + pgvector** — Production auth data:
   - Users (credentials, personal info)
   - FaceProfiles (512-d ArcFace embeddings, cosine distance comparison)

2. **SQLite (demo_tax_db)** — Synthetic tax records:
   - Taxpayers (1000+, seeded on startup)
   - Tax returns
   - Used ONLY by chatbot's `database_query` intent
   - Never touches PostgreSQL

---

## Backend (`backend/`)

### Project Structure
```
app/
├── __init__.py
├── config.py                 # All env-var configuration
├── main.py                   # FastAPI app setup + startup hooks
├── auth/                     # User authentication
│   ├── routes.py            # POST /auth/signup, /login; GET /auth/me
│   ├── schemas.py           # Pydantic request/response models
│   ├── service.py           # Business logic (user lookup, etc.)
│   ├── security.py          # Password hashing, JWT token creation
│   └── dependencies.py      # Dependency injection (require_authenticated, etc.)
├── face/                     # Face enrollment + verification
│   ├── routes.py            # POST /face/enroll, /verify
│   ├── face_engine.py       # InsightFace (ArcFace) detection + embedding
│   └── liveness_engine.py   # MiniFASNetV2 anti-spoofing
├── chat/                     # Chatbot agent + LLM integration
│   ├── graph.py             # LangGraph state machine (intent routing + branches)
│   ├── intent.py            # 7-way intent classifier
│   ├── routes.py            # POST /chat/message (run or resume)
│   ├── state.py             # AgentState TypedDict
│   ├── config.py            # LLM provider order, models, thresholds
│   ├── fraud/               # Fraud assessment branch
│   │   ├── schema.py        # FraudFeatures model, categories, thresholds
│   │   ├── extraction.py    # LLM extraction (all-Optional, never guesses)
│   │   ├── validation.py    # Python form validation
│   │   ├── engine.py        # XGBoost prediction (loads .joblib models)
│   │   └── models/          # Trained encoders + XGBoost artifact
│   ├── db/                  # Database query branch
│   │   ├── query_chain.py   # SQL generation + execution (read-only)
│   │   ├── connection.py    # SQLite connection + seeding
│   │   ├── schema.py        # Demo DB schema definition
│   │   └── seed.py          # Taxpayer/tax return data generation
│   └── providers/           # LLM + STT abstraction
│       ├── base.py          # Common exceptions, cooldown tracker
│       ├── llm.py           # call_llm_text(...), call_llm_structured(...) with fallback
│       └── stt.py           # call_transcribe_audio(...) with fallback
├── database/                 # PostgreSQL ORM
│   ├── db.py                # SQLAlchemy engine, session
│   └── models.py            # User, FaceProfile
└── Dockerfile               # Python 3.11 + dependencies + pre-built models
```

### Key Components

#### 1. Authentication (`auth/`)
**Flow:**
```
POST /auth/signup  → stage=pending_enrollment (face enrollment required)
POST /face/enroll  → stage=authenticated (face verified)
POST /auth/login   → stage=face_required (password verified)
POST /face/verify  → stage=authenticated (face matched)
GET  /auth/me      → requires stage=authenticated
```

**Security Model:**
- Stage tokens are **short-lived** (enrollment 15 min, verification 10 min, session 60 min)
- Each stage token **only unlocks its matching endpoint** — enforced by `require_stage` dependency
- `/face/verify` fetches ONLY the embedding for the current user (`sub` in token) — no nearest-neighbor search across all users
- Passwords stored as bcrypt hashes; face verification compares via pgvector cosine distance

**Key Files:**
- [routes.py](backend/app/auth/routes.py): signup/login logic
- [security.py](backend/app/auth/security.py): password hashing, JWT creation
- [dependencies.py](backend/app/auth/dependencies.py): route guards

---

#### 2. Face Recognition (`face/`)
**InsightFace (ArcFace) + MiniFASNetV2 (Liveness)**

**Key Architecture:**
- `buffalo_l` model pack, standalone implementation (no external package dependency)
- Pre-built models baked into Docker image at build time (slow first build)
- Liveness gates BOTH enrollment and verification (passive spoofing defense)

**Enrollment:**
1. User captures frame → detect largest face → run liveness check
2. If live: extract 512-d ArcFace embedding → store in `face_profiles` table

**Verification:**
1. User captures frame → detect largest face → run liveness check
2. If live: extract embedding → compare with pgvector cosine distance against stored profile
3. If distance < MATCH_THRESHOLD (0.45): authenticated

**Key Files:**
- [face_engine.py](backend/app/face/face_engine.py): InsightFace detection
- [liveness_engine.py](backend/app/face/liveness_engine.py): Anti-spoofing
- [routes.py](backend/app/face/routes.py): Enrollment + verification endpoints

---

#### 3. Chat Agent (`chat/`)
**LangGraph State Machine: Intent → Branch → Response**

**Architecture:**
```python
route_intent(message) 
  → classify via LLM (7 intents: fraud_assessment, database_query, etc.)
  → INTENT_ROUTING dict (Python-driven, never LLM-decided)
  → Branch node
```

**Implemented Branches:**

##### A. Fraud Assessment (`fraud_assessment`)
1. **extract_fraud_fields** — LLM extraction (Pydantic `all-Optional` model)
   - Never guesses; unmentioned fields stay `null`
   - 23 raw fields (numeric + categorical)

2. **review_form** — `langgraph.interrupt()` pause
   - Always shown (even if extraction filled every field)
   - User reviews/corrects in the form UI
   - Checkpointed in `InMemorySaver` with thread_id `{user_id}:{uuid}`

3. **validate_fraud_form** — Python validation
   - Type checking, range validation, required fields
   - On error: loop back to `review_form` (same interrupt, prefilled + errors shown)

4. **predict_fraud** — XGBoost model inference
   - Loads 3 `.joblib` artifacts: onehot_encoder, ordinal_encoder, xgboost_fraud_model
   - Feature order and categories confirmed by inspecting artifacts (not docs)
   - Returns (label: "Suspicious"/"Not suspicious", probability: 0.0–1.0)

5. **fraud_response** — Text response
   - Always includes hedging: "does not confirm fraud — refer for manual review"

**Key Files:**
- [schema.py](backend/app/chat/fraud/schema.py): FraudFeatures model + categories
- [extraction.py](backend/app/chat/fraud/extraction.py): LLM extraction node
- [validation.py](backend/app/chat/fraud/validation.py): Form validation
- [engine.py](backend/app/chat/fraud/engine.py): XGBoost prediction

##### B. Database Query (`database_query`)
1. **prepare_db_question** — LLM translates message to internal English question

2. **run_sql_query** — LLM writes SQL, Python executes
   - LLM generates a single `SELECT` statement via `call_llm_text`
   - Python regex validates: SELECT-only, blocks dangerous keywords
   - SQLite connection opened read-only (OS-level write protection)

3. **db_response** — Phrased in detected language
   - Language detection: cheap Arabic Unicode-range regex (not "ask LLM")
   - Attaches full result set as `table` payload for frontend DataTable

**Key Files:**
- [query_chain.py](backend/app/chat/db/query_chain.py): SQL generation + execution
- [connection.py](backend/app/chat/db/connection.py): SQLite setup
- [seed.py](backend/app/chat/db/seed.py): Demo data generation

##### C. Placeholder Branches (Not Yet Implemented)
- `assistant_identity` → hardcoded response
- `tax_conversation` → placeholder
- `off_topic` → hardcoded response
- `unclear` → placeholder (requires form interrupt for clarification)
- `multi_intent` → placeholder (split into sub-questions)

---

### LLM Integration (`chat/providers/`)

**Central Abstraction:** All LLM calls go through `call_llm_text()` or `call_llm_structured()`, never direct Groq/Gemini client instantiation.

**Provider & Model Fallback:**
- Priority order: env var `LLM_PROVIDER_ORDER` (e.g., `["groq", "gemini"]`)
- Per provider: model list (e.g., `GROQ_LLM_MODELS = ["openai/gpt-oss-20b", "llama-3.3-70b-versatile"]`)
- On failure: mark model as cooling down for `MODEL_COOLDOWN_SECONDS`, try next

**Groq Clients:**
- Text: `gpt-oss-20b`, `llama-3.3-70b-versatile`, etc. (json_object mode for structured output)
- Only `openai/gpt-oss-20b` + `openai/gpt-oss-120b` support strict `json_schema` mode; others get inline schema description + json validation fallback

**Gemini:**
- Supports full `GenerateContentConfig` with system instructions

**Key Files:**
- [llm.py](backend/app/chat/providers/llm.py): `call_llm_text()`, `call_llm_structured()`
- [stt.py](backend/app/chat/providers/stt.py): `transcribe_audio()` (Cohere → Groq fallback)
- [base.py](backend/app/chat/providers/base.py): `CooldownTracker`, exceptions

---

### Chat Configuration (`chat/config.py`)
**All chatbot config is env-driven**, never hardcoded:
```python
LLM_PROVIDER_ORDER           # e.g., "groq,gemini"
GROQ_API_KEY, GEMINI_API_KEY # Provider credentials
GROQ_LLM_MODELS              # e.g., "openai/gpt-oss-20b,llama-3.3-70b-versatile"
GEMINI_LLM_MODELS
MODEL_COOLDOWN_SECONDS       # Failure cooldown per model
DEMO_DB_PATH                 # SQLite path (named volume)
STT_DETECT_PROVIDER          # Language detection (default: groq)
STT_TRANSCRIBE_PROVIDER      # Transcript provider (default: cohere)
COHERE_API_KEY               # STT provider
GROQ_STT_MODELS
TTS_PROVIDER_ORDER           # e.g., "elevenlabs,gemini"
ELEVENLABS_TTS_KEY           # Text-to-speech (POST /chat/speak, separate from the graph)
```

---

### Database Models

**PostgreSQL Schema:**
```sql
users
├─ id (UUID primary key)
├─ full_name
├─ username (unique)
├─ email (unique)
├─ password_hash (bcrypt)
├─ is_active
├─ created_at, updated_at

face_profiles
├─ id (int primary key)
├─ user_id (UUID foreign key, unique)
├─ embedding (vector[512])  -- pgvector cosine similarity
├─ created_at, updated_at
```

**SQLite Demo Tax DB Schema:**
```sql
taxpayers (seeded on startup)
├─ id
├─ name
├─ income, deductions, ...

tax_returns
├─ id
├─ taxpayer_id
├─ year, amount_paid, ...
```

---

### Startup Sequence (`main.py`)
1. Init PostgreSQL + create tables (SQLAlchemy)
2. Ensure demo SQLite DB ready (seed if first run, idempotent)
3. Pre-load InsightFace + MiniFASNetV2 models
4. Start Uvicorn with hot-reload (development only)

---

### Configuration (`config.py`)
- **DATABASE_URL** — PostgreSQL connection string
- **JWT_SECRET_KEY, JWT_ALGORITHM** — Token signing
- **Stage token TTLs** — enrollment, verification, session lifetimes
- **ALLOWED_ORIGINS** — CORS whitelist (localhost:5173 by default)
- **INSIGHTFACE_MODEL_PACK** — `buffalo_l` (fixed)
- **MATCH_THRESHOLD** — Face similarity cutoff (0.45)
- **LIVENESS_THRESHOLD** — Anti-spoofing confidence (0.85)
- **ANTISPOOF_MODEL_PATH** — MiniFASNetV2 weights location

---

## Frontend (`frontend/`)

### Project Structure
```
src/
├── App.jsx                   # Main router
├── main.jsx                  # React entry
├── api/
│   └── client.js            # HTTP client (signup, login, chat, face, etc.)
├── auth/
│   ├── AuthContext.jsx      # Global auth state (token, stage, user)
│   └── ProtectedRoute.jsx   # Route guard by stage
├── pages/
│   ├── LandingPage.jsx      # Home page
│   ├── SignupPage.jsx       # Registration
│   ├── LoginPage.jsx        # Password login
│   ├── FaceEnrollmentPage.jsx # Biometric enrollment
│   ├── FaceVerificationPage.jsx # Biometric verification
│   └── ChatPage.jsx         # Main chat interface
├── components/
│   ├── core/                # Primitives (Button, Card, Badge, Icon, etc.)
│   ├── forms/               # Form inputs (TextField, Select, Checkbox)
│   ├── auth/                # Auth shell
│   ├── chat/                # Chat-specific (ChatComposer, ChatMessage, FraudForm)
│   ├── face/                # Camera (LiveCameraFrame)
│   ├── data/                # DataTable for results
│   ├── feedback/            # Alert, Spinner, StatusSteps
│   ├── navigation/          # AppHeader
│   └── overlay/             # Modal
├── hooks/
│   └── useCamera.js         # Camera access helper
├── styles/
│   └── tokens/              # Design tokens (colors, spacing, fonts, motion)
└── constants.js             # Logo src, API URLs
```

### Authentication Flow

**AuthContext.jsx:**
- Stores `{ token, stage, user }`
- Stages: `pending_enrollment` → `face_required` → `authenticated`
- On signup/login: backend returns stage token
- On successful face verification: backend returns authenticated token

**ProtectedRoute.jsx:**
- Checks `auth.stage` before rendering
- Redirects to login if stage doesn't match

**Example Route Chain:**
```
/ (landing)
  → /signup (create account) → POST /auth/signup
  → /face-enrollment (required stage=pending_enrollment) → POST /face/enroll
  → /chat (required stage=authenticated)
OR
/ (landing)
  → /login (password) → POST /auth/login
  → /face-verification (required stage=face_required) → POST /face/verify
  → /chat (required stage=authenticated)
```

---

### Chat Page (`pages/ChatPage.jsx`)

**State Management:**
- `turns` — array of chat messages (role: 'assistant'|'user')
- `pendingForm` — fraud form data (only during interrupt)
- `busy` — loading indicator
- `error` — error message display
- `sessionValid` — backend session validation (calls GET /auth/me)

**Message Flow:**
1. User types message → ChatComposer → `POST /chat/message` (with thread_id for resume)
2. Backend returns `{ reply, table?, awaiting?, thread_id }`
3. If `awaiting` (interrupt):
   - Render FraudForm with `awaiting.fields`, `awaiting.schema`, `awaiting.errors`
   - User submits form → `POST /chat/message` with `resume=<submitted_form>`
   - Backend resumes graph from interrupt, validates, loops or continues
4. If `table`:
   - Render DataTable alongside assistant's text reply
5. If plain reply:
   - Append to turns

**Voice Support (Not Yet Implemented):**
- STT/TTS plumbing exists (`chat/providers/stt.py`, env vars `ELEVENLABS_TTS_KEY`)
- No UI component yet

---

### Design System

**Tokens** (in `styles/tokens/`):
- **base.css** — CSS custom properties reset
- **colors.css** — Brand palette (primary, secondary, danger, etc.)
- **spacing.css** — Scale (space-1 to space-12)
- **fonts.css** — Typography
- **typography.css** — Text styles
- **elevation.css** — Shadows/z-index
- **motion.css** — Transitions/animations

**Components (Reusable Primitives):**
- **core/** — Button, Card, Badge, Icon, IconButton, Logo (never hand-roll these)
- **forms/** — TextField, Select, Checkbox (prefilled from schema)
- **data/** — DataTable (renders backend result sets)
- **chat/** — ChatMessage, FraudForm, SuggestionChip
- **face/** — LiveCameraFrame (camera access)
- **feedback/** — Alert, Spinner, StatusSteps

---

### API Client (`api/client.js`)

**Endpoints Wrapped:**
- `auth.signup(payload)` → POST /auth/signup
- `auth.login(payload)` → POST /auth/login
- `auth.me(token)` → GET /auth/me
- `face.enroll(token, imageBytes)` → POST /face/enroll
- `face.verify(token, imageBytes)` → POST /face/verify
- `chat.message(token, threadId, message)` → POST /chat/message
- Error handling: wraps responses in `ApiError` exception

---

## Configuration & Deployment

### Environment Variables (`.env`)

**Required:**
```bash
JWT_SECRET_KEY=<random-secret>           # Change from default
COHERE_API_KEY=<key>                     # Speech-to-text
GROQ_API_KEY=<key>                       # LLM (Groq)
GEMINI_API_KEY=<key>                     # LLM (Google)
ELEVENLABS_TTS_KEY=<key>                 # Text-to-speech
```

**Optional (with defaults):**
```bash
DATABASE_URL=postgresql+psycopg2://etax:etax_pw@localhost:5432/etax
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
INSIGHTFACE_MODEL_PACK=buffalo_l
MATCH_THRESHOLD=0.45
LIVENESS_THRESHOLD=0.85
FACE_ENROLLMENT_TOKEN_TTL_MINUTES=15
FACE_VERIFICATION_TOKEN_TTL_MINUTES=10
SESSION_TOKEN_TTL_MINUTES=60

LLM_PROVIDER_ORDER=groq,gemini
GROQ_LLM_MODELS=openai/gpt-oss-20b,llama-3.3-70b-versatile
GEMINI_LLM_MODELS=gemini-2.0-flash
MODEL_COOLDOWN_SECONDS=60

STT_DETECT_PROVIDER=groq
STT_TRANSCRIBE_PROVIDER=cohere
GROQ_STT_MODEL=whisper-large-v3-turbo

TTS_PROVIDER_ORDER=elevenlabs,gemini
```

### Docker Compose

**Services:**
- **postgres** — PostgreSQL + pgvector
- **pgAdmin** — Database UI (admin@etax.com / admin123)
- **backend** — FastAPI (uvicorn with --reload)
- **frontend** — Node.js (Vite dev server)
- **Named volumes:**
  - `postgres_data` — persist PostgreSQL
  - `demo_tax_db` — persist SQLite (DEMO_DB_PATH)

**Startup:**
```bash
docker compose up --build
```

**Endpoints:**
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- pgAdmin: http://localhost:5050

---

## Key Constraints & Design Decisions

### 1. Two Independent Databases
- **PostgreSQL** holds real authentication + biometric data (sensitive)
- **SQLite** is demo-only, separate concern, never joined with auth
- Rationale: Separate security posture, easier to version the demo data

### 2. Staged Authentication
- Each step (signup, enrollment, verify) returns a **different stage token**
- Frontend routing respects stages (ProtectedRoute)
- Backend **independently enforces** stages on every request (security, not UX)
- Rationale: Multi-factor flow; face verification can't bypass password; prevents accidental enrollment without liveness

### 3. LLM Never Decides Facts
- **Fraud prediction** comes from XGBoost, not LLM guessing
- **Database answers** grounded in actual SQL rows returned
- **Intent routing** is Python dict lookup, never LLM-decided
- Rationale: Audit trail, reproducibility, guardrails against hallucination

### 4. All Chatbot Config is Env-Driven
- Provider order, model names, thresholds, DB paths all in `.env`
- Node logic is stateless (pure functions)
- Rationale: Ship different configs without code changes; multi-tenancy ready

### 5. Liveness Gating Both Enroll & Verify
- Passive anti-spoofing (MiniFASNetV2) prevents static attacks
- Defends against photo/screen/replay presentation attacks; doesn't defend against deep fakes or more sophisticated spoofing
- Rationale: Standard baseline; documented limitations

### 6. InMemorySaver Checkpointer (Not Durable)
- Chat interrupts stored in Python memory, cleared on restart
- Thread ID format: `{user_id}:{uuid}` (unique per session)
- Rationale: Fast iteration; production would use PostgreSQL checkpointer

### 7. Read-Only SQLite Connection
- OS-level write protection (file mode)
- Even a `DELETE` statement that bypassed validation would fail at the DB layer
- Rationale: Defense in depth

---

## Roadmap (Not Yet Implemented)

1. **Voice Input/Output** — STT/TTS plumbing exists, UI component missing
2. **Controlled SQL Subgraph** — Query repair loop, schema inspection
3. **`unclear` Intent Interrupt** — Ask user to clarify (fraud check vs. DB query)
4. **`multi_intent` Handling** — Split request into sub-questions
5. **Durable Chat Checkpoints** — PostgreSQL checkpointer instead of in-memory
6. **Tax Conversation Intent** — Real LLM node with knowledge base or retrieval
7. **Test Suite** — No pytest/eslint configured yet
8. **Linter Configuration** — No eslint, no isort, no mypy in CI/CD

---

## How to Run Locally

```bash
# 1. Clone repo (already done)

# 2. Set up environment
cp .env.example .env
# Edit .env: set JWT_SECRET_KEY, GROQ_API_KEY, GEMINI_API_KEY, etc.

# 3. Start all services
docker compose up --build

# 4. Verify
# Frontend: http://localhost:5173
# Backend docs: http://localhost:8000/docs
# pgAdmin: http://localhost:5050 (admin@etax.com/admin123)

# 5. Manual LLM smoke test (requires real API keys)
docker compose exec backend python -m app.chat._manual_test_intent

# 6. View logs
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f postgres
```

---

## Summary

| Component | Technology | Status |
|-----------|-----------|--------|
| **Auth** | FastAPI + SQLAlchemy + JWT | ✅ Complete |
| **Face Recognition** | InsightFace (ArcFace) + MiniFASNetV2 | ✅ Complete |
| **Fraud Assessment** | LLM extraction + XGBoost + UI form | ✅ Complete |
| **Database Queries** | LLM SQL generation + read-only SQLite | ✅ Complete (basic) |
| **Intent Routing** | Groq/Gemini with fallback + cooldown | ✅ Complete |
| **Chat UI** | React + design system tokens | ✅ Complete |
| **Face Enrollment UI** | Camera capture + liveness check | ✅ Complete |
| **Voice Input/Output** | Plumbing exists (providers/stt.py) | ⏳ Partial |
| **Placeholder Intents** | identity, tax_conversation, off_topic, unclear, multi_intent | ⏳ Stubs only |
| **SQL Repair Loop** | Planned for roadmap | ❌ Not started |
| **Durable Checkpoints** | Planned for roadmap | ❌ Not started |
| **Test Suite** | No pytest/eslint configured | ❌ Not started |

---

## Key Files Reference

**Backend Entry Points:**
- [main.py](backend/app/main.py) — FastAPI setup
- [chat/routes.py](backend/app/chat/routes.py) — POST /chat/message
- [auth/routes.py](backend/app/auth/routes.py) — POST /auth/signup, /login
- [face/routes.py](backend/app/face/routes.py) — POST /face/enroll, /verify

**Chatbot Nodes:**
- [chat/graph.py](backend/app/chat/graph.py) — LangGraph state machine
- [chat/fraud/engine.py](backend/app/chat/fraud/engine.py) — XGBoost prediction
- [chat/db/query_chain.py](backend/app/chat/db/query_chain.py) — SQL generation

**Frontend Entry Points:**
- [App.jsx](frontend/src/App.jsx) — Router setup
- [pages/ChatPage.jsx](frontend/src/pages/ChatPage.jsx) — Main chat UI
- [auth/AuthContext.jsx](frontend/src/auth/AuthContext.jsx) — Global auth state

**Configuration:**
- [.env.example](.env.example) — All env vars (copy to .env)
- [backend/app/config.py](backend/app/config.py) — Python config loader
- [docker-compose.yml](docker-compose.yml) — Service orchestration
