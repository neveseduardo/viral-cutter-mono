"""Subtitle Layout Engine (§7.8/§8.3): Timed Words → Canonical Subtitle Track.

The canonical JSON is the single source of truth; ASS/SRT/VTT are derived
artifacts. Blocks are built word-by-word with an optional gap limit and a
highlight window (the currently spoken word).
"""

import copy

from .presets import clean_text


def build_canonical(words: list[dict], *, language: str = "pt", preset: dict | None = None,
                    schema_version: str = "1.0") -> dict:
    """Builds the canonical subtitle track from a list of timed words.

    words: [{word, start, end, score}, ...] (times ABSOLUTE into the clip).
    Returns a dict conforming to schemas/subtitles.schema.json.
    """
    preset = preset or {}
    words_per_block = max(1, int(preset.get("words_per_block", 2)))
    gap_limit = float(preset.get("gap_limit", 0.5))
    remove_punctuation = bool(preset.get("remove_punctuation", True))
    uppercase = bool(preset.get("uppercase", False))

    clean_words = [
        {
            "word": clean_text(w.get("word", ""), remove_punctuation=remove_punctuation, uppercase=uppercase) or " ",
            "start": float(w.get("start", 0)),
            "end": float(w.get("end", 0)),
            "score": round(float(w.get("score", 0.0)), 2),
        }
        for w in words
        if w.get("word")
    ]
    clean_words.sort(key=lambda x: x["start"])

    blocks = _group_words(clean_words, words_per_block=words_per_block, gap_limit=gap_limit)

    return {
        "schema_version": schema_version,
        "language": language,
        "derived": [],
        "segments": [
            {
                "start": block["start"],
                "end": block["end"],
                "text": " ".join(w["word"] for w in block["words"]),
                "words": block["words"],
            }
            for block in blocks
        ],
    }


def _group_words(words: list[dict], *, words_per_block: int, gap_limit: float) -> list[dict]:
    if not words:
        return []
    blocks = []
    current = [words[0]]
    for word in words[1:]:
        last = current[-1]
        gap = word["start"] - last["end"]
        if len(current) >= words_per_block or gap > gap_limit:
            blocks.append(_block_from(current))
            current = [word]
        else:
            current.append(word)
    if current:
        blocks.append(_block_from(current))
    return blocks


def _block_from(words: list[dict]) -> dict:
    return {
        "start": round(words[0]["start"], 3),
        "end": round(words[-1]["end"], 3),
        "words": words,
    }


def reanchor(track: dict, offset: float = 0.0) -> dict:
    """Shifts every timestamp in a canonical track by offset (used per-cut→global)."""
    shifted = copy.deepcopy(track)
    for seg in shifted["segments"]:
        seg["start"] = round(seg["start"] + offset, 3)
        seg["end"] = round(seg["end"] + offset, 3)
        for w in seg["words"]:
            w["start"] = round(w["start"] + offset, 3)
            w["end"] = round(w["end"] + offset, 3)
    return shifted


def to_srt(track: dict) -> str:
    """Derives SRT from the canonical track."""
    lines = []
    for i, seg in enumerate(track["segments"], start=1):
        lines.append(str(i))
        lines.append(f"{_fmt_srt(seg['start'])} --> {_fmt_srt(seg['end'])}")
        lines.append(seg.get("text", ""))
        lines.append("")
    return "\n".join(lines)


def to_vtt(track: dict) -> str:
    lines = ["WEBVTT", ""]
    for seg in track["segments"]:
        lines.append(f"{_fmt_vtt(seg['start'])} --> {_fmt_vtt(seg['end'])}")
        lines.append(seg.get("text", ""))
        lines.append("")
    return "\n".join(lines)


def to_ass(track: dict, preset: dict | None = None, width: int = 1080, height: int = 1920) -> str:
    """Derives ASS from the canonical track + preset (see ass.py for the engine)."""
    from .ass import build_ass

    return build_ass(track, preset=preset, width=width, height=height)


def _fmt_srt(t: float) -> str:
    ms = int(round((t - int(t)) * 1000))
    s = int(t) % 60
    m = int(t // 60) % 60
    h = int(t // 3600)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _fmt_vtt(t: float) -> str:
    ms = int(round((t - int(t)) * 1000))
    s = int(t) % 60
    m = int(t // 60) % 60
    h = int(t // 3600)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"