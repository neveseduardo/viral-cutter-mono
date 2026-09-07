"""Subtitle presets (§7.8). Legacy presets adapted from `old/`:

- "Hormozi Classic": 2 words/block, highlight upper, Montserrat ExtraBold, y=200.
- "MrBeast Clean Hook": 3 words/block, gold highlight (FFD700), y=180.

Any preset is a plain JSON dict; custom presets can be persisted per project.
"""

HORMOZI_CLASSIC = {
    "name": "hormozi-classic",
    "label": "Hormozi Classic",
    "mode": "highlight",
    "words_per_block": 2,
    "gap_limit": 0.5,
    "font_name": "Montserrat-ExtraBold",
    "font_size_base": 62,
    "font_size_highlight": 74,
    "color_base": "FFFFFF",
    "color_highlight": "00FF00",
    "outline_color": "111111",
    "shadow_color": "000000",
    "outline_width": 2,
    "shadow_width": 1,
    "bold": True,
    "italic": False,
    "underline": False,
    "uppercase": True,
    "remove_punctuation": True,
    "vertical_position": 200,
    "alignment": 2,
    "border": "outline",
}

MRBEAST_CLEAN = {
    "name": "mrbeast-clean",
    "label": "MrBeast Clean Hook",
    "mode": "highlight",
    "words_per_block": 3,
    "gap_limit": 0.5,
    "font_name": "Montserrat-ExtraBold",
    "font_size_base": 62,
    "font_size_highlight": 74,
    "color_base": "FFFFFF",
    "color_highlight": "FFD700",
    "outline_color": "111111",
    "shadow_color": "000000",
    "outline_width": 2,
    "shadow_width": 1,
    "bold": True,
    "italic": False,
    "underline": False,
    "uppercase": True,
    "remove_punctuation": False,
    "vertical_position": 180,
    "alignment": 2,
    "border": "outline",
}

DEFAULT_PRESET = "hormozi-classic"
PRESETS = {p["name"]: p for p in (HORMOZI_CLASSIC, MRBEAST_CLEAN)}


def resolve_preset(value) -> dict:
    """Accepts a preset name, a full preset dict, or None → defaults."""
    if value is None:
        value = DEFAULT_PRESET
    if isinstance(value, str):
        preset = PRESETS.get(value)
        if not preset:
            raise ValueError(f"preset desconhecido: {value}")
        return dict(preset)
    if isinstance(value, dict):
        return dict(value)
    raise ValueError("subtitle preset inválido")


def list_presets() -> list[dict]:
    return list(PRESETS.values())


def clean_text(text: str, *, remove_punctuation: bool = True, uppercase: bool = False) -> str:
    """Normalizes word text per preset rules."""
    import re

    if remove_punctuation:
        text = re.sub(r"[^\w\sáéíóúâêôãõàç´`'\"-]", "", text)
    if uppercase:
        text = text.upper()
    return text.strip()