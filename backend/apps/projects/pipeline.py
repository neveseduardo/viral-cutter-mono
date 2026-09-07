"""Pipeline orchestration (AGENTS.md §5, §7.13).

Creates a PipelineRun + its Jobs, resolves the effective configuration snapshot
from a ProcessingProfile + overrides, applies fingerprints (reuses past
artifacts → skips stages), and dispatches the Celery chain.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from apps.projects.models import (
    ArtifactCache,
    Job,
    JobStage,
    PipelineRun,
    ProcessingProfile,
    Project,
    QueueName,
    RunStatus,
)
from pipeline.progress import publish_event
from pipeline.routing import encode_queue, io_queue, transcription_queue

logger = logging.getLogger(__name__)

BUILTIN_PROFILES: list[dict] = [
    {
        "name": "Shorts padrão",
        "is_builtin": True,
        "config": {
            "segments": 3,
            "min_duration": 20,
            "max_duration": 60,
            "whisper_model": "large-v3-turbo",
            "face_mode": "auto",
            "no_face_mode": "padding",
            "subtitle_preset": "Hormozi (Classic)",
            "translation_language": None,
            "video_quality": "1080p",
            "use_youtube_subs": False,
            "chunk_size": 15000,
            "ai_provider": "auto",
            "min_score": 50,
        },
    },
    {
        "name": "Hormozi Fast (CPU)",
        "is_builtin": True,
        "config": {
            "segments": 3,
            "min_duration": 20,
            "max_duration": 60,
            "whisper_model": "base",
            "face_mode": "auto",
            "no_face_mode": "padding",
            "subtitle_preset": "Hormozi (Classic)",
            "translation_language": None,
            "video_quality": "720p",
            "use_youtube_subs": False,
            "chunk_size": 15000,
            "ai_provider": "auto",
            "min_score": 50,
        },
    },
    {
        "name": "Vertical Center Crop",
        "is_builtin": True,
        "config": {
            "segments": 3,
            "min_duration": 20,
            "max_duration": 60,
            "whisper_model": "base",
            "face_mode": "none",
            "no_face_mode": "zoom",
            "subtitle_preset": "Hormozi (Classic)",
            "translation_language": None,
            "video_quality": "1080p",
            "use_youtube_subs": False,
            "chunk_size": 15000,
            "ai_provider": "auto",
            "min_score": 50,
        },
    },
]

# workflow → ordered stages with their default queues
STAGE_PLAN: dict[str, list[tuple[JobStage, str]]] = {
    "full": [
        (JobStage.INGEST, io_queue()),
        (JobStage.TRANSCRIBE, transcription_queue()),
        (JobStage.ANALYZE, QueueName.CPU),
        (JobStage.ALIGN, QueueName.CPU),
        (JobStage.CUT, encode_queue()),
        (JobStage.EDIT, encode_queue()),
        (JobStage.SUBTITLES, QueueName.CPU),
        (JobStage.TRANSLATE, QueueName.CPU),
        (JobStage.RENDER, encode_queue()),
    ],
    "cut_only": [
        (JobStage.INGEST, io_queue()),
        (JobStage.TRANSCRIBE, transcription_queue()),
        (JobStage.ANALYZE, QueueName.CPU),
        (JobStage.ALIGN, QueueName.CPU),
        (JobStage.CUT, encode_queue()),
        (JobStage.EDIT, encode_queue()),
    ],
    "subtitles_only": [
        (JobStage.SUBTITLES, QueueName.CPU),
        (JobStage.TRANSLATE, QueueName.CPU),
        (JobStage.RENDER, encode_queue()),
    ],
}

WORKFLOW_STAGES: dict[str, list[str]] = {
    "full": ["ingest", "transcribe", "analyze", "align", "cut", "edit", "subtitles", "translate", "render"],
    "cut_only": ["ingest", "transcribe", "analyze", "align", "cut", "edit"],
    "subtitles_only": ["subtitles", "translate", "render"],
}

TASK_BY_STAGE = {
    "ingest": "apps.ingestion.tasks.ingest_stage",
    "transcribe": "apps.transcription.tasks.transcribe_stage",
    "analyze": "apps.analysis.tasks.analyze_stage",
    "align": "apps.analysis.tasks.align_stage",
    "cut": "apps.editing.tasks.cut_stage",
    "edit": "apps.editing.tasks.edit_stage",
    "subtitles": "apps.subtitles.tasks.subtitles_stage",
    "translate": "apps.subtitles.tasks.translate_stage",
    "render": "apps.rendering.tasks.render_stage",
}


def ensure_builtin_profiles() -> None:
    for data in BUILTIN_PROFILES:
        if not ProcessingProfile.objects.filter(name=data["name"], is_builtin=True).exists():
            ProcessingProfile.objects.create(
                name=data["name"], is_builtin=True, config=data["config"]
            )


def resolve_config(workflow: str, profile_id: int | None, overrides: dict | None) -> dict:
    overrides = dict(overrides or {})
    base: dict = {}
    if profile_id:
        try:
            profile = ProcessingProfile.objects.get(id=profile_id)
            base = dict(profile.config)
        except ProcessingProfile.DoesNotExist:
            raise ValueError("ProcessingProfile inválido.")
    base.update(overrides)
    base.setdefault("workflow", workflow)
    base.setdefault("segments", overrides.get("segments") or 3)
    base.setdefault("min_duration", 20)
    base.setdefault("max_duration", 60)
    base.setdefault("whisper_model", settings.WHISPER_MODEL)
    base.setdefault("video_quality", "1080p")
    base.setdefault("use_youtube_subs", False)
    base.setdefault("ai_provider", settings.AI_FAILOVER.split(",")[0])
    base.setdefault("face_mode", "auto")
    base.setdefault("no_face_mode", "padding")
    base.setdefault("subtitle_preset", "Hormozi (Classic)")
    base.setdefault("max_segments", settings.MAX_SEGMENTS)
    return base


def build_stages(workflow: str) -> list[str]:
    return list(WORKFLOW_STAGES.get(workflow, WORKFLOW_STAGES["full"]))


def _mark_skipped(run: PipelineRun, stage: str, message: str) -> Job:
    job = Job.objects.create(
        pipeline_run=run,
        stage=stage,
        queue=QueueName.CPU,
        status="skipped",
        progress=100,
        message=message,
        finished_at=timezone.now(),
    )
    publish_event(run.id, "job.finished", {
        "job_id": str(job.id), "stage": stage, "status": "skipped", "progress": 100,
        "message": message, "queue": QueueName.CPU,
    })
    return job


def start_pipeline(project_id: int, workflow: str, profile_id: int | None = None,
                   overrides: dict | None = None) -> PipelineRun:
    """Creates the run + jobs and dispatches the Celery chain."""
    project = Project.objects.get(id=project_id)
    config = resolve_config(workflow, profile_id, overrides)
    max_segments = int(config.get("max_segments") or settings.MAX_SEGMENTS)
    if int(config.get("segments") or 1) > max_segments:
        raise ValueError(f"máximo de {max_segments} segmentos por execução")

    run = PipelineRun.objects.create(
        project=project,
        workflow=workflow,
        profile_id=profile_id,
        configuration_snapshot=config,
        status=RunStatus.PENDING,
    )
    publish_event(run.id, "pipeline.started", {"workflow": workflow, "status": run.status})

    stages = build_stages(workflow)
    chain_sigs = []
    jobs_by_stage: dict[str, Job] = {}

    for stage in stages:
        if stage == "translate" and not config.get("translation_language"):
            _mark_skipped(run, stage, "Tradução não solicitada")
            continue

        if stage == "ingest":
            queue = io_queue()
        elif stage == "transcribe":
            queue = transcription_queue()
        elif stage in ("cut", "edit", "render"):
            queue = encode_queue()
        else:
            queue = QueueName.CPU
        job = Job.objects.create(
            pipeline_run=run, stage=stage, status="pending", queue=queue
        )
        jobs_by_stage[stage] = job

    # Fingerprint-based skip: reuse a previous transcription when the source
    # asset and configuration are unchanged (§4.5 idempotency).
    from pipeline.fingerprints import asset_fingerprint

    normalized = project.assets.filter(kind="normalized").order_by("-id").first()
    transcribe_job = jobs_by_stage.get("transcribe")
    if normalized and transcribe_job:
        fp = asset_fingerprint(
            normalized,
            stage="transcribe",
            model=str(config.get("whisper_model") or settings.WHISPER_MODEL),
            config={"language": config.get("language", "auto")},
        )
        config["transcribe_fingerprint"] = fp
        run.configuration_snapshot = config
        run.save(update_fields=["configuration_snapshot"])

        cached = ArtifactCache.objects.filter(
                project=project, fingerprint=fp, stage="transcribe"
            ).first()
        if cached:
            transcribe_job.status = "skipped"
            transcribe_job.progress = 100
            transcribe_job.message = "Transcrição reutilizada do cache (fingerprint idêntico)"
            transcribe_job.finished_at = timezone.now()
            transcribe_job.save(update_fields=["status", "progress", "message", "finished_at"])
            publish_event(run.id, "job.finished", {
                "job_id": str(transcribe_job.id), "stage": "transcribe",
                "status": "skipped", "progress": 100,
                "message": transcribe_job.message, "queue": transcribe_job.queue,
            })

    # Build a sequential chain of immutable signatures (one per active job).
    from celery import chain, signature

    signatures = []
    for stage in stages:
        job = jobs_by_stage.get(stage)
        if job is None or job.status == "skipped":
            continue
        signatures.append(
            signature(TASK_BY_STAGE[stage], args=[run.id, job.id, {}], immutable=True)
        )

    if signatures:
        task_chain = chain(*signatures)
        task_chain.link_error(_failure_callback.s(run.id))
        task_chain.apply_async()
    else:
        from pipeline.progress import refresh_run_status

        refresh_run_status(run)
    return run


def chain_target(task_name: str, run_id: int, job_id: int):
    """Builds an immutable Celery signature for the next stage."""
    from celery import signature

    return signature(task_name, args=[run_id, job_id, {}], immutable=True)


from celery import shared_task  # noqa: E402


@shared_task(name="viralcutter.pipeline.failure_callback")
def _failure_callback(request, exc, traceback, run_id):
    """Marks a failed run when a link_error fires (errback signature: request, exc, traceback, *args)."""
    try:
        run = PipelineRun.objects.get(id=run_id)
        run.status = RunStatus.FAILED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
        publish_event(run.id, "pipeline.finished", {"status": "failed", "progress": run.progress})
    except PipelineRun.DoesNotExist:
        pass