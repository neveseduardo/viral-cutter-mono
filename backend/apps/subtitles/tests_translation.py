"""Unit tests: subtitle translation (§7.6) — offline engine, batching, structure."""

from django.test import SimpleTestCase

from apps.subtitles.engine import build_canonical
from apps.subtitles.translation import (
    TranslationError,
    translate_lines,
    translate_track,
)

WORDS = [
    {"word": "Quem", "start": 0.0, "end": 0.12, "score": 0.9},
    {"word": "não", "start": 0.14, "end": 0.26, "score": 0.6},
    {"word": "tiver", "start": 0.30, "end": 0.50, "score": 0.8},
]


class TranslateLinesTest(SimpleTestCase):
    def test_unsupported_language_raises(self):
        with self.assertRaises(TranslationError):
            translate_lines(["a"], target="xx")

    def test_offline_engine_returns_identity(self):
        out = translate_lines(["olá mundo", "tudo bem"], target="en", engine="offline")
        self.assertEqual(out, ["olá mundo", "tudo bem"])

    def test_empty_lines(self):
        self.assertEqual(translate_lines([], target="en", engine="offline"), [])


class TranslateTrackTest(SimpleTestCase):
    def setUp(self):
        self.track = build_canonical(WORDS)

    def test_preserves_structure_and_timings(self):
        out = translate_track(self.track, target="en", engine="offline")
        self.assertEqual(out["language"], "en")
        self.assertEqual(len(out["segments"]), len(self.track["segments"]))
        self.assertEqual(out["segments"][0]["start"], self.track["segments"][0]["start"])
        self.assertIs(out["translated"], True)

    def test_does_not_mutate_original(self):
        translate_track(self.track, target="en", engine="offline")
        self.assertEqual(self.track["language"], "pt")
