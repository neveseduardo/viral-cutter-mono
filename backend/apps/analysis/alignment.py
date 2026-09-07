"""Post-AI alignment (AGENTS.md §7.4).

Turns approximate ranges from the LLM into exact speech-aligned timestamps by
searching the boundary texts in the transcript. Invalid segments are rejected,
never silently kept.
"""

import logging
import re

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return re.sub(r"[^\w\s]", "", str(text or "")).lower()


def _word_index(transcript: dict) -> list[dict]:
    """Flattens every {word, start, end} into a single ordered list."""
    flat = []
    for seg in transcript.get("segments", []):
        for word in seg.get("words") or []:
            if word.get("word"):
                flat.append({
                    "word": _normalize(word["word"]),
                    "start": float(word.get("start", 0)),
                    "end": float(word.get("end", 0)),
                })
    return flat


def _match_phrase(words: list[dict], phrase: str, from_index: int = 0) -> int | None:
    """Returns the index of the first phrase token that matches (allow fuzz)."""
    tokens = [_normalize(t) for t in phrase.split() if t.strip()]
    if not tokens:
        return None
    for i in range(from_index, max(from_index, len(words) - len(tokens)) + 1):
        matched = True
        for j, tok in enumerate(tokens):
            if i + j >= len(words) or (tok not in words[i + j]["word"] and words[i + j]["word"] not in tok):
                matched = False
                break
        if matched:
            return i
    return None


def align_segment(segment: dict, transcript: dict, *, min_duration: float, max_duration: float,
                  video_duration: float | None = None) -> dict | None:
    """Aligns one candidate to real speech timestamps. Returns None if rejected."""
    words = _word_index(transcript)
    if not words:
        return None

    start_text = segment.get("start_text", "")
    end_text = segment.get("end_text", "")

    start_idx = _match_phrase(words, start_text)
    if start_idx is None:
        # Fallback to the reference time tag ± 20 words
        ref = segment.get("start_time_ref")
        ref_val = None
        m = re.search(r"(\d+)", str(ref or ""))
        if m:
            ref_val = float(m.group(1))
        if ref_val is not None:
            start_idx = min(range(len(words)), key=lambda i: abs(words[i]["start"] - ref_val))
    if start_idx is None:
        logger.warning("segmento '%s' descartado: start_text não encontrado", segment.get("title"))
        return None

    end_idx = _match_phrase(words, end_text, from_index=start_idx)
    if end_idx is None:
        # fallback: min_duration ahead
        target = words[start_idx]["start"] + min_duration
        end_idx = start_idx
        for i in range(start_idx, len(words)):
            if words[i]["start"] >= target:
                end_idx = i
                break
            end_idx = i

    start_time = words[start_idx]["start"]
    end_time = words[end_idx]["end"]
    if end_time <= start_time:
        end_time = start_time + min_duration

    duration = end_time - start_time
    if duration < min_duration:
        end_time = start_time + min_duration
        duration = min_duration
    if duration > max_duration:
        end_time = start_time + max_duration
        duration = max_duration

    if video_duration is not None and start_time >= video_duration:
        logger.warning("segmento '%s' descartado: começa além do vídeo", segment.get("title"))
        return None
    if video_duration is not None:
        end_time = min(end_time, video_duration)
        duration = max(0.1, end_time - start_time)

    result = dict(segment)
    result["start_time"] = round(start_time, 3)
    result["end_time"] = round(end_time, 3)
    result["duration"] = round(duration, 3)
    result["rejected"] = False
    result["rejection_reason"] = None
    return result


def align_all(segments: list[dict], transcript: dict, *, min_duration: float, max_duration: float,
              video_duration: float | None = None) -> list[dict]:
    aligned = [
        s for s in (align_segment(
            seg, transcript, min_duration=min_duration, max_duration=max_duration,
            video_duration=video_duration,
        ) for seg in segments)
        if s is not None
    ]
    aligned.sort(key=lambda s: s.get("start_time", 0))
    return aligned