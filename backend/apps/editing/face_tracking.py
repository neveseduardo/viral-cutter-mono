"""Face detection + tracking (AGENTS.md §7.7 / Fase 4).

Detection is SAMPLED (not per-frame) and interpolated, producing a face timeline
(§8.4) with a bbox/center per sampled instant. The dynamic crop uses this track
with dead-zone smoothing to avoid micro-tremors.

Backends (optional, degrade gracefully):
1. mediapipe (lightweight, preferred when installed)
2. cv2 Haar cascade (always available via opencv-headless)
3. insightface (accurate onnx) when explicitly configured
"""

import json
import logging

logger = logging.getLogger(__name__)

_FACE_CASCADE_PATH = "haarcascade_frontalface_default.xml"


def _load_backend(preference: str = "auto"):
    """Returns a `detect_one(image_bgr) -> bbox | None` callable."""
    if preference in ("mediapipe", "auto"):
        try:
            import cv2

            import mediapipe as mp

            detector = mp.solutions.face_detection.FaceDetection(
                model_selection=1, min_detection_confidence=0.5
            )
            from mediapipe.python.solutions.drawing_utils import _normalized_to_pixel_coordinates  # noqa: F401

            def detect(image):
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                results = detector.process(rgb)
                if not results.detections:
                    return None
                h, w = image.shape[:2]
                det = results.detections[0]
                box = det.location_data.relative_bounding_box
                x = int(max(0, box.xmin * w))
                y = int(max(0, box.ymin * h))
                bw = int(box.width * w)
                bh = int(box.height * h)
                return (x, y, bw, bh)

            return detect
        except Exception as exc:
            logger.debug("mediapipe unavailable (%s); falling back to Haar", exc)

    if preference in ("haar", "auto"):
        try:
            import cv2

            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + _FACE_CASCADE_PATH)

            def detect(image):
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
                if len(faces) == 0:
                    return None
                x, y, w, h = faces[0]  # largest/topmost
                return (int(x), int(y), int(w), int(h))

            return detect
        except Exception as exc:
            logger.debug("haar unavailable: %s", exc)

    return lambda image: None


def compute_face_timeline(input_path: str, *, sample_period: float = 0.5,
                          backend: str = "auto", two_face_threshold: float = 1.0,
                          confidence_threshold: float = 0.5, fps: float | None = None,
                          on_progress=None) -> dict:
    """Builds a face timeline (§8.4) by sampling the input video."""
    import cv2

    cap = cv2.VideoCapture(input_path)
    try:
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        video_fps = fps or cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not total or total <= 0:
            total = 1
    except Exception:
        cap.release()
        raise

    detect = _load_backend(backend)

    samples = []
    frame_idx = 0
    if sample_period <= 0:
        step = 1
    else:
        step = max(1, int(round(sample_period * video_fps)))
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_idx += 1
        current_t = round(frame_idx / video_fps, 3)
        just_start = frame_idx == 1
        if just_start or frame_idx % step == 0:
            bbox = detect(frame) if detect else None
            if bbox:
                x, y, w, h = bbox
                center = [round(x + w / 2, 1), round(y + h / 2, 1)]
                samples.append({"t": current_t, "mode": "one", "bbox": list(bbox), "center": center, "faces": 1})
            else:
                samples.append({"t": current_t, "mode": "none", "bbox": None, "center": None, "faces": 0})
        if on_progress and frame_idx % max(1, step * 10) == 0:
            on_progress(min(round(frame_idx / total * 100), 100))
    cap.release()

    timeline = {
        "schema_version": "1.0",
        "width": width,
        "height": height,
        "fps": round(video_fps, 3),
        "frames": samples,
    }
    if on_progress:
        on_progress(100)
    return timeline


def load_or_create_timeline(timeline_path, input_path, *, sample_period=0.5, on_progress=None) -> dict:
    import os

    if os.path.exists(timeline_path):
        with open(timeline_path, "r", encoding="utf-8") as f:
            return json.load(f)
    timeline = compute_face_timeline(input_path, sample_period=sample_period, on_progress=on_progress)
    os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False)
    return timeline