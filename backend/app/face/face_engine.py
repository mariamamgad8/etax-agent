"""
Face detection + embedding using InsightFace (ArcFace).

Same buffalo_l model pack, detection/embedding approach and largest-face
selection as the mariam_face_recognition reference project, reimplemented
here as a standalone module with no dependency on that package.
"""
import io

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image

from app.config import INSIGHTFACE_MODEL_PACK

_app = None


class NoFaceDetected(Exception):
    pass


def get_app() -> FaceAnalysis:
    global _app
    if _app is None:
        # CPUExecutionProvider works everywhere out of the box. Swap to
        # CUDAExecutionProvider (and install onnxruntime-gpu instead of
        # onnxruntime) if a GPU is available.
        _app = FaceAnalysis(name=INSIGHTFACE_MODEL_PACK, providers=["CPUExecutionProvider"])
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
    # to the camera) — the typical case for a single-user auth flow.
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return img_bgr, face
