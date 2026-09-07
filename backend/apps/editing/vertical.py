"""9:16 cinematic reframing following faces (AGENTS.md §7.7 / Fase 4A/4B).

Pipeline per cut video:
  timeline (sampled face centers) → interpolated track → dynamic crop window
  with dead-zone smoothing → per-frame BGR written to a rawvideo ffmpeg subprocess
  → audio muxed from the source.

Fallback modes when no face is present: `padding` (blur bars) or `zoom`
(central zoomed crop) — configurable.
"""

import logging

logger = logging.getLogger(__name__)


def _sample_at(timeline: dict, t: float):
    """Returns nearest (linear-interpolated) track sample with center/bbox."""
    frames = timeline.get("frames", [])
    if not frames:
        return {"mode": "none", "center": None, "bbox": None}
    if t <= frames[0]["t"]:
        return frames[0]
    if t >= frames[-1]["t"]:
        return frames[-1]
    for i in range(1, len(frames)):
        if frames[i]["t"] >= t:
            a, b = frames[i - 1], frames[i]
            if a["mode"] == "none" and b["mode"] == "none":
                return {"mode": "none", "center": None, "bbox": None}
            if a["center"] is None or b["center"] is None:
                return b if b["mode"] != "none" else a
            span = b["t"] - a["t"]
            alpha = (t - a["t"]) / span if span > 0 else 0
            return {
                "mode": "one",
                "center": [
                    a["center"][0] + (b["center"][0] - a["center"][0]) * alpha,
                    a["center"][1] + (b["center"][1] - a["center"][1]) * alpha,
                ],
                "bbox": a["bbox"],
            }
    return frames[-1]


def _crop_window(center, width, height, target_ratio: float, dead_zone: float = 0.03) -> list:
    """Returns [x, y, w, h] in source pixel space that matches target_ratio.

    Window is anchored at `center` but only moves when the center drifts beyond
    a dead-zone relative to the window size (avoids micro-jitter)."""
    if center is None:
        center = [width / 2, height / 2]
    if target_ratio >= 1:
        crop_w = width
        crop_h = round(crop_w / target_ratio)
        crop_h = min(crop_h, height)
        crop_x = 0
        crop_y = int(max(0, min(height - crop_h, center[1] - crop_h / 2)))
    else:
        crop_h = height
        crop_w = round(crop_h * target_ratio)
        crop_w = min(crop_w, width)
        crop_y = 0
        crop_x = int(max(0, min(width - crop_w, center[0] - crop_w / 2)))
    return [crop_x, crop_y, crop_w, crop_h]


class _Cam:
    """Dead-zone camera that eases the crop window toward the tracked center."""

    def __init__(self, width, height, target_w, target_h, dead_zone=0.03, ease=0.2):
        self.width, self.height = width, height
        self.target_w, self.target_h = target_w, target_h
        self.ratio = target_w / target_h
        self.dead_zone = dead_zone
        self.ease = ease
        self.window = None  # [x, y, w, h] in source coords

    def reset(self, center=None):
        self.window = _crop_window(center, self.width, self.height, self.ratio, 0)

    def update(self, center, force=False):
        if self.window is None:
            self.reset(center)
            return self.window
        x, y, w, h = self.window
        cx, cy = x + w / 2, y + h / 2
        dx = center[0] - cx
        dy = center[1] - cy
        dz = self.dead_zone * min(w, h)
        if abs(dx) <= dz and abs(dy) <= dz:
            return self.window
        # ease toward the face within the max travel allowed by the window
        max_travel_x = self.width - w
        max_travel_y = self.height - h

        def target_axis(c, d, size, max_travel):
            target = c + d * self.ease
            return max(0, min(max_travel, target))

        if not force and w < self.width:
            new_x = target_axis(x, dx, w, max_travel_x)
        else:
            new_x = x
        if not force and h < self.height:
            new_y = target_axis(y, dy, h, max_travel_y)
        else:
            new_y = y
        self.window = [round(new_x), round(new_y), w, h]
        return self.window


def process_vertical(input_path: str, output_path: str, timeline: dict | None,
                     *, target_w: int = 1080, target_h: int = 1920, face_mode: str = "auto",
                     no_face_mode: str = "zoom", dead_zone: float = 0.03,
                     encoder: str = "", crf: str = "20", preset: str = "veryfast",
                     job_id=None, on_progress=None) -> str:
    """Reframes a cut video to target_w×target_h, following faces when available."""
    import subprocess

    import cv2

    from apps.media.engine import _persistent_process

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"não foi possível abrir {input_path}")

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1

    # pick encoder
    enc = getattr(cfg(), "FFMPEG_ENCODER", "") or encoder
    if "nvenc" in enc.lower():
        video_args = ["-c:v", enc, "-preset", "p4", "-b:v", "5M", "-pix_fmt", "yuv420p"]
    else:
        video_args = ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]

    raw_w, raw_h = target_w, target_h
    ffmpeg = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{raw_w}x{raw_h}", "-pix_fmt", "bgr24", "-r", f"{fps}",
        "-i", "pipe:0",
        "-an",
        *video_args,
        "-movflags", "+faststart",
        output_path,
    ]
    proc = subprocess.Popen(
        ffmpeg,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _persistent_process(job_id, proc)

    cam = _Cam(src_w, src_h, target_w, target_h, dead_zone=dead_zone, ease=0.25)
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            t = frame_idx / fps
            sample = _sample_at(timeline, t) if timeline else {"mode": "none", "center": None}
            no_face = sample.get("center") is None
            if no_face and no_face_mode == "padding":
                bg = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
                bg = cv2.GaussianBlur(bg, (25, 25), 0)
                scale = min(target_w / src_w, target_h / src_h)
                fw, fh = max(1, int(src_w * scale)), max(1, int(src_h * scale))
                fg = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_LINEAR)
                x0 = (target_w - fw) // 2
                y0 = (target_h - fh) // 2
                out = bg.copy()
                out[y0:y0 + fh, x0:x0 + fw] = fg
            else:
                if sample.get("center") is not None:
                    win = cam.update(sample["center"])
                elif frame_idx == 1:
                    cam.reset()
                    win = cam.window
                else:
                    win = cam.window
                if win is None:
                    win = _crop_window([src_w / 2, src_h / 2], src_w, src_h, target_w / target_h, 0)

                x, y, w, h = win
                x = max(0, min(x, src_w - 1))
                y = max(0, min(y, src_h - 1))
                w = max(1, min(w, src_w - x))
                h = max(1, min(h, src_h - y))
                crop = frame[y:y + h, x:x + w]
                out = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            proc.stdin.write(out.tobytes())
            if on_progress and frame_idx % max(1, int(fps)) == 0:
                on_progress(min(round(frame_idx / total * 100, 1), 99))
    finally:
        cap.release()
        if proc.stdin:
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass

    proc.wait()
    _persistent_process(job_id, None)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg reframe falhou (código {proc.returncode})")

    _mux_audio(input_path, output_path, job_id=job_id)
    if on_progress:
        on_progress(100)
    return output_path


def _mux_audio(source: str, target: str, *, job_id=None) -> None:
    """Copies the source audio track into the reframed video (no re-encode)."""
    import subprocess

    from apps.media.engine import _persistent_process

    tmp = target + ".mux.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-i", target,
        "-i", source,
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c", "copy",
        "-shortest",
        tmp,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _persistent_process(job_id, proc)
    proc.wait()
    _persistent_process(job_id, None)
    if proc.returncode != 0:
        raise RuntimeError(f"mux de áudio falhou (código {proc.returncode})")
    import os

    os.replace(tmp, target)


def cfg():
    from django.conf import settings

    return settings