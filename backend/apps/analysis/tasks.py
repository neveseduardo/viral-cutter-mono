"""Celery tasks for viral-segment analysis + alignment (AGENTS.md §7.3/§7.4).

Queue: `cpu`.
"""

import logging

from celery import shared_task
from django.conf import settings

from apps.projects.models import Job, Project, Segment, SegmentStatus, Transcription
from pipeline.messages import MESSAGES
from pipeline.progress import mark_job, report_job_progress

from .alignment import align_all
from .selection import AnalysisFailure, select_viral_segments

logger = logging.getLogger(__name__)

__all__ = ["analyze_stage", "align_stage"]


def _config(run):
    cfg = dict(run.configuration_snapshot)
    cfg.setdefault("chunk_size", 15000)
    cfg.setdefault("ai_provider", "auto")
    return cfg


def _provider_secrets(cfg: dict) -> dict:
    """Server-side provider config (never exposed to the frontend)."""
    return {
        "gemini": {"gemini_api_key": settings.GEMINI_API_KEY, "gemini_model": settings.GEMINI_MODEL},
        "openai": {
            "openai_api_key": settings.OPENAI_API_KEY,
            "openai_model": settings.OPENAI_MODEL,
            "openai_base_url": settings.OPENAI_BASE_URL,
        },
        "ollama": {"ollama_url": settings.OLLAMA_URL, "ollama_model": settings.OLLAMA_MODEL},
    }


def _transcript_for(project: Project, run) -> dict:
    if hasattr(project, "transcription"):
        tx = project.transcription
        return {
            "schema_version": "1.0",
            "language": tx.language,
            "source": tx.source,
            "model": tx.model,
            "segments": tx.segments,
        }
    # Raw from the previous stage context
    tx_id = run.jobs.filter(stage="transcribe").first()
    return {"segments": [], "language": "pt"}


@shared_task(name="apps.analysis.tasks.analyze_stage")
def analyze_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    config = _config(run)

    mark_job(job, "running", progress=1, message=MESSAGES["job.analyze.started"])

    if not hasattr(project, "transcription"):
        mark_job(job, "failed", error="Transcrição não disponível antes da análise.")
        raise ValueError("transcription missing")

    transcript = _transcript_for(project, run)
    if not transcript["segments"]:
        mark_job(job, "failed", error="Transcrição vazia — não é possível analisar.")
        raise ValueError("empty transcript")

    try:
        result = select_viral_segments(
            transcript,
            amount=int(config.get("segments", 3)),
            min_duration=float(config.get("min_duration", 20)),
            max_duration=float(config.get("max_duration", 60)),
            ai_provider=config.get("ai_provider", "auto"),
            failover=settings.AI_FAILOVER,
            config=_provider_secrets(config),
            progress_cb=lambda p, msg=None: report_job_progress(job, int(p), msg or ""),
        )
    except AnalysisFailure as exc:
        logger.warning("analyze failed: %s", exc)
        mark_job(job, "failed", error=str(exc), message=MESSAGES["job.analyze.failed"])
        raise

    # Persist candidate segments (status=queued; alignment follows)
    Segment.objects.filter(project=project).delete()
    for i, seg in enumerate(result["segments"]):
        Segment.objects.create(
            project=project,
            pipeline_run=run,
            index=i,
            title=seg.get("title", "") or "Viral Segment",
            hook=seg.get("hook", ""),
            start_text=seg.get("start_text", ""),
            end_text=seg.get("end_text", ""),
            reasoning=seg.get("reasoning", ""),
            score=seg.get("score", 0),
            scores=seg.get("scores", {}),
            start_time=seg.get("start_time", 0) or 0,
            end_time=seg.get("end_time", 0),
            status=SegmentStatus.QUEUED,
        )
    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.analyze.done"])
    return {"segment_count": len(result["segments"])}


@shared_task(name="apps.analysis.tasks.align_stage")
def align_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    config = _config(run)

    mark_job(job, "running", progress=5, message=MESSAGES["job.align.started"])

    transcript = _transcript_for(project, run)
    if not hasattr(project, "transcription") or not transcript["segments"]:
        mark_job(job, "failed", error="Transcrição indisponível para alinhamento.")
        raise ValueError("transcription missing")

    candidates = []
    for seg in project.segments.order_by("index"):
        candidates.append({
            "title": seg.title,
            "hook": seg.hook,
            "reasoning": seg.reasoning,
            "score": seg.score,
            "scores": seg.scores,
            "start_text": seg.start_text or seg.hook or seg.title,
            "end_text": seg.end_text,
            "start_time_ref": seg.start_time,
            "start_time": seg.start_time,
            "end_time": seg.end_time,
        })

    # For MVP the LLM already returned aligned refs; here we hard-align using speech.
    aligned = align_all(
        candidates, transcript,
        min_duration=float(config.get("min_duration", 20)),
        max_duration=float(config.get("max_duration", 60)),
        video_duration=None,
    )

    kept = 0
    for i, seg_data in enumerate(aligned):
        seg = project.segments.filter(index=i).first()
        if seg:
            seg.title = seg_data.get("title", seg.title)
            seg.hook = seg_data.get("hook", seg.hook)
            seg.start_time = seg_data["start_time"]
            seg.end_time = seg_data["end_time"]
            seg.score = seg_data.get("score", seg.score)
            seg.scores = seg_data.get("scores", seg.scores)
            seg.status = SegmentStatus.QUEUED
            seg.save()
            kept += 1
    report_job_progress(job, 90, "Segmentos alinhados aos tempos de fala.")

    # Drop segments that were not aligned (beyond kept count)
    for seg in project.segments.order_by("index")[kept:]:
        seg.rejected = True
        seg.rejection_reason = "Não encontrável na transcrição durante alinhamento."
        seg.save()

    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.align.done"])
    return {"aligned": kept}