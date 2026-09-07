"""ASS generation engine (AGENTS.md §7.8).

Produces a libass-compatible .ass with per-word highlight (Hormozi style).
Colors are stored in ASS BGR notation: &H{BGR}{alpha}.
"""

from .presets import resolve_preset


def _ass_color(hex_color: str) -> str:
    """'RRGGBB' → '&HBBGGRR&'"""
    hex_color = hex_color.lstrip("#").upper()
    if len(hex_color) != 6:
        hex_color = "FFFFFF"
    r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
    return f"&H{b}{g}{r}&"


def build_ass(track: dict, *, preset: dict | None = None, width: int = 1080, height: int = 1920) -> str:
    preset = resolve_preset(preset)
    font_name = preset.get("font_name", "Montserrat-ExtraBold")
    base_size = int(preset.get("font_size_base", 62))
    bold = 1 if preset.get("bold", True) else 0
    italic = 1 if preset.get("italic", False) else 0
    underline = 1 if preset.get("underline", False) else 0
    outline = int(preset.get("outline_width", 2))
    shadow = int(preset.get("shadow_width", 1))
    alignment = int(preset.get("alignment", 2))
    margin_v = int(preset.get("vertical_position", 200))
    color_base = _ass_color(preset.get("color_base", "FFFFFF"))
    color_hl = _ass_color(preset.get("color_highlight", "00FF00"))
    color_outline = _ass_color(preset.get("outline_color", "111111"))
    color_shadow = _ass_color(preset.get("shadow_color", "000000"))
    mode = preset.get("mode", "highlight")

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{base_size},{color_base},&H00FFFFFF&,{color_outline},&H80000000&,{bold},{italic},{underline},0,100,100,0,0,1,{outline},{shadow},{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = _events(track, preset, color_base, color_hl, mode, bold, italic, underline)
    return header + events


def _events(track, preset, color_base, color_hl, mode, bold, italic, underline):
    flags = "\\b1" if bold else ""
    lines = []
    ensure = "\\N" if preset.get("uppercase", False) else ""
    for seg in track.get("segments", []):
        words = seg.get("words", [])
        start, end = seg["start"], seg["end"]
        text = seg.get("text", "")
        if mode == "no_highlight":
            lines.append(_dialogue(start, end, f"{{\\c{color_base}}} {text}"))
            continue
        if mode == "word_by_word":
            for w in words:
                lines.append(_dialogue(w["start"], w["end"], f"{{\\c{color_base}}}{flags} {w['word']}"))
            continue
        # highlight mode: repeat the block, highlighting the current word
        for idx, w in enumerate(words):
            prior = words[:idx]
            current = w
            after = words[idx + 1:]
            prior_text = " ".join(p["word"] for p in prior)
            after_text = " ".join(p["word"] for p in after)
            highlight = f"{{\\c{color_hl}}}{flags}\\b1 {current['word']}"
            body = ""
            if prior_text:
                body += f"{{\\c{color_base}}} {prior_text}"
            body += highlight
            if after_text:
                body += f"{{\\c{color_base}}} {after_text}"
            lines.append(_dialogue(w["start"], w["end"], body))
    return "\n".join(lines) + "\n"


def _dialogue(start, end, text) -> str:
    return f"Dialogue: 0,{_t(start)},{_t(end)},Default,,0,0,0,,{text}"


def _t(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    ms = round((seconds - int(seconds)) * 100)
    total_cs = int(seconds * 100)
    h = total_cs // 360000
    m = (total_cs % 360000) // 6000
    s = (total_cs % 6000) // 100
    cs = total_cs % 100
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"