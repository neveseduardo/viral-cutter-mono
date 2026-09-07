"""API tests (DRF): contract §11 — health, projects, ingest, pipeline-runs, segments.

Runs with Celery in eager mode so `.delay()`/`apply_async()` execute synchronously,
and with storage pointing at a temp dir.
"""

import io
import tempfile

from django.test import override_settings
from rest_framework.test import APITestCase

from apps.projects.models import PipelineRun, Project, VideoAsset

MODELS_TO_OVERRIDE = {
    "CELERY_TASK_ALWAYS_EAGER": False,
    "AUTH_DISABLED": True,
}


@override_settings(**MODELS_TO_OVERRIDE)
class HealthApiTest(APITestCase):
    def test_health(self):
        resp = self.client.get("/api/v1/health")
        # status may be 200 or 503 depending on redis reachability in CI; schema must hold
        self.assertIn(resp.status_code, (200, 503))
        self.assertIn("status", resp.json())


@override_settings(**MODELS_TO_OVERRIDE)
class ProjectApiTest(APITestCase):
    def test_create_and_list_project(self):
        resp = self.client.post("/api/v1/projects", {"name": "Meu projeto"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "Meu projeto")

        resp = self.client.get("/api/v1/projects")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 1)

    def test_project_detail_contains_aggregate(self):
        proj = Project.objects.create(name="agg")
        resp = self.client.get(f"/api/v1/projects/{proj.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("assets", data)
        self.assertIn("segments", data)
        self.assertIn("pipeline_runs", data)

    def test_get_404_for_missing_project(self):
        resp = self.client.get("/api/v1/projects/99999")
        self.assertEqual(resp.status_code, 404)


@override_settings(**MODELS_TO_OVERRIDE, STORAGE_ROOT=tempfile.mkdtemp())
class IngestApiTest(APITestCase):
    def test_upload_requires_file(self):
        proj = Project.objects.create(name="up")
        resp = self.client.post(f"/api/v1/projects/{proj.id}/ingest", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_upload_creates_source_asset(self):
        proj = Project.objects.create(name="up2")
        fake = io.BytesIO(b"fake-video-bytes")
        resp = self.client.post(
            f"/api/v1/projects/{proj.id}/ingest",
            {"file": fake},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 202)
        self.assertTrue(VideoAsset.objects.filter(project=proj, kind="source").exists())

    def test_youtube_requires_url(self):
        proj = Project.objects.create(name="yt")
        resp = self.client.post(
            f"/api/v1/projects/{proj.id}/ingest",
            {"source": "youtube"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


@override_settings(**MODELS_TO_OVERRIDE)
class PipelineRunApiTest(APITestCase):
    def setUp(self):
        self.proj = Project.objects.create(name="pipe")

    def test_create_pipeline_run(self):
        resp = self.client.post(
            f"/api/v1/projects/{self.proj.id}/pipeline-runs",
            {"workflow": "full", "overrides": {"translation_language": None}},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(PipelineRun.objects.filter(project=self.proj).exists())

    def test_create_pipeline_run_respects_max_segments(self):
        resp = self.client.post(
            f"/api/v1/projects/{self.proj.id}/pipeline-runs",
            {"workflow": "full", "overrides": {"segments": 9999}},
            format="json",
        )
        self.assertEqual(resp.status_code, 422)

    def test_run_job_list_and_detail(self):
        resp = self.client.post(
            f"/api/v1/projects/{self.proj.id}/pipeline-runs",
            {"workflow": "subtitles_only"},
            format="json",
        )
        run = PipelineRun.objects.get(project=self.proj)
        resp = self.client.get(f"/api/v1/pipeline-runs/{run.id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("jobs", resp.json())

    def test_jobs_endpoint_returns_flat_job_list(self):
        """§11: GET /pipeline-runs/{id}/jobs → lista de jobs (não runs), paginada."""
        resp = self.client.post(
            f"/api/v1/projects/{self.proj.id}/pipeline-runs",
            {"workflow": "full"},
            format="json",
        )
        run = PipelineRun.objects.get(project=self.proj)
        resp = self.client.get(f"/api/v1/pipeline-runs/{run.id}/jobs")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        results = data["results"]
        self.assertEqual(len(results), run.jobs.count())
        self.assertIn("stage", results[0])
        self.assertIn("status", results[0])
        self.assertNotIn("workflow", results[0])

    def test_cancel_run(self):
        resp = self.client.post(
            f"/api/v1/projects/{self.proj.id}/pipeline-runs",
            {"workflow": "subtitles_only"},
            format="json",
        )
        run = PipelineRun.objects.get(project=self.proj)
        resp = self.client.post(f"/api/v1/pipeline-runs/{run.id}/cancel")
        self.assertEqual(resp.status_code, 200)


@override_settings(**MODELS_TO_OVERRIDE)
class FrontendConfigApiTest(APITestCase):
    def test_public_config(self):
        resp = self.client.get("/api/v1/config/frontend")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("limits", data)
        self.assertIn("workflows", data)
        self.assertIn("profiles", data)
