"""Robust LLM output parsing (AGENTS.md §7.3 robustness).

Adapted from the legacy `clean_json_response`: strips thinking tags, handles
markdown fences, truncated JSON and escaped garbage, then recovers as many
segment objects as possible.
"""

import ast
import json
import re


def clean_json_response(response_text: str) -> dict:
    """Returns a dict that is guaranteed to have a `segments` list."""
    if not isinstance(response_text, str):
        response_text = str(response_text)
    if not response_text:
        return {"segments": []}

    # 1. Strip thinking tags (DeepSeek R1 style)
    response_text = re.sub(r'', '', response_text, flags=re.DOTALL)
    response_text = re.sub(r'^.*? response', '', response_text, flags=re.DOTALL)

    # 2. Locate the object containing "segments" and try strict decodes FIRST,
    #    so valid JSON with proper escapes (\n, \") survives. Escape
    #    normalization below is only a fallback for corrupted/mangled output.
    recovered = _locate_and_decode(response_text)
    if recovered is not None:
        return recovered

    # 3. Normalize doubled escapes then retry (handles LLMs that double-escape)
    response_text = response_text.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'")
    recovered = _locate_and_decode(response_text)
    if recovered is not None:
        return recovered

    # 4. Markdown code fence
    fence = re.search(r"```(?:json)?\s*(.*?)```", response_text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict) and isinstance(obj.get("segments"), list):
                return obj
        except json.JSONDecodeError:
            pass

    # 5. LAST RESORT: fragment parser for truncated JSON
    recovered = _parse_fragment_list(response_text)
    if recovered:
        return {"segments": recovered}

    return {"segments": []}


def _locate_and_decode(text: str) -> dict | None:
    """Finds the {…} object containing `segments` and decodes it (strict or balanced)."""
    matches = [m.start() for m in re.finditer(r"segments", text)]
    for match_idx in matches:
        start_search = max(0, match_idx - 5000)
        snippet_before = text[start_search:match_idx]
        last_open = snippet_before.rfind("{")
        if last_open == -1:
            continue
        candidate = text[start_search + last_open:]

        try:
            obj, _ = json.JSONDecoder().raw_decode(candidate)
            if isinstance(obj, dict) and isinstance(obj.get("segments"), list):
                return obj
        except json.JSONDecodeError:
            pass

        try:
            end = _find_balanced(candidate)
            if end != -1:
                obj = ast.literal_eval(candidate[: end + 1])
                if isinstance(obj, dict) and isinstance(obj.get("segments"), list):
                    return obj
        except (ValueError, SyntaxError):
            pass
    return None


def _find_balanced(text: str) -> int:
    balance = 0
    in_string = False
    escape = False
    for i, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue
        if char in "'\"":
            in_string = not in_string
            continue
        if not in_string:
            if char == "{":
                balance += 1
            elif char == "}":
                balance -= 1
                if balance == 0:
                    return i
    return -1


def _parse_fragment_list(text: str) -> list[dict]:
    match_list = re.search(r'"segments"\s*:\s*\[', text)
    if not match_list:
        return []
    pos = match_list.end()
    decoder = json.JSONDecoder()
    items = []
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\n\r,":
            pos += 1
        if pos >= len(text) or text[pos] == "]":
            break
        try:
            obj, consumed = decoder.raw_decode(text[pos:])
            if isinstance(obj, dict):
                items.append(obj)
            pos += consumed
        except json.JSONDecodeError:
            break
    return items


def clean_pasted_json(raw: str) -> list[dict]:
    """Cleans a manual user-provided segment list."""
    data = clean_json_response(raw)
    return data.get("segments", [])


def extract_segments_from_text(raw: str) -> list[dict]:
    return clean_json_response(raw).get("segments", [])