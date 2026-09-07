"""Output validation pipeline (AGENTS.md §10, 🔒).

LLM output → Parsing → JSON normalization → JSON Schema validation →
Domain validation (timestamps, duration min/max, content).
"""

import json
import os
import re
from pathlib import Path

import jsonschema

from .llm_cleanup import clean_json_response

# In Docker, __file__ lives at /app/... so the "4 parents up" heuristic resolves
# to the filesystem root. VC_SCHEMA_DIR lets infra/ mount schemas explicitly.
def _resolve_schema_dir() -> Path:
    env = os.environ.get("VC_SCHEMA_DIR")
    if env:
        return Path(env)
    cached = Path(__file__).resolve().parent.parent.parent.parent / "schemas"
    if cached.exists():
        return cached
    # container fallbacks (image copies schemas to /app/schemas)
    for candidate in ("/app/schemas", "/schemas"):
        p = Path(candidate)
        if p.exists():
            return p
    return cached


SCHEMA_DIR = _resolve_schema_dir()

_SCHEMA_CACHE = {}


def load_schema(name: str) -> dict:
    if name not in _SCHEMA_CACHE:
        path = SCHEMA_DIR / name
        with open(path, "r", encoding="utf-8") as f:
            _SCHEMA_CACHE[name] = json.load(f)
    return _SCHEMA_CACHE[name]


class ValidationError(Exception):
    def __init__(self, message: str, reasons: list[str]):
        super().__init__(message)
        self.reasons = reasons


def normalize_segments(raw: str | dict | list) -> list[dict]:
    """Turns any LLM output into a normalized list of segment dicts."""
    if isinstance(raw, list):
        data = {"segments": raw}
    elif isinstance(raw, str):
        data = clean_json_response(raw)
    elif isinstance(raw, dict):
        data = raw
    else:
        data = {"segments": []}

    segments = data.get("segments", [])
    normalized = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        item = {
            "title": str(seg.get("title", "Viral Segment")).strip(),
            "hook": str(seg.get("hook", "")).strip(),
            "reasoning": str(seg.get("reasoning", "")).strip(),
            "score": _as_number(seg.get("score", seg.get("scores", {}).get("total", 0))),
            "start_text": str(seg.get("start_text", "")).strip(),
            "end_text": str(seg.get("end_text", "")).strip(),
            "start_time_ref": seg.get("start_time_ref", ""),
            "scores": {
                "hook": _as_number(seg.get("scores", {}).get("hook", 0)),
                "story": _as_number(seg.get("scores", {}).get("story", 0)),
                "emotion": _as_number(seg.get("scores", {}).get("emotion", 0)),
                "standalone": _as_number(seg.get("scores", {}).get("standalone", 0)),
                "shareability": _as_number(seg.get("scores", {}).get("shareability", 0)),
            },
        }
        if seg.get("start_time") is not None:
            item["start_time"] = _as_number(seg.get("start_time"))
        if seg.get("end_time") is not None:
            item["end_time"] = _as_number(seg.get("end_time"))
        if seg.get("rejected") is not None:
            item["rejected"] = bool(seg.get("rejected"))
            item["rejection_reason"] = seg.get("rejection_reason")
        normalized.append(item)
    return normalized


def _as_number(value, default=0) -> float:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return default


def validate_schema(normalized: list[dict]) -> list[str]:
    """Validates the normalized list against viral-segments.schema.json."""
    schema = load_schema("viral-segments.schema.json")
    try:
        jsonschema.validate({"schema_version": "1.0", "segments": normalized}, schema)
        return []
    except jsonschema.ValidationError as exc:
        return [f"schema: {exc.message} (caminho {list(exc.path)})"]


def _extract_ref_time(ref) -> float:
    if ref is None or ref == "":
        return None
    if isinstance(ref, (int, float)):
        return float(ref)
    match = re.search(r"(\d+)", str(ref))
    return float(match.group(1)) if match else None


def validate_domain(normalized: list[dict], *, min_duration: float, max_duration: float,
                    video_duration: float | None = None) -> list[str]:
    problems = []
    for i, seg in enumerate(normalized):
        if not seg.get("title"):
            problems.append(f"segmento {i}: título vazio")
        if not seg.get("start_text"):
            problems.append(f"segmento {i}: start_text ausente (necessário p/ alinhamento)")
        if not seg.get("end_text"):
            problems.append(f"segmento {i}: end_text ausente (necessário p/ alinhamento)")
        score = seg.get("score", 0)
        if not (0 <= score <= 100):
            problems.append(f"segmento {i}: score fora de 0-100 ({score})")
        for key, val in (seg.get("scores") or {}).items():
            if not (0 <= val <= 100):
                problems.append(f"segmento {i}: scores.{key} fora de 0-100 ({val})")
        ref = _extract_ref_time(seg.get("start_time_ref"))
        if ref is not None and video_duration and ref > video_duration:
            problems.append(f"segmento {i}: start_time_ref ({ref:.1f}s) além do vídeo ({video_duration:.1f}s)")
    return problems


def validate_full(raw, *, min_duration: float, max_duration: float,
                  video_duration: float | None = None):
    """Runs the whole pipeline; returns (segments, problems). Raises on no valid output."""
    normalized = normalize_segments(raw)
    problems = validate_schema(normalized)
    problems += validate_domain(
        normalized, min_duration=min_duration, max_duration=max_duration,
        video_duration=video_duration,
    )
    return normalized, problems