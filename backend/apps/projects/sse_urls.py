"""SSE routes — top-level, NO /api/v1 prefix (contrato §11: GET /stream/...)."""

from django.urls import path

from .sse import stream_pipeline_run

urlpatterns = [
    path("pipeline-runs/<int:pipeline_run_id>", stream_pipeline_run, name="pipeline-stream"),
]