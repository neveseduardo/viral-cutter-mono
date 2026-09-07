"""Two-stage viral-segment selection (AGENTS.md §5.5, 🔒).

Stage 1 — Candidate generation  : chunk the transcript, ask a provider per chunk,
                                  tolerate per-chunk failure.
Stage 2 — Global ranking        : de-duplicate, resolve overlaps, keep the best N
                                  GLOBAL segments (the user-requested count is
                                  applied HERE, never per-chunk).
"""

import logging
import re
import time

from .llm_cleanup import clean_json_response, extract_segments_from_text
from .prompts import CANDIDATE_SYSTEM, CANDIDATE_USER, RANKING_SYSTEM, RANKING_USER, chunk_transcript, preprocess_transcript_for_ai
from .providers import ProviderError, ProviderUnavailable, iter_providers, resolve_provider_order
from .validation import normalize_segments, validate_domain, validate_full

logger = logging.getLogger(__name__)


class AnalysisFailure(Exception):
    """No provider produced usable candidates."""


def _call_with_failover(order: list[str], system: str, user: str, cfg: dict) -> tuple[str, str]:
    """Tries providers sequentially; raises on total failure."""
    last_error = None
    for name, provider in iter_providers(order, cfg):
        try:
            text = provider.complete(system, user)
            return name, text
        except ProviderUnavailable as exc:
            logger.warning("provider %s unavailable: %s", name, exc)
            last_error = exc
            continue
        except ProviderError as exc:
            logger.warning("provider %s failed: %s", name, exc)
            last_error = exc
            continue
    raise AnalysisFailure(f"Nenhum provider respondeu: {last_error}")


def candidate_generation(transcript: dict, *, amount: int, min_duration: float, max_duration: float,
                         ai_provider: str, failover: str, config: dict, progress_cb=None) -> list[dict]:
    """Stage 1: per-chunk candidate generation (tolerante a falha local)."""
    segments = transcript.get("segments", [])
    text = preprocess_transcript_for_ai(segments)
    chunk_size = int(config.get("chunk_size") or 15000)
    chunks = chunk_transcript(text, chunk_size)
    order = resolve_provider_order(ai_provider, failover, config)
    count = max(1, amount)

    all_candidates: list[dict] = []
    tried = 0
    for idx, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb(int(idx / max(len(chunks), 1) * 60), f"Analisando parte {idx + 1}/{len(chunks)}...")
        try:
            provider_name, raw = _call_with_failover(
                order,
                CANDIDATE_SYSTEM,
                CANDIDATE_USER.format(
                    part_index=idx + 1, total_parts=len(chunks),
                    chunk=chunk, amount=count,
                    extra_instructions="",
                ),
                config,
            )
            if not raw:
                continue
            parsed = clean_json_response(raw).get("segments", [])
            all_candidates.extend(parsed)
            tried += 1
        except AnalysisFailure as exc:
            logger.warning("chunk %d: %s", idx, exc)
            continue

    if not all_candidates:
        raise AnalysisFailure("Nenhum candidato gerado pelos providers.")

    normalized = normalize_segments(all_candidates)
    # Apply the *per-chunk* prompt baked min/max domain hints on the candidate pool
    problems = validate_domain(normalized, min_duration=min_duration, max_duration=max_duration)
    if problems:
        logger.debug("domain warnings on candidates: %s", problems[:5])
    logger.info("candidate_generation: %d candidatos de %d chunks", len(normalized), tried)
    return normalized


def _overlaps(a: dict, b: dict, threshold: float = 5.0) -> bool:
    s1, e1 = a.get("start_time"), a.get("end_time")
    s2, e2 = b.get("start_time"), b.get("end_time")
    if None in (s1, e1, s2, e2):
        return False
    inter = min(e1, e2) - max(s1, s2)
    return inter > threshold


def global_ranking(candidates: list[dict], *, amount: int, min_duration: float, max_duration: float,
                   ai_provider: str, failover: str, config: dict, progress_cb=None) -> list[dict]:
    """Stage 2a: pure algorithmic de-dup/overlap resolution + sort by aggregate score."""
    best = []
    seen_title_sigs = set()

    def _sig(seg):
        title = re.sub(r"[^\w]", "", str(seg.get("title", ""))).lower()
        start = seg.get("start_time") or seg.get("start_time_ref") or ""
        return f"{title}|{start}"

    for seg in sorted(candidates, key=lambda x: x.get("score") or 0, reverse=True):
        sig = _sig(seg)
        if sig in seen_title_sigs:
            continue
        seen_title_sigs.add(sig)
        if any(_overlaps(seg, other) for other in best):
            continue
        best.append(seg)
        if len(best) >= amount:
            break
    if progress_cb:
        progress_cb(85, "Rankeando globalmente...")
    return best[:amount]


def aggregate(seg: dict, weights: dict | None = None) -> float:
    """Centralized aggregation formula (§5.6) — the only place score blends today."""
    weights = weights or {"hook": 0.3, "story": 0.2, "emotion": 0.2, "standalone": 0.15, "shareability": 0.15}
    scores = seg.get("scores") or {}
    total = 0.0
    total_w = 0.0
    for key, w in weights.items():
        value = scores.get(key, 0)
        total += w * float(value)
        total_w += w
    return round(min(100.0, max(0.0, total / total_w)), 1)


def select_viral_segments(transcript: dict, *, amount: int, min_duration: float, max_duration: float,
                          ai_provider: str, failover: str, config: dict, progress_cb=None) -> dict:
    """Two-stage selection → canonical viral_segments.json (§8.2)."""
    candidates = candidate_generation(
        transcript, amount=amount, min_duration=min_duration, max_duration=max_duration,
        ai_provider=ai_provider, failover=failover, config=config, progress_cb=progress_cb,
    )

    # ALGORITHMIC global ranking first (no provider needed) — deterministic.
    ranked = global_ranking(
        candidates, amount=amount, min_duration=min_duration, max_duration=max_duration,
        ai_provider=ai_provider, failover=failover, config=config, progress_cb=progress_cb,
    )

    for seg in ranked:
        seg["score"] = aggregate(seg) or (seg.get("score") or 0)
        seg["scores"] = seg.get("scores") or {k: 0 for k in ("hook", "story", "emotion", "standalone", "shareability")}
        seg["scores"]["total"] = seg["score"]

    result = {
        "schema_version": "1.0",
        "segments": ranked,
    }
    # Final validation: schema + domain on the exact N picked (§10)
    return validate_final(result, min_duration=min_duration, max_duration=max_duration)


def validate_final(result: dict, *, min_duration: float, max_duration: float):
    """Re-normalize + schema-validate the final selection; drop invalid rows."""
    segments, problems = validate_full(
        result, min_duration=min_duration, max_duration=max_duration
    )
    if problems:
        logger.info("final validation warnings: %s", problems)
    return {"schema_version": "1.0", "segments": segments}


def manual_segments(raw_json: str) -> list[dict]:
    """Parses user-pasted JSON (manual provider) into a candidate list."""
    return extract_segments_from_text(raw_json)