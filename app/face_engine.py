"""
Face detection + embedding using InsightFace (ArcFace), matching the first
working approach from the exploration notebook.

Unlike AdaFace, InsightFace's model pack (detector + recognition model) is
downloaded automatically on first use — no manual Google Drive step, which
is why this is the "ready to deploy" option.
"""
import io
import cv2
import numpy as np
from PIL import Image
from insightface.app import FaceAnalysis

from app.config import INSIGHTFACE_MODEL_PACK

_app = None


class NoFaceDetected(Exception):
    pass


def get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        # CPUExecutionProvider works everywhere out of the box. Swap to
        # CUDAExecutionProvider (and install onnxruntime-gpu instead of
        # onnxruntime) if you have a GPU available.
        _app = FaceAnalysis(
            name=INSIGHTFACE_MODEL_PACK, providers=["CPUExecutionProvider"]
        )
        _app.prepare(ctx_id=0, det_size=(640, 640))
    return _app


def _bgr_from_bytes(image_bytes: bytes) -> np.ndarray:
    pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


def detect(image_bytes: bytes):
    """
    Detect the largest face in the image. Returns (img_bgr, face) where
    `face` is InsightFace's Face object (has .bbox, .normed_embedding, ...)
    and img_bgr is the full decoded frame — both are needed by the liveness
    check, which re-crops the same face at its own scale/size.
    Raises NoFaceDetected if no face is found.
    """
    img_bgr = _bgr_from_bytes(image_bytes)
    faces = get_app().get(img_bgr)
    if not faces:
        raise NoFaceDetected("Could not detect a face in the supplied image.")

    # If multiple faces are present, use the largest bounding box (closest
    # to the camera) — the typical case for a single-user auth kiosk.
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return img_bgr, face


def get_embedding(image_bytes: bytes) -> np.ndarray:
    """Convenience wrapper: detect + return just the 512-d embedding."""
    _, face = detect(image_bytes)
    return face.normed_embedding.astype(np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
