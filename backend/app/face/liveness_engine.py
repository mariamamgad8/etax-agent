"""
Passive face anti-spoofing (liveness) check using MiniFASNetV2 from
minivision-ai/Silent-Face-Anti-Spoofing, applied to the exact face crop
InsightFace already located — so we get a "real vs. spoof" verdict on the
same face we're about to run recognition on, with only one extra model pass.

Same preprocessing and thresholding approach as the mariam_face_recognition
reference project, reimplemented here as a standalone module. It blocks a
printed/phone-screen photo of an enrolled face being accepted as a live
sign-in; it does not defend against a high-quality 3D mask or a compromised
camera feed — no single-frame check does. See
mariam_face_recognition/README.md for the full threat-model notes.

Source repo (MIT-licensed) is vendored at build time in the Dockerfile via
`git clone`; model weights are committed directly in that repo.
"""
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F

# The cloned repo uses `from src.model_lib...` style absolute imports, so
# its root needs to be on sys.path.
_ANTISPOOF_REPO_ROOT = "/workspace/AntiSpoofing"
if _ANTISPOOF_REPO_ROOT not in sys.path:
    sys.path.insert(0, _ANTISPOOF_REPO_ROOT)

from src.generate_patches import CropImage  # noqa: E402
from src.model_lib.MiniFASNet import MiniFASNetV2  # noqa: E402
from src.utility import get_kernel, parse_model_name  # noqa: E402

from app.config import ANTISPOOF_MODEL_PATH, LIVENESS_THRESHOLD

_device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
_model = None
_cropper = CropImage()
_H_INPUT, _W_INPUT, _MODEL_TYPE, _SCALE = parse_model_name(os.path.basename(ANTISPOOF_MODEL_PATH))


def get_model():
    global _model
    if _model is None:
        kernel_size = get_kernel(_H_INPUT, _W_INPUT)
        _model = MiniFASNetV2(conv6_kernel=kernel_size).to(_device)
        state_dict = torch.load(ANTISPOOF_MODEL_PATH, map_location=_device)

        # This checkpoint was saved from a torch.nn.DataParallel-wrapped
        # model, so every key is prefixed with "module." — strip it before
        # loading into our plain model, exactly as the upstream repo does.
        first_key = next(iter(state_dict))
        if first_key.startswith("module."):
            state_dict = {k[len("module."):]: v for k, v in state_dict.items()}

        _model.load_state_dict(state_dict)
        _model.eval()
    return _model


def check_liveness(img_bgr: np.ndarray, bbox_xyxy) -> tuple[bool, float]:
    """
    img_bgr: full frame, BGR uint8 (same array face_engine already has).
    bbox_xyxy: (x1, y1, x2, y2) face box, e.g. InsightFace's face.bbox.

    Returns (is_live, confidence): confidence is the model's score (0-1) for
    the "real face" class. A failed check is a hard reject — callers must
    not proceed to identity matching on is_live=False.
    """
    x1, y1, x2, y2 = [int(v) for v in bbox_xyxy]
    bbox_xywh = [x1, y1, x2 - x1, y2 - y1]

    patch = _cropper.crop(
        org_img=img_bgr,
        bbox=bbox_xywh,
        scale=_SCALE,
        out_w=_W_INPUT,
        out_h=_H_INPUT,
        crop=True,
    )

    # Matches the repo's own preprocessing exactly: HWC->CHW, float, NO /255
    # normalization (the model was trained on raw 0-255 pixel values).
    tensor = torch.from_numpy(patch.transpose((2, 0, 1))).float().unsqueeze(0).to(_device)

    model = get_model()
    with torch.no_grad():
        logits = model(tensor)
        probs = F.softmax(logits, dim=1).cpu().numpy()[0]

    label = int(np.argmax(probs))  # label 1 == real face (repo convention)
    confidence = float(probs[label])

    is_live = (label == 1) and (confidence >= LIVENESS_THRESHOLD)
    return is_live, confidence
