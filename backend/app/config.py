import os


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://etax:etax_pw@localhost:5432/etax"
)

# --- Restricted DB role for executing user/LLM-generated SQL ---
# A separate, unprivileged Postgres login (app_agent) — not the table-owning
# superuser DATABASE_URL connects as — used only by app/chat/services/sql_runner.py
# to run ownership-aware, view-restricted queries with RLS enforced. Never
# hardcode a real password here; the dev default below matches this
# project's existing convention for local-only credentials (see
# POSTGRES_PASSWORD/JWT_SECRET_KEY dev defaults) and must be overridden for
# any real deployment via the env var. Kept as two vars (not just parsed out
# of the URL) because security_setup.py's CREATE/ALTER ROLE needs the raw
# password value, not an assembled connection string.
APP_AGENT_DB_USER = os.getenv("APP_AGENT_DB_USER", "app_agent")
APP_AGENT_DB_PASSWORD = os.getenv("APP_AGENT_DB_PASSWORD", "5")
APP_AGENT_DATABASE_URL = os.getenv(
    "APP_AGENT_DATABASE_URL",
    f"postgresql+psycopg2://{APP_AGENT_DB_USER}:{APP_AGENT_DB_PASSWORD}@localhost:5432/etax",
)

# --- Auth / sessions ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
# Stage tokens are deliberately short-lived: each one only unlocks the next
# step of the sign-in sequence, not the whole session.
FACE_ENROLLMENT_TOKEN_TTL_MINUTES = int(os.getenv("FACE_ENROLLMENT_TOKEN_TTL_MINUTES", "15"))
FACE_VERIFICATION_TOKEN_TTL_MINUTES = int(os.getenv("FACE_VERIFICATION_TOKEN_TTL_MINUTES", "10"))
# The "authenticated" session is sliding, not fixed-duration: app/auth/
# dependencies.py's require_authenticated stamps auth.users.last_active_at
# on every request and rejects it once more than
# SESSION_INACTIVITY_TIMEOUT_MINUTES has passed since the last one — that
# check, not the JWT's own expiry, is the real session-length enforcement.
# SESSION_TOKEN_TTL_MINUTES is just the outer ceiling on the token itself
# (a plain JWT's `exp` is fixed at issuance and can't slide on its own), set
# well above the inactivity window so it's never what actually ends an
# active session.
SESSION_TOKEN_TTL_MINUTES = int(os.getenv("SESSION_TOKEN_TTL_MINUTES", "480"))
SESSION_INACTIVITY_TIMEOUT_MINUTES = int(os.getenv("SESSION_INACTIVITY_TIMEOUT_MINUTES", "60"))

ALLOWED_ORIGINS = _env_list(
    "ALLOWED_ORIGINS", ["http://localhost:5173", "http://localhost:3000"]
)

# --- Face recognition (InsightFace / ArcFace) ---
# Same buffalo_l pack and thresholding approach as the mariam_face_recognition
# reference project (used only as a reference — not a dependency of this app).
INSIGHTFACE_MODEL_PACK = os.getenv("INSIGHTFACE_MODEL_PACK", "buffalo_l")
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.45"))
EMBEDDING_DIM = 512

# --- Liveness / anti-spoofing (MiniFASNetV2, minivision-ai/Silent-Face-Anti-Spoofing) ---
ANTISPOOF_MODEL_PATH = os.getenv(
    "ANTISPOOF_MODEL_PATH",
    "/workspace/AntiSpoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth",
)
LIVENESS_THRESHOLD = float(os.getenv("LIVENESS_THRESHOLD", "0.85"))
