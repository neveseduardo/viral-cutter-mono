"""Unit tests: ASS generation (highlight mode, colors, structure)."""

from django.test import SimpleTestCase

from apps.subtitles.ass import build_ass
from apps.subtitles.engine import build_canonical

WORDS = [
    {"word": "Quem", "start": 0.0, "end": 0.12, "score": 0.9},
    {"word": "não", "start": 0.14, "end": 0.26, "score": 0.6},
    {"word": "tiver", "start": 0.30, "end": 0.50, "score": 0.8},
]


class AssStructureTest(SimpleTestCase):
    def setUp(self):
        track = build_canonical(WORDS, preset={"words_per_block": 3, "gap_limit": 99.0})
        self.ass = build_ass(track, preset={
            "mode": "highlight",
            "color_highlight": "00FF00",
            "color_base": "FFFFFF",
        })

    def test_sections_present(self):
        self.assertIn("[Script Info]", self.ass)
        self.assertIn("[V4+ Styles]", self.ass)
        self.assertIn("[Events]", self.ass)

    def test_highlighted_word_present(self):
        self.assertIn("\\c&H00FF00&", self.ass)

    def test_has_dialogue_events(self):
        self.assertIn("Dialogue:", self.ass)

    def test_no_highlight_mode(self):
        track = build_canonical(WORDS, preset={"words_per_block": 3, "gap_limit": 99.0})
        ass = build_ass(track, preset={"mode": "no_highlight"})
        self.assertIn("Dialogue:", ass)
