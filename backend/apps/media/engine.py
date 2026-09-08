"""Media Engine — single choke-point for all FFmpeg/ffprobe operations.

AGENTS.md §6: "Criar uma camada única que encapsula **todas** as operações de
FFmpeg/ffprobe.  Nenhuma regra de negócio deve espalhar chamadas de
subprocess/FFmpeg pelo projeto."

Public surface:
    probe(path)                           → dict
    cut(src_key, dst_key, start, duration, *, job_id, encoder, crf, preset)
    extract_audio(src_key, dst_key, *, job_id, log_sink, on_progress)
    burn_subtitles(src_key, ass_key, dst_key, *, job_id, total_duration, on_progress)
    thumbnail(src_key, dst_key, *, time_s)
    cancel_processes(tags)                → int (number cancelled)
    cancel_job_processes(job_id)          → int
    _persistent_process(job_id, proc)     (internal — used by vertical.py)

Exceptions:
    MediaEngineError     — non-retryable media/data errors
    ProcessCancelled     — raised when a tracked process is interrupted
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

from django.conf import settings

from .storage import abs_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MediaEngineError(Exception):
    """Non-retryable media/data error (bad file, missing stream, etc.)."""


class ProcessCancelled(Exception):
    """Raised when a tracked FFmpeg process is cancelled via cancel_processes()."""


# ---------------------------------------------------------------------------
# Process registry — tracks running subprocesses for cancellation
# ---------------------------------------------------------------------------
# Structure: { tag: set[subprocess.Popen] }
# Tags used: f"job:{job_id}", f"run:{run_id}", f"job_any:{run_id}"

_process_lock = threading.Lock()
_active: dict[str, set[subprocess.Popen]] = {}


def _register(proc: subprocess.Popen, tags: set[str]) -> None:
    with _process_lock:
        for tag in tags:
            _active.setdefault(tag, set()).add(proc)


def _unregister(proc: subprocess.Popen, tags: set[str]) -> None:
    with _process_lock:
        for tag in tags:
            bucket = _active.get(tag)
            if bucket:
                bucket.discard(proc)
                if not bucket:
                    del _active[tag]


def _persistent_process(job_id, proc: subprocess.Popen | None) -> None:
    """Register *or* unregister a long-running process for a job.

    Called with a Popen instance to register, and with None to unregister
    (after the process has finished).  Used internally by vertical.py which
    drives the ffmpeg subprocess directly.
    """
    tag = f"job:{job_id}" if job_id is not None else "__untagged__"
    if proc is None:
        # Unregister all processes for this tag
        with _process_lock:
            _active.pop(tag, None)
    else:
        _register(proc, {tag})


def cancel_processes(tags: set[str]) -> int:
    """Terminate all processes matching any of the given tags.

    Returns the count of processes killed.
    """
    procs_to_kill: set[subprocess.Popen] = set()
    with _process_lock:
        for tag in tags:
            bucket = _active.get(tag)
            if bucket:
                procs_to_kill.update(bucket)
    killed = 0
    for proc in procs_to_kill:
        try:
            proc.terminate()
            killed += 1
        except Exception:
            pass
    return killed


def cancel_job_processes(job_id) -> int:
    """Cancel all FFmpeg processes associated with a specific job_id."""
    return cancel_processes({f"job:{job_id}"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ffmpeg_bin() -> str:
    return getattr(settings, "FFMPEG_BIN", "ffmpeg")


def _ffprobe_bin() -> str:
    return getattr(settings, "FFPROBE_BIN", "ffprobe")


def _encoder() -> str:
    """Return the configured video encoder (defaults to libx264)."""
    enc = getattr(settings, "FFMPEG_ENCODER", "") or ""
    return enc.strip() or "libx264"


def _run(cmd: list[str], *, job_id=None, check: bool = True,
         capture_stderr: bool = True) -> subprocess.CompletedProcess:
    """Run an FFmpeg command, registering the process for cancellation.

    Raises ProcessCancelled if the process is killed via cancel_processes().
    Raises MediaEngineError on non-zero exit.
    """
    tags = set()
    if job_id is not None:
        tags.add(f"job:{job_id}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
    )
    if tags:
        _register(proc, tags)
    try:
        stdout, stderr = proc.communicate()
    finally:
        if tags:
            _unregister(proc, tags)

    if proc.returncode == -15 or proc.returncode == -9:
        raise ProcessCancelled(f"Processo FFmpeg cancelado: {cmd[0]}")
    if check and proc.returncode != 0:
        err = stderr.decode(errors="replace")[-2000:] if capture_stderr else ""
        raise MediaEngineError(
            f"FFmpeg falhou (código {proc.returncode}):\n{err}"
        )
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr if capture_stderr else b"")


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------


def probe(path: str | Path) -> dict:
    """Return a dict with video metadata: duration, width, height, fps, codec, size.

    Uses ffprobe -v quiet -print_format json -show_streams -show_format.
    Never raises on a missing field — returns 0/None for unknown values.
    """
    import json

    path = str(path)
    cmd = [
        _ffprobe_bin(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError:
        raise MediaEngineError("ffprobe não encontrado. Verifique FFPROBE_BIN.")
    except subprocess.TimeoutExpired:
        raise MediaEngineError(f"ffprobe timeout ao sondar {path}")

    if result.returncode != 0:
        err = result.stderr.decode(errors="replace")[-500:]
        raise MediaEngineError(f"ffprobe falhou para {path!r}:\n{err}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaEngineError(f"ffprobe retornou JSON inválido: {exc}") from exc

    # Extract from video stream first, then audio, then format
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), {}
    )
    fmt = data.get("format", {})

    def _fps(s: dict) -> float:
        try:
            r = s.get("r_frame_rate", "0/1")
            if "/" in r:
                n, d = r.split("/")
                return float(n) / float(d) if float(d) else 0.0
            return float(r)
        except Exception:
            return 0.0

    duration = 0.0
    try:
        duration = float(video_stream.get("duration") or fmt.get("duration") or 0)
    except (TypeError, ValueError):
        pass

    size = 0
    try:
        size = int(fmt.get("size") or os.path.getsize(path) if os.path.exists(path) else 0)
    except (TypeError, ValueError, OSError):
        pass

    return {
        "duration": duration,
        "width": int(video_stream.get("width") or 0) or None,
        "height": int(video_stream.get("height") or 0) or None,
        "fps": _fps(video_stream),
        "codec": video_stream.get("codec_name") or "",
        "size": size,
        "bit_rate": int(fmt.get("bit_rate") or 0),
    }


# ---------------------------------------------------------------------------
# cut
# ---------------------------------------------------------------------------


def cut(
    src_key: str,
    dst_key: str,
    start: float,
    duration: float,
    *,
    job_id=None,
    encoder: str = "",
    crf: str = "20",
    preset: str = "veryfast",
) -> Path:
    """Cut a segment from src_key [start, start+duration] into dst_key.

    Produces a clean re-encode at the requested quality.  The output file
    is validated via ffprobe before returning.

    Returns the absolute Path to the output file.
    """
    src_path = abs_path(src_key)
    dst_path = abs_path(dst_key)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    enc = (encoder.strip() or _encoder())
    if "nvenc" in enc.lower():
        video_codec_args = ["-c:v", enc, "-preset", "p4", "-b:v", "5M", "-pix_fmt", "yuv420p"]
    else:
        video_codec_args = [
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
        ]

    cmd = [
        _ffmpeg_bin(), "-y",
        "-ss", f"{start:.3f}",
        "-i", str(src_path),
        "-t", f"{duration:.3f}",
        *video_codec_args,
        "-c:a", "aac",
        "-movflags", "+faststart",
        str(dst_path),
    ]
    logger.debug("cut: %s", " ".join(cmd))
    _run(cmd, job_id=job_id)

    # Validate output
    info = probe(str(dst_path))
    if info["duration"] == 0:
        raise MediaEngineError(f"Corte produzido sem duração detectável: {dst_key}")

    return dst_path


# ---------------------------------------------------------------------------
# extract_audio
# ---------------------------------------------------------------------------


def extract_audio(
    src_key: str,
    dst_key: str,
    *,
    job_id=None,
    log_sink: Callable[[str], None] | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Extract audio track from src_key to dst_key as WAV (16kHz, mono).

    Suitable as input for Whisper.
    """
    src_path = abs_path(src_key)
    dst_path = abs_path(dst_key)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _ffmpeg_bin(), "-y",
        "-i", str(src_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        str(dst_path),
    ]
    logger.debug("extract_audio: %s", " ".join(cmd))
    _run(cmd, job_id=job_id)

    if not dst_path.exists():
        raise MediaEngineError(f"Extração de áudio falhou: {dst_key} não criado")
    return dst_path


# ---------------------------------------------------------------------------
# burn_subtitles
# ---------------------------------------------------------------------------


def burn_subtitles(
    src_key: str,
    ass_key: str,
    dst_key: str,
    *,
    job_id=None,
    total_duration: float = 0.0,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Burn an ASS subtitle file into the source video (libass burn-in).

    ``src_key`` — storage key of the edited 9:16 video.
    ``ass_key`` — storage key of the .ass file (relative path OK).
    ``dst_key`` — output storage key for the final rendered video.

    Progress is reported via ``on_progress(0.0–1.0)`` if provided.
    """
    src_path = abs_path(src_key)
    ass_path = abs_path(ass_key)
    dst_path = abs_path(dst_key)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if not src_path.exists():
        raise MediaEngineError(f"Arquivo de vídeo não encontrado: {src_key}")
    if not ass_path.exists():
        raise MediaEngineError(f"Arquivo ASS não encontrado: {ass_key}")

    enc = _encoder()
    if "nvenc" in enc.lower():
        video_codec_args = ["-c:v", enc, "-preset", "p4", "-b:v", "5M", "-pix_fmt", "yuv420p"]
    else:
        video_codec_args = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
        ]

    # Escape colons and backslashes in the ASS path for the vf filter
    ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")

    cmd = [
        _ffmpeg_bin(), "-y",
        "-i", str(src_path),
        "-vf", f"ass={ass_escaped}",
        *video_codec_args,
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(dst_path),
    ]
    logger.debug("burn_subtitles: %s", " ".join(cmd))

    if on_progress is None or total_duration == 0.0:
        # Simple synchronous run without progress reporting
        _run(cmd, job_id=job_id)
    else:
        # Streaming progress via ffmpeg stderr "-progress pipe:2"
        progress_cmd = [
            _ffmpeg_bin(), "-y",
            "-i", str(src_path),
            "-vf", f"ass={ass_escaped}",
            *video_codec_args,
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-progress", "pipe:2",
            str(dst_path),
        ]
        proc = subprocess.Popen(
            progress_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        tags = {f"job:{job_id}"} if job_id else set()
        if tags:
            _register(proc, tags)
        try:
            for raw_line in proc.stderr:
                line = raw_line.decode(errors="replace").strip()
                if line.startswith("out_time_ms="):
                    try:
                        ms = int(line.split("=", 1)[1])
                        pct = min(ms / (total_duration * 1_000_000), 1.0)
                        on_progress(pct)
                    except ValueError:
                        pass
        finally:
            if tags:
                _unregister(proc, tags)

        proc.wait()
        if proc.returncode not in (0, None):
            raise MediaEngineError(f"burn_subtitles falhou (código {proc.returncode})")

    # Validate output
    info = probe(str(dst_path))
    if info["duration"] == 0:
        raise MediaEngineError(f"burn_subtitles produziu arquivo sem duração: {dst_key}")

    return dst_path


# ---------------------------------------------------------------------------
# thumbnail
# ---------------------------------------------------------------------------


def thumbnail(
    src_key: str,
    dst_key: str,
    *,
    time_s: float = 0.0,
) -> Path:
    """Extract a single JPEG frame from src_key at time_s seconds."""
    src_path = abs_path(src_key)
    dst_path = abs_path(dst_key)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        _ffmpeg_bin(), "-y",
        "-ss", f"{time_s:.3f}",
        "-i", str(src_path),
        "-vframes", "1",
        "-q:v", "2",
        str(dst_path),
    ]
    _run(cmd)
    return dst_path
