FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Anti-spoofing (liveness) model + code, same as mariam_face_recognition's
# Dockerfile — weights are committed directly in this repo (MIT-licensed),
# no manual download step.
RUN git clone --depth 1 https://github.com/minivision-ai/Silent-Face-Anti-Spoofing.git AntiSpoofing

COPY requirements.txt .

# CPU-only torch build — only used for the liveness model on CPU here.
# --extra-index-url lets pip pull torch's pure-python deps (typing-extensions,
# sympy, etc.) from regular PyPI: the pytorch CPU index alone doesn't serve
# their build dependencies (e.g. flit_core), and a metadata-name mismatch on
# that index otherwise forces pip into a source build that fails without them.
RUN pip install --no-cache-dir --default-timeout=180 --retries 10 \
    torch==2.2.0 --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple

RUN pip install --no-cache-dir --default-timeout=180 --retries 10 -r requirements.txt

COPY app ./app
COPY tests ./tests
COPY pytest.ini .

# Pre-warm both models at BUILD time (not on the first live request).
RUN python -c "from insightface.app import FaceAnalysis; FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']).prepare(ctx_id=0, det_size=(640, 640))"
RUN python -c "import sys; sys.path.insert(0, '/workspace'); from app.face import liveness_engine; liveness_engine.get_model(); print('anti-spoofing model loaded ok')"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
