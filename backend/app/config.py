import os


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://etax:etax_pw@localhost:5432/etax"
)

# --- Auth / sessions ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
# Stage tokens are deliberately short-lived: each one only unlocks the next
# step of the sign-in sequence, not the whole session.
FACE_ENROLLMENT_TOKEN_TTL_MINUTES = int(os.getenv("FACE_ENROLLMENT_TOKEN_TTL_MINUTES", "15"))
FACE_VERIFICATION_TOKEN_TTL_MINUTES = int(os.getenv("FACE_VERIFICATION_TOKEN_TTL_MINUTES", "10"))
SESSION_TOKEN_TTL_MINUTES = int(os.getenv("SESSION_TOKEN_TTL_MINUTES", "60"))

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
