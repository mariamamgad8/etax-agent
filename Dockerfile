FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Anti-spoofing (liveness) model + code. Weights are committed directly in
# this repo (small, MIT-licensed) — no manual download step, same as
# InsightFace below.
RUN git clone --depth 1 https://github.com/minivision-ai/Silent-Face-Anti-Spoofing.git AntiSpoofing

COPY requirements.txt .

# CPU-only torch build (~200MB) instead of the default CUDA build (~755MB)
# — we only run the liveness model on CPU here, so the GPU libs are pure
# dead weight. This alone cuts the slowest part of the build by ~3-4x.
RUN pip install --no-cache-dir --default-timeout=180 --retries 10 \
    torch==2.2.0 --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir --default-timeout=180 --retries 10 -r requirements.txt

COPY app ./app

# Pre-warm both models at BUILD time (not on the first live request). This
# avoids the API hanging/blocking on its first call, and means the
# container works offline after being built once.
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']).prepare(ctx_id=0, det_size=(640, 640))"
RUN python -c "import sys; sys.path.insert(0, '/workspace'); from app import liveness_engine; liveness_engine.get_model(); print('anti-spoofing model loaded ok')"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
