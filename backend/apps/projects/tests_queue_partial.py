"""Tests: queue semantics (§5.3), job plan (§4.2), and Partial Success (§5.7).

Fast and deterministic: no ffmpeg/video is required. We exercise the run/job
creation, per-stage queue assignment, fingerprint-based skipping, and the
partial-status aggregation logic.
"""

from django.test import TestCase, override_settings

from apps.projects.models import (
    ArtifactCache,
    Job,
    PipelineRun,
    Project,
    RunStatus,
    VideoAsset,
)
from apps.projects.pipeline import build_stages, resolve_config, start_pipeline
from pipeline.fingerprints import asset_fingerprint
from pipeline.progress import mark_job, refresh_run_status


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class QueuePlanTest(TestCase):
    """Stages map to queue by task nature — but the plan carries the intent.
    Queue names come from routing (io/cpu/gpu). We check plan structure & jobs."""

    def setUp(self):
        self.proj = Project.objects.create(name="qplan")

    def _run(self, workflow, overrides=None):
        run = start_pipeline(self.proj.id, workflow, overrides=overrides or {})
        return PipelineRun.objects.get(id=run.id)

    def test_full_workflow_builds_all_stages(self):
        run = self._run("full")
        stages = [j.stage for j in run.jobs.all()]
        self.assertIn("ingest", stages)
        self.assertIn("transcribe", stages)
        self.assertIn("analyze", stages)
        self.assertIn("cut", stages)
        self.assertIn("edit", stages)
        self.assertIn("subtitles", stages)

    def test_config_snapshot_persisted(self):
        run = self._run("full", {"segments": 4, "whisper_model": "base"})
        snap = run.configuration_snapshot
        self.assertEqual(snap["segments"], 4)
        self.assertEqual(snap["workflow"], "full")
        self.assertIn("min_duration", snap)
        self.assertEqual(snap["whisper_model"], "base")

    def test_jobs_have_queue_assigned(self):
        run = self._run("full")
        for job in run.jobs.all():
            self.assertIn(job.queue, ("io", "cpu", "gpu"))

    def test_translate_skipped_when_no_lang(self):
        run = self._run("full")
        self.assertTrue(run.jobs.filter(stage="translate", status="skipped").exists())

    def test_queues_are_named_by_nature(self):
        from pipeline.routing import io_queue, encode_queue

        self.assertEqual(io_queue(), "io")
        self.assertIn(encode_queue(), ("gpu", "cpu"))


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class FingerprintSkipTest(TestCase):
    def setUp(self):
        self.proj = Project.objects.create(name="fp-skip")
        self.asset = VideoAsset.objects.create(
            project=self.proj, kind="normalized", storage_key="n", checksum="c0ffee00",
        )

    def test_transcribe_skipped_when_cache_hit(self):
        fp = asset_fingerprint(self.asset, stage="transcribe", model="base", config={"language": "auto"})
        ArtifactCache.objects.create(
            project=self.proj, fingerprint=fp, stage="transcribe", payload={"ok": True}
        )
        run = start_pipeline(self.proj.id, "full", overrides={"whisper_model": "base"})
        run = PipelineRun.objects.get(id=run.id)
        tr_job = run.jobs.get(stage="transcribe")
        self.assertEqual(tr_job.status, "skipped")

    def test_transcribe_not_skipped_when_no_cache(self):
        run = start_pipeline(self.proj.id, "full", overrides={"whisper_model": "base"})
        tr_job = PipelineRun.objects.get(id=run.id).jobs.get(stage="transcribe")
        self.assertNotEqual(tr_job.status, "skipped")


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class PartialSuccessTest(TestCase):
    def setUp(self):
        self.proj = Project.objects.create(name="partial")
        self.run = PipelineRun.objects.create(
            project=self.proj, workflow="full", status=RunStatus.PENDING,
            configuration_snapshot={"workflow": "full"},
        )
        self.j1 = Job.objects.create(pipeline_run=self.run, stage="ingest", status="pending", queue="io")
        self.j2 = Job.objects.create(pipeline_run=self.run, stage="transcribe", status="pending", queue="gpu")
        self.j3 = Job.objects.create(pipeline_run=self.run, stage="render", status="pending", queue="gpu")

    def test_partial_when_some_fail_some_succeed(self):
        mark_job(self.j1, "succeeded", progress=100)
        mark_job(self.j2, "succeeded", progress=100)
        mark_job(self.j3, "failed", progress=50, error="boom")
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.PARTIAL)

    def test_failed_when_all_fail(self):
        mark_job(self.j1, "failed", error="e1")
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.FAILED)

    def test_succeeded_when_all_ok(self):
        mark_job(self.j1, "succeeded", progress=100)
        mark_job(self.j2, "succeeded", progress=100)
        mark_job(self.j3, "succeeded", progress=100)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, RunStatus.SUCCEEDED)


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class ComponentPlanTest(TestCase):
    def test_build_stages_known_stages(self):
        stages = build_stages("full")
        self.assertEqual(len(stages), 9)
        self.assertIn("render", stages)

    def test_resolve_config_applies_overrides(self):
        cfg = resolve_config("full", None, {"segments": 5})
        self.assertEqual(cfg["segments"], 5)
        self.assertIn("workflow", cfg)
