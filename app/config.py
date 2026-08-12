import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://faceapp:faceapp_pw@localhost:5432/face_auth"
)

# insightface model pack. "buffalo_l" is downloaded automatically on first
# run (cached under /root/.insightface/models — persisted via the
# insightface_models volume in docker-compose.yml).
INSIGHTFACE_MODEL_PACK = os.getenv("INSIGHTFACE_MODEL_PACK", "buffalo_l")

# Cosine similarity threshold for "same person". ArcFace (buffalo_l)
# typically separates genuine/impostor pairs cleanly around 0.45-0.5 on
# normalized embeddings — tune against your own enrolled users.
MATCH_THRESHOLD = float(os.getenv("MATCH_THRESHOLD", "0.45"))
EMBEDDING_DIM = 512

# --- Liveness / anti-spoofing (MiniFASNetV2, minivision-ai/Silent-Face-Anti-Spoofing) ---
ANTISPOOF_MODEL_PATH = os.getenv(
    "ANTISPOOF_MODEL_PATH",
    "/workspace/AntiSpoofing/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth",
)
# Minimum "real face" confidence (0-1) required to pass. Higher = stricter
# (more false rejections of real users), lower = more permissive (more risk
# of a spoof getting through). Tune against real captures + real attack
# attempts (printed photo, phone screen) from your own camera setup before
# relying on this for production login.
LIVENESS_THRESHOLD = float(os.getenv("LIVENESS_THRESHOLD", "0.85"))
