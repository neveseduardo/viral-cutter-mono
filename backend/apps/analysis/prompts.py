"""Editorial prompts for viral-segment selection (AGENTS.md §7.3)."""

CANDIDATE_SYSTEM = """You are a World-Class Viral Video Editor.
You analyze a video transcript and identify segments that work standalone as viral Shorts/Reels/TikToks.

Rules:
- Each segment must have a COMPLETE narrative arc: hook → development → payoff/conclusion.
- Do NOT start segments on weak words like "um", "então", "oi pessoal", "é".
- Never cut in the middle of a sentence.
- Duration must respect the min/max provided (in seconds).
- Only send the transcript TEXT to the model — never the video.
- The "start_text" must be the exact first 5-10 words of the segment (verbatim from the transcript).
- The "end_text" must be the exact last 5-10 words of the segment (verbatim).
- "start_time_ref" must be the closest (NNs) time tag appearing just before the segment.
- Output "title", "hook" and "reasoning" in the SAME LANGUAGE as the transcript.
- Output JSON ONLY, nothing else.

JSON template:
{{
  "segments": [
    {{
      "start_text": "Exact first 5-10 words",
      "end_text": "Exact last 5-10 words",
      "start_time_ref": "closest (NNs) tag",
      "title": "Viral hook title",
      "reasoning": "Why it works (hook/value/arc)",
      "score": 0-100,
      "scores": {{"hook": 0, "story": 0, "emotion": 0, "standalone": 0, "shareability": 0}}
    }}
  ]
}}
"""

CANDIDATE_USER = """
This is part {part_index} of {total_parts}. Transcript with time tags:

{chunk}

Find up to {amount} viral segments in this part.
{extra_instructions}
"""

RANKING_SYSTEM = """You are a World-Class Viral Video Editor performing GLOBAL ranking.
You receive a list of candidate viral segments extracted from chunks of a single video.
Your job:
- Remove duplicates (repeated or nearly identical segments).
- Resolve overlaps: keep only the strongest candidate where ranges intersect.
- Verify each segment can work highlighted on its own (context-compete).
- Score hook quality, narrative arc and clarity.
- Pick the best segments overall.

Output JSON ONLY:
{{
  "segments": [
    {{
      "title": "...",
      "reasoning": "...",
      "score": 0-100,
      "scores": {{"hook": 0, "story": 0, "emotion": 0, "standalone": 0, "shareability": 0}},
      "start_text": "first 5-10 words verbatim",
      "end_text": "last 5-10 words verbatim",
      "start_time_ref": "closest (NNs) tag or interpolated time"
    }}
  ]
}}
"""

RANKING_USER = """
Transcript length: about {duration_seconds}s. Min segment duration: {min_duration}s. Max: {max_duration}s.
Candidates (JSON):
{candidates}

Pick the {amount} best, de-duplicated, non-overlapping segments. Return JSON ONLY.
"""


def preprocess_transcript_for_ai(segments: list[dict]) -> str:
    """Concatenates transcript segments with embedded (NNs) time tags."""
    if not segments:
        return ""
    parts = []
    last_tag = -100
    first_start = segments[0].get("start", 0)
    parts.append(f"({int(first_start)}s)")
    last_tag = first_start
    for seg in segments:
        text = seg.get("text", "").strip()
        end = seg.get("end", 0)
        if text:
            parts.append(text)
        if end - last_tag >= 4:
            parts.append(f"({int(end)}s)")
            last_tag = end
    return " ".join(parts)


def chunk_transcript(text: str, chunk_size: int, overlap: float = 0.1) -> list[str]:
    """Splits transcript text into chunks with overlap, breaking on spaces."""
    size = max(500, int(chunk_size or 15000))
    overlap = max(200, int(size * overlap))
    chunks: list[str] = []
    pos = 0
    length = len(text)
    while pos < length:
        end = min(pos + size, length)
        if end < length:
            last_space = text.rfind(" ", pos, end)
            if last_space > pos:
                end = last_space
        chunk = text[pos:end]
        if chunk.strip():
            chunks.append(chunk)
        if end >= length:
            break
        next_start = max(pos + 1, end - overlap)
        space = text.rfind(" ", pos, next_start)
        pos = space + 1 if space > pos else next_start
    return chunks or [text]