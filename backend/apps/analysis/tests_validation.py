"""Unit tests: JSON Schema validation + domain validation + aggregate score."""

from django.test import SimpleTestCase

from apps.analysis.selection import aggregate
from apps.analysis.validation import (
    normalize_segments,
    validate_domain,
    validate_full,
    validate_schema,
)


class NormalizeTest(SimpleTestCase):
    def test_normalize_basic(self):
        raw = '{"segments": [{"title": " A ", "score": "87", "scores": {"hook": 92, "emotion": 90}}]}'
        segs = normalize_segments(raw)
        self.assertEqual(segs[0]["title"], "A")
        self.assertEqual(segs[0]["score"], 87.0)
        self.assertEqual(segs[0]["scores"]["hook"], 92.0)
        self.assertAlmostEqual(segs[0]["scores"]["story"], 0.0)

    def test_normalize_ignores_non_dict_items(self):
        segs = normalize_segments([{"title": "B"}, "lixo", 42])
        self.assertEqual(len(segs), 1)


class SchemaValidationTest(SimpleTestCase):
    def test_valid_segments_pass_schema(self):
        segs = normalize_segments('{"segments": [{"title": "Hook A", "score": 80, '
                                  '"scores": {"hook": 80, "story": 70, "emotion": 60, '
                                  '"standalone": 80, "shareability": 70}}]}')
        problems = validate_schema(segs)
        self.assertEqual(problems, [])


class DomainValidationTest(SimpleTestCase):
    def test_missing_start_text_is_problem(self):
        seg = {"title": "A", "start_text": "", "end_text": "fim",
               "score": 80, "scores": {}}
        problems = validate_domain([seg], min_duration=10, max_duration=60)
        self.assertTrue(any("start_text" in p for p in problems))

    def test_score_out_of_range_is_problem(self):
        seg = {"title": "A", "start_text": "x", "end_text": "y",
               "score": 150, "scores": {}}
        problems = validate_domain([seg], min_duration=10, max_duration=60)
        self.assertTrue(any("score" in p for p in problems))

    def test_ref_time_beyond_video_is_problem(self):
        seg = {"title": "A", "start_text": "x", "end_text": "y",
               "start_time_ref": "(999s)", "score": 80, "scores": {}}
        problems = validate_domain([seg], min_duration=10, max_duration=60, video_duration=100)
        self.assertTrue(any("além do vídeo" in p for p in problems))


class AggregateTest(SimpleTestCase):
    def test_aggregate_weights(self):
        seg = {"scores": {"hook": 100, "story": 0, "emotion": 0,
                          "standalone": 0, "shareability": 0}}
        # hook weight = 0.3 / total 1.0 => 30
        self.assertEqual(aggregate(seg), 30.0)

    def test_aggregate_clamped(self):
        seg = {"scores": {"hook": 200, "story": 100, "emotion": 100,
                          "standalone": 100, "shareability": 100}}
        self.assertLessEqual(aggregate(seg), 100.0)

    def test_validate_full_returns_segments_and_problems(self):
        raw = '{"segments": [{"title": "Hook A", "start_text": "x", "end_text": "y", "score": 80}]}'
        segs, problems = validate_full(raw, min_duration=10, max_duration=60)
        self.assertEqual(len(segs), 1)
        self.assertEqual(problems, [])
