"""Progress reporting + SSE event publishing (AGENTS.md §8.6).

Workers call `report_job_progress(...)` which persists progress on the Job and
publishes a JSON event to the Redis channel `pipeline:{run_id}`. The SSE view
in `apps.projects.sse` subscribes to that channel.
"""

import json
import logging

import redis
from django.conf import settings
from django.utils import timezone

from apps.projects.models import RunStatus

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


def _client():
    return redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)


def channel_for(pipeline_run_id) -> str:
    return f"pipeline:{pipeline_run_id}"


def publish_event(pipeline_run_id, event: str, payload: dict):
    """Publishes a single SSE event for a pipeline run."""
    body = {
        "schema_version": SCHEMA_VERSION,
        "pipeline_run_id": str(pipeline_run_id),
        "event": event,
        **payload,
    }
    try:
        _client().publish(channel_for(pipeline_run_id), json.dumps(body, ensure_ascii=False))
    except Exception as exc:  # pragma: no cover - redis may be down
        logger.warning("SSE publish failed (run %s): %s", pipeline_run_id, exc)


def job_event(job, event: str, extra: dict | None = None):
    payload = {
        "job_id": str(job.id),
        "stage": job.stage,
        "queue": job.queue,
        "status": job.status,
        "attempt": job.attempt,
        "progress": job.progress,
        "message": job.message,
        "segment_index": job.segment_index,
    }
    if extra:
        payload.update(extra)
    publish_event(job.pipeline_run_id, event, payload)


def report_job_progress(job, progress: int, message: str = "", *, log: str | None = None) -> None:
    """Persists progress and streams it over SSE."""
    update_fields = ["progress"]
    if message:
        job.message = message
        update_fields.append("message")
    if log:
        job.logs = (job.logs or []) + [{"t": timezone.now().isoformat(), "msg": log}]
        update_fields.append("logs")

    job.progress = max(0, min(100, int(progress)))
    Job = job.__class__
    Job.objects.filter(pk=job.pk).update(**{f: getattr(job, f) for f in update_fields})
    job.status = Job.objects.filter(pk=job.pk).values_list("status", flat=True).first() or job.status
    job_event(job, "job.progress")


def mark_job(job, status: str, *, progress: int | None = None, message: str = "", error: str = ""):
    """Idempotent status transition persisted + streamed (AGENTS.md §5.2/5.4)."""
    update_fields = ["status", "message", "error"]
    if progress is not None:
        job.progress = progress
        update_fields.append("progress")
    if message:
        job.message = message
    if error:
        job.error = error
    if status == "running":
        job.started_at = timezone.now()
        update_fields.append("started_at")
    if status in ("succeeded", "failed", "cancelled", "skipped"):
        job.finished_at = timezone.now()
        update_fields.append("finished_at")

    job.status = status
    job.save(update_fields=update_fields)

    event = {
        "succeeded": "job.finished",
        "failed": "job.finished",
        "cancelled": "job.finished",
        "running": "job.started",
        "skipped": "job.finished",
    }.get(status, "job.progress")
    job_event(job, event, extra={"error": error or None})

    refresh_run_status(job.pipeline_run)


def refresh_run_status(run):
    """Aggregates job states into run status / progress (§5.7 partial)."""
    jobs = run.jobs.all()
    if not jobs.exists():
        return

    states = set(jobs.values_list("status", flat=True))
    done = jobs.filter(status__in=["succeeded", "skipped"]).count()
    failed = jobs.filter(status="failed").count()
    total = jobs.count()

    progress = round(sum(j.progress for j in jobs) / total)
    run.progress = progress

    if run.status in (RunStatus.SUCCEEDED, RunStatus.CANCELLED):
        if run.status == RunStatus.CANCELLED:
            run.save(update_fields=["progress"])
            return
        run.save(update_fields=["progress"])
        stage_counts = dict(jobs.values_list("stage", "status"))
        publish_event(run.id, "pipeline.progress", {"status": run.status, "progress": run.progress, "stages": stage_counts})
        return

    if failed and done:
        run.status = RunStatus.PARTIAL
    elif failed:
        run.status = RunStatus.FAILED
    elif "running" in states or "pending" in states:
        run.status = RunStatus.RUNNING
    else:
        run.status = RunStatus.SUCCEEDED
        run.finished_at = timezone.now()

    run.save(update_fields=["status", "progress", "finished_at"])
    stage_counts = dict(jobs.values_list("stage", "status"))
    publish_event(run.id, "pipeline.finished" if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.PARTIAL) else "pipeline.progress", {
        "status": run.status,
        "progress": run.progress,
        "stages": stage_counts,
    })