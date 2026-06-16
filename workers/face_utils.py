"""
Face detection + recognition helpers for the active censorship pipeline.

Uses OpenCV's built-in YuNet detector and SFace recognizer (both ONNX-backed)
so no extra Python dependencies are needed beyond opencv-python.
"""
import os
import cv2
import numpy as np
from blur_strength import pixelate_factor, opencv_blur_kernel

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODELS_DIR = os.path.join(_PROJECT_ROOT, "models_cache", "face")
DET_PATH = os.path.join(_MODELS_DIR, "face_detection_yunet_2023mar.onnx")
REC_PATH = os.path.join(_MODELS_DIR, "face_recognition_sface_2021dec.onnx")

# Cosine similarity threshold above which two face embeddings are considered
# the same identity. SFace's own docs recommend ~0.363 for cosine.
SIMILARITY_THRESHOLD = 0.363


class FaceEngine:
    """Lazy-loaded YuNet + SFace pair. One instance per worker."""

    def __init__(self):
        self._detector = None
        self._recognizer = None

    def _ensure_loaded(self, w, h):
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN_create(
                DET_PATH, "", (320, 320), 0.6, 0.3, 5000
            )
            self._recognizer = cv2.FaceRecognizerSF_create(REC_PATH, "")
        self._detector.setInputSize((w, h))

    def detect(self, frame_bgr):
        """Return list of YuNet face rows [x, y, w, h, lm5x2, score], or empty list."""
        h, w = frame_bgr.shape[:2]
        self._ensure_loaded(w, h)
        _, faces = self._detector.detect(frame_bgr)
        return faces if faces is not None else []

    def embed(self, frame_bgr, face_row):
        """Compute an SFace embedding for one face within frame_bgr."""
        self._ensure_loaded(frame_bgr.shape[1], frame_bgr.shape[0])
        aligned = self._recognizer.alignCrop(frame_bgr, face_row)
        return self._recognizer.feature(aligned)

    def cosine(self, emb_a, emb_b):
        """SFace cosine similarity in [-1, 1]; higher = more similar."""
        return float(self._recognizer.match(emb_a, emb_b, cv2.FaceRecognizerSF_FR_COSINE))

    def embed_reference(self, image_path):
        """Load a reference photo and return the embedding of its largest face."""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not read reference image: {image_path}")
        faces = self.detect(img)
        if len(faces) == 0:
            raise ValueError("No face detected in the reference photo.")
        # Pick the largest face by bbox area
        largest = max(faces, key=lambda f: f[2] * f[3])
        return self.embed(img, largest)


def apply_region_effect(frame, x, y, w, h, mode, strength=5):
    """Mutate `frame` in place by applying mode ∈ {'blur','pixelate','box'} to the region."""
    H, W = frame.shape[:2]
    x = max(0, int(x)); y = max(0, int(y))
    w = min(W - x, int(w)); h = min(H - y, int(h))
    if w <= 1 or h <= 1:
        return
    region = frame[y:y + h, x:x + w]
    if mode == "pixelate":
        f = pixelate_factor(strength)
        sw = max(1, w // f); sh = max(1, h // f)
        small = cv2.resize(region, (sw, sh), interpolation=cv2.INTER_AREA)
        frame[y:y + h, x:x + w] = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    elif mode == "box":
        frame[y:y + h, x:x + w] = 0
    else:  # blur (default)
        # Kernel scaled to face size AND the chosen strength (odd).
        k = opencv_blur_kernel(w, h, strength)
        frame[y:y + h, x:x + w] = cv2.GaussianBlur(region, (k, k), 0)
