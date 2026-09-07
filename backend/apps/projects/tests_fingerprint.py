"""Unit tests: fingerprint/idempotency (AGENTS.md §4.5)."""

from django.test import TestCase

from pipeline.fingerprints import asset_fingerprint, compute_fingerprint

from apps.projects.models import Project, VideoAsset


class FingerprintTest(TestCase):
    def test_same_input_same_fingerprint(self):
        a = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3", config={"language": "pt"})
        b = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3", config={"language": "pt"})
        self.assertEqual(a, b)

    def test_different_model_different_fingerprint(self):
        a = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3", config={"language": "pt"})
        b = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3-turbo", config={"language": "pt"})
        self.assertNotEqual(a, b)

    def test_different_input_different_fingerprint(self):
        a = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3", config={"language": "pt"})
        b = compute_fingerprint(input_checksum="abd", stage="transcribe", model="large-v3", config={"language": "pt"})
        self.assertNotEqual(a, b)

    def test_different_config_different_fingerprint(self):
        a = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3", config={"language": "pt"})
        b = compute_fingerprint(input_checksum="abc", stage="transcribe", model="large-v3", config={"language": "en"})
        self.assertNotEqual(a, b)


class AssetFingerprintTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="fp")
        self.asset = VideoAsset.objects.create(
            project=self.project, kind="source", storage_key="k", checksum="deadbeef",
        )

    def test_uses_checksum(self):
        fp1 = asset_fingerprint(self.asset, stage="transcribe", model="m", config={"language": "pt"})
        fp2 = compute_fingerprint(input_checksum="deadbeef", stage="transcribe", model="m", config={"language": "pt"})
        self.assertEqual(fp1, fp2)

    def test_falls_back_to_storage_key_when_no_checksum(self):
        other = VideoAsset.objects.create(project=self.project, kind="source", storage_key="other/k")
        fp = asset_fingerprint(other, stage="transcribe", model="m", config={})
        self.assertEqual(fp, compute_fingerprint(input_checksum="other/k", stage="transcribe", model="m", config={}))
