# Face Recognition Service — ArcFace (InsightFace) + Liveness Detection + PostgreSQL/pgvector

A ready-to-deploy face login service: capture a **live** face, run an
anti-spoofing check, then compare it against enrolled clients in the
database — greet known users by name, or enroll new ones on the spot. No
manual model downloads — everything runs with a single `docker compose up`.

## How it works

```
Browser webcam (live frame, never a file upload)
     → Face Detection (InsightFace / ArcFace, buffalo_l pack)
     → Liveness check (MiniFASNetV2 anti-spoofing) — REJECTS photos/screens here
     → 512-D normalized embedding
     → Nearest-neighbor search in Postgres (pgvector, cosine similarity)
     → similarity ≥ threshold → "known"   → return the matched name
     → similarity < threshold → "unknown" → enroll via /register
```

Only the embedding vector is stored (not raw images), which keeps lookups
fast and avoids storing biometric images unnecessarily.

## Why this setup

- **ArcFace/InsightFace** instead of AdaFace: its model pack downloads
  automatically on first build — no manual Google Drive checkpoint step.
- **MiniFASNetV2** (minivision-ai/Silent-Face-Anti-Spoofing) for liveness:
  weights are committed directly in that repo too — same "no manual
  download" deployability, MIT-licensed.
- **Live camera capture only** (`/ui`): the frontend grabs frames straight
  from `getUserMedia()`, never a file picker — closing off the "upload any
  photo you want" path entirely, not just filtering it after the fact.

## ⚠️ Security model — read this before using it for real login

This now has **two independent layers** against a photo/screen fooling it:
1. The `/ui` page only ever sends live webcam frames, no file uploads.
2. Every `/recognize` and `/register` call is gated by a liveness check —
   a spoofed face gets a `403` and never reaches identity matching at all.

**What this does defend against:** a printed photo or a phone/tablet screen
held up to the camera — exactly what fooled the earlier version of this
project.

**What this does *not* defend against**, and what you should know before
treating this as a full login system:
- **A high-quality 3D mask or prosthetic.** No single-frame check reliably catches these.
- **A compromised or virtual camera feed.** If an attacker can inject frames
  before they reach the browser (a virtual webcam driver, a rooted device,
  a man-in-the-middle on the API itself), the liveness model only ever sees
  what it's given. Liveness detection secures *what's in front of the
  camera*, not the integrity of the camera pipeline itself.
- **Replay of a recorded video of the real person's face**, which can pass
  a single-frame check that a static photo would fail. If this matters for
  your threat model, add an **active** challenge on top (e.g. "blink now" /
  "turn your head" verified across a few frames) — this project only
  implements the passive, single-frame check.
- **API abuse independent of the face check**: rate limiting, HTTPS, and
  authenticating *who* is allowed to call `/register` at all are still your
  responsibility — see the deployment checklist below.

Treat this as a strong second factor or a convenience layer, not as the
sole gate on anything highly sensitive, without adding the items above.

## Project structure

```
face_recognition_system/
├── docker-compose.yml    # Postgres+pgvector + API
├── Dockerfile
├── requirements.txt
└── app/
    ├── config.py          # env vars, similarity/liveness thresholds
    ├── face_engine.py     # InsightFace: detect + embed
    ├── liveness_engine.py # MiniFASNetV2: real vs. spoof check
    ├── db.py               # Postgres/pgvector: register / find_closest
    ├── main.py              # FastAPI: /register /recognize /health
    └── static/index.html    # Live-camera UI, served at /ui
```

## API

**POST `/recognize`** — multipart `image` (a live-captured frame)
```json
{"status": "known", "name": "Ahmed Mostafa", "person_id": 3, "similarity": 0.71, "liveness_confidence": 0.97}
```
or
```json
{"status": "unknown", "similarity": 0.22, "liveness_confidence": 0.94}
```
or, if the face fails the liveness check — `403`:
```json
{"detail": "Liveness check failed (confidence=0.310). This looks like a photo, screen, or other spoof rather than a live face."}
```

**POST `/register`** — multipart `name` + `image`
```json
{"person_id": 4, "name": "Sara Ali", "liveness_confidence": 0.96}
```
Also liveness-gated (`403` on spoof) and rejects enrollment (`409`) if the
face already matches an existing person.

**GET `/health`**

## Run it

```bash
docker compose up --build
```

No model files to fetch by hand. First build takes a while — both model
packs (InsightFace + MiniFASNetV2) are pulled and pre-warmed during the
build itself, not on the first live request.

- **Live camera UI**: `http://localhost:8000/ui`
- **API / Swagger docs**: `http://localhost:8000/docs`
- **DB**: `localhost:5432`

Open `/ui`, allow camera access, then use "Recognize" or "Register as new
person" — both buttons capture a fresh frame from the live video feed.

## Deployment checklist

- Set real secrets (`POSTGRES_PASSWORD`, etc.) via `.env`, not hardcoded.
- Put the API behind a reverse proxy (nginx/Traefik) with **HTTPS** —
  browsers require a secure origin (HTTPS or `localhost`) for camera access
  anyway, so this isn't optional once you're off `localhost`.
- Add authentication/rate-limiting in front of `/register` and `/recognize`
  — they're open by default. `/register` in particular should require an
  authenticated admin/operator session in most real deployments, not be
  open to anyone who loads the page.
- For GPU throughput: install `onnxruntime-gpu` instead of `onnxruntime`
  (InsightFace) and a CUDA-enabled `torch` build (liveness model).
- Back up the Postgres volume regularly (it holds every enrolled embedding).
- Tune both thresholds against real captures **and real spoof attempts**
  from your own camera setup before trusting the defaults:
  - `MATCH_THRESHOLD` (default `0.45`) — identity match strictness.
  - `LIVENESS_THRESHOLD` (default `0.85`) — anti-spoofing strictness. Lower
    it if real users get falsely rejected too often; raise it if spoofs
    still get through.

## Troubleshooting

**A request to `/register` or `/recognize` hangs forever ("Loading" in Swagger):**
Both model packs are baked into the image at build time, so this shouldn't
happen on a fresh build. If it still does:
- Check `docker compose logs -f api` for errors.
- Confirm the container has internet access at *build* time:
  `docker exec -it <api_container> curl -I https://github.com`
- Rebuild from scratch: `docker compose build --no-cache api`

**Camera doesn't start on `/ui`:** browsers block `getUserMedia()` on
non-secure origins. `http://localhost:8000` is allowed by default; anything
else needs HTTPS.
