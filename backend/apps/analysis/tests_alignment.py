"""Unit tests: timestamp alignment (AGENTS.md §7.4)."""

from django.test import SimpleTestCase

from apps.analysis.alignment import align_segment


TRANSCRIPT = {
    "segments": [
        {"start": 0.0, "end": 2.0, "words": [
            {"word": "Olá", "start": 0.0, "end": 0.4},
            {"word": "mundo", "start": 0.5, "end": 0.9},
        ]},
        {"start": 5.0, "end": 8.0, "words": [
            {"word": "Segunda", "start": 5.0, "end": 5.5},
            {"word": "frase", "start": 5.6, "end": 6.0},
        ]},
        {"start": 10.0, "end": 12.0, "words": [
            {"word": "Vamos", "start": 10.0, "end": 10.4},
            {"word": "fechar", "start": 10.5, "end": 10.8},
        ]},
    ]
}


class AlignSegmentTest(SimpleTestCase):
    def test_align_by_boundary_text(self):
        seg = {"title": "A", "start_text": "Olá mundo", "end_text": "Segunda frase",
               "score": 80, "scores": {}}
        result = align_segment(seg, TRANSCRIPT, min_duration=1.0, max_duration=60.0)
        self.assertIsNotNone(result)
        # start at word "Olá" (0.0) ... first word is "Olá"
        self.assertIn("start_time", result)
        self.assertTrue(result["start_time"] < result["end_time"])
        self.assertFalse(result["rejected"])

    def test_returns_none_when_not_found_and_no_ref(self):
        seg = {"title": "X", "start_text": "inexistente", "end_text": "também",
               "score": 80, "scores": {}}
        result = align_segment(seg, TRANSCRIPT, min_duration=1.0, max_duration=60.0)
        self.assertIsNone(result)

    def test_respects_min_duration(self):
        seg = {"title": "A", "start_text": "Olá mundo", "end_text": "Olá mundo",
               "score": 80, "scores": {}}
        result = align_segment(seg, TRANSCRIPT, min_duration=5.0, max_duration=60.0)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["duration"], 4.9)

    def test_rejects_start_beyond_video(self):
        seg = {"title": "A", "start_text": "inexistente", "end_text": "inexistente",
               "start_time_ref": "(999s)", "score": 80, "scores": {}}
        result = align_segment(seg, TRANSCRIPT, min_duration=1.0, max_duration=60.0,
                               video_duration=12.0)
        # start_text not found; ref (999s) falls back to nearest word but start >= video
        # should reject when start lands at/after video end
        self.assertTrue(result is None or result["start_time"] < 12.0)

    def test_uses_ref_fallback_when_text_not_found(self):
        seg = {"title": "X", "start_text": "inexistente", "end_text": "Vamos",
               "start_time_ref": "(5s)", "score": 80, "scores": {}}
        result = align_segment(seg, TRANSCRIPT, min_duration=1.0, max_duration=60.0)
        self.assertIsNotNone(result)
        self.assertLess(result["start_time"], 12.0)
