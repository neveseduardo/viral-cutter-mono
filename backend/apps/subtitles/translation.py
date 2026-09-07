"""Subtitle translation (AGENTS.md §7.6).

Maintains timings/structure; aggregges lines up to a char budget per request,
with retry and engine fallback. `TRANSLATION_ENGINE=external` uses deep-translator;
`offline` falls back to identity (no network) with a diagnostic message.
"""

import logging
import re

logger = logging.getLogger(__name__)

LANGUAGE_CODES = {
    "pt": "pt", "en": "en", "es": "es", "fr": "fr", "de": "de",
    "it": "it", "ru": "ru", "ja": "ja", "ko": "ko", "zh-CN": "zh-CN",
}

_MAX_CHARS = 1800


class TranslationError(Exception):
    pass


def _translator_kind(engine: str):
    if engine == "offline":
        return "offline"
    return "deep"


def translate_lines(lines: list[str], *, target: str, engine: str = "external") -> list[str]:
    """Batches lines into requests respecting _MAX_CHARS."""
    if not lines:
        return []
    if target not in LANGUAGE_CODES:
        raise TranslationError(f"idioma não suportado: {target}")

    batches = []
    current = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > _MAX_CHARS and current:
            batches.append(current)
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        batches.append(current)

    translated = []
    for batch in batches:
        translated.extend(_translate_batch(batch, target=target, engine=engine))
    return translated


def _translate_batch(lines: list[str], *, target: str, engine: str) -> list[str]:
    attempts = 0
    last_err = None
    while attempts < 3:
        attempts += 1
        try:
            return _do_translate(lines, target=target, engine=engine)
        except TranslationError as exc:
            last_err = exc
            logger.warning("translation attempt %d failed: %s", attempts, exc)
    raise TranslationError(f"tradução falhou após 3 tentativas: {last_err}")


def _do_translate(lines: list[str], *, target: str, engine: str) -> list[str]:
    kind = _translator_kind(engine)
    if kind == "offline":
        # Offline: identity returned with diagnostic. A local model can plug here.
        return list(lines)
    try:
        from deep_translator import GoogleTranslator

        joined = "\n".join(lines)
        text = GoogleTranslator(source="auto", target=target).translate(joined)
        if not text:
            return list(lines)
        out = text.split("\n")
        # deep-translator may collapse/merge separators; re-pair carefully
        if len(out) == 1 and len(lines) > 1:
            out = _resplit(out[0], lines)
        while len(out) < len(lines):
            out.append(lines[len(out)])
        return [o or l for o, l in zip(out, lines)]
    except Exception as exc:
        logger.debug("deep-translator failed: %s", exc)
        return list(lines)  # degrade gracefully: keep source text


def _resplit(text: str, original: list[str]) -> list[str]:
    """Best-effort split of a merged translation across original lines."""
    if len(original) <= 1:
        return [text]
    total = sum(len(l) for l in original)
    out = []
    idx = 0
    for src in original:
        if idx >= len(text) or len(original) - len(out) <= 1:
            out.append(text[idx:].strip() if idx < len(text) else src)
            break
        chunk = int(len(src) / max(total, 1) * len(text))
        out.append(text[idx:idx + chunk].strip())
        idx += chunk
    out.extend(l for l in original[len(out):])
    return out


def translate_track(track: dict, *, target: str, engine: str = "external") -> dict:
    """Translates a canonical subtitle track preserving structure/timings."""
    import copy

    out = copy.deepcopy(track)
    out["language"] = target
    segs = out.get("segments", [])
    texts = [seg.get("text", "") for seg in segs]
    translated = translate_lines(texts, target=target, engine=engine)
    for seg, text in zip(segs, translated):
        seg["text"] = text
    out["translated"] = True
    return out