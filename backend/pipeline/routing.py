"""Queue routing helpers (AGENTS.md §5.3).

Encoding work only goes to the GPU queue when explicitly configured; otherwise
it falls back to CPU.
"""

import os

from apps.projects.models import QueueName


def default_encoder() -> str:
    return os.environ.get("FFMPEG_ENCODER", "").strip() or "libx264"


def encode_queue(use_gpu_override: bool | None = None) -> str:
    """Queue for media encode tasks (cut/edit/render)."""
    wants_gpu = os.environ.get("USE_GPU", "false").lower() in {"1", "true", "yes", "on"}
    if use_gpu_override is not None:
        wants_gpu = use_gpu_override
    encoder = default_encoder()
    if wants_gpu and encoder in ("h264_nvenc", "hevc_nvenc"):
        return QueueName.GPU
    return QueueName.CPU


def transcription_queue() -> str:
    use_gpu = os.environ.get("USE_GPU", "false").lower() in {"1", "true", "yes", "on"}
    return QueueName.GPU if use_gpu else QueueName.CPU


def io_queue() -> str:
    return QueueName.IO


def cpu_queue() -> str:
    return QueueName.CPU