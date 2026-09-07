"""Unit tests: Subtitle Layout Engine (§7.8/§8.3) and ASS derivation."""

from django.test import SimpleTestCase

from apps.subtitles.engine import (
    build_canonical,
    reanchor,
    to_ass,
    to_srt,
    to_vtt,
)

WORDS = [
    {"word": "Quem", "start": 0.0, "end": 0.12, "score": 0.9},
    {"word": "não", "start": 0.14, "end": 0.26, "score": 0.6},
    {"word": "tiver", "start": 0.30, "end": 0.50, "score": 0.8},
    {"word": "coragem,", "start": 0.60, "end": 0.90, "score": 0.7},
]


class BuildCanonicalTest(SimpleTestCase):
    def test_canonical_schema_version(self):
        track = build_canonical(WORDS, language="pt")
        self.assertEqual(track["schema_version"], "1.0")
        self.assertEqual(track["language"], "pt")
        self.assertIn("segments", track)

    def test_groups_words_respecting_words_per_block(self):
        track = build_canonical(WORDS, preset={"words_per_block": 2, "gap_limit": 0.5})
        # first block: "Quem não" (gap 0.02 <= 0.5)
        self.assertEqual(track["segments"][0]["text"], "Quem não")

    def test_negative_gap_variants(self):
        track = build_canonical(WORDS, preset={"words_per_block": 1, "gap_limit": 0.2})
        # each word becomes its own block
        self.assertEqual(len(track["segments"]), len(WORDS))


class ReanchorTest(SimpleTestCase):
    def test_shift_all_timestamps(self):
        track = build_canonical(WORDS)
        shifted = reanchor(track, offset=5.0)
        self.assertAlmostEqual(shifted["segments"][0]["start"], 5.0, places=1)
        self.assertAlmostEqual(shifted["segments"][0]["words"][0]["start"], 5.0, places=1)

    def test_does_not_mutate_input(self):
        track = build_canonical(WORDS)
        reanchor(track, offset=5.0)
        self.assertAlmostEqual(track["segments"][0]["start"], 0.0, places=1)


class DeriveFormatsTest(SimpleTestCase):
    def setUp(self):
        self.track = build_canonical(WORDS, language="pt",
                                     preset={"words_per_block": 4, "gap_limit": 99.0})

    def test_srt(self):
        srt = to_srt(self.track)
        self.assertIn("00:00:00,000 --> 00:00:00,900", srt)
        self.assertIn("Quem não tiver coragem", srt)

    def test_vtt(self):
        vtt = to_vtt(self.track)
        self.assertTrue(vtt.startswith("WEBVTT"))
        self.assertIn("00:00:00.000 --> 00:00:00.900", vtt)

    def test_ass(self):
        ass = to_ass(self.track, preset={"mode": "highlight"}, width=1080, height=1920)
        self.assertIn("[Script Info]", ass)
        self.assertIn("[Events]", ass)
        self.assertIn("Dialogue:", ass)
