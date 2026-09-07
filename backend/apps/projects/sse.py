"""Server-Sent Events progress streaming (AGENTS.md §8.6).

GET /stream/pipeline-runs/{id} — on connect we send a full `pipeline.snapshot`
(event carrying the current aggregate state) so a reconnecting client can
re-sync, then we stream live events from the Redis channel `pipeline:{id}`.
"""

import json

import redis
from django.conf import settings
from django.http import StreamingHttpResponse

from apps.projects.models import PipelineRun


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def serialize_run(run: PipelineRun) -> dict:
    jobs = []
    for job in run.jobs.all().order_by("id"):
        jobs.append({
            "id": str(job.id),
            "stage": job.stage,
            "queue": job.queue,
            "status": job.status,
            "progress": job.progress,
            "attempt": job.attempt,
            "message": job.message,
            "error": job.error or None,
            "segment_index": job.segment_index,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        })
    return {
        "schema_version": "1.0",
        "pipeline_run_id": str(run.id),
        "project_id": str(run.project_id),
        "workflow": run.workflow,
        "status": run.status,
        "progress": run.progress,
        "jobs": jobs,
    }


class SSESubscription:
    """Generator that replays the snapshot and streams live events."""

    def __init__(self, run: PipelineRun):
        self.run = run

    def __call__(self):
        yield _sse("pipeline.snapshot", serialize_run(self.run))

        client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=5)
        pubsub = client.pubsub()
        channel = f"pipeline:{self.run.id}"
        pubsub.subscribe(channel)

        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=10.0)
                if message is None:
                    # Heartbeat keeps proxies from closing the connection
                    yield ": keep-alive\n\n"
                    continue
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                except json.JSONDecodeError:
                    continue
                event = payload.pop("event", "job.progress")
                payload["pipeline_run_id"] = str(self.run.id)
                yield _sse(event, payload)
        except GeneratorExit:
            pass
        finally:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:
                pass


def stream_pipeline_run(request, pipeline_run_id):
    try:
        run = PipelineRun.objects.get(id=pipeline_run_id)
    except PipelineRun.DoesNotExist:
        return StreamingHttpResponse(
            (json.dumps({"error": True, "code": "not_found", "detail": "Pipeline run não encontrada."}) for _ in [""]),
            status=404,
            content_type="application/json",
        )

    response = StreamingHttpResponse(
        SSESubscription(run)(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response