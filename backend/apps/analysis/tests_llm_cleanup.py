"""Unit tests: LLM output cleanup/parsing (AGENTS.md §14.2)."""

from django.test import SimpleTestCase

from apps.analysis.llm_cleanup import clean_json_response, clean_pasted_json


class CleanJsonResponseTest(SimpleTestCase):
    def test_clean_json(self):
        raw = '{"segments": [{"title": "A", "score": 80}]}'
        out = clean_json_response(raw)
        self.assertEqual(out["segments"][0]["title"], "A")

    def test_markdown_fence(self):
        raw = '```json\n{"segments": [{"title": "B"}]}\n```'
        out = clean_json_response(raw)
        self.assertEqual(out["segments"][0]["title"], "B")

    def test_thinking_tags_stripped(self):
        raw = "<thinking>reflexão</thinking>RACIOCÍNIO:\n\n" '{"segments": [{"title": "A"}]}'
        out = clean_json_response(raw)
        self.assertEqual(out["segments"][0]["title"], "A")

    def test_escaped_garbage(self):
        raw = '{"segments": [{"title": "a\\nb", "scores": {"hook": 1}}]}'
        out = clean_json_response(raw)
        self.assertIn("a", out["segments"][0]["title"])

    def test_truncated_json_fragments(self):
        raw = '"segments": [{"title": "X", "score": 90}, {"title": "Y", "score": 70}]'
        out = clean_json_response(raw)
        self.assertGreaterEqual(len(out["segments"]), 2)

    def test_empty_returns_empty_list(self):
        out = clean_json_response("")
        self.assertEqual(out, {"segments": []})

    def test_clean_pasted_json(self):
        segs = clean_pasted_json('{"segments": [{"title": "Z"}]}')
        self.assertEqual(segs[0]["title"], "Z")


class CleanGarbageTest(SimpleTestCase):
    def test_prose_around_json(self):
        raw = 'Aqui estão os cortes:\n\n```json\n{"segments": [{"title": "Hook", "score": 85}]}\n```\nfim'
        out = clean_json_response(raw)
        self.assertEqual(out["segments"][0]["title"], "Hook")

    def test_never_returns_non_list_segments(self):
        out = clean_json_response("nada útil aqui")
        self.assertIsInstance(out.get("segments"), list)
