"""REST views for the project domain + orchestration entrypoints (AGENTS.md §11)."""

import hashlib
import mimetypes

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.media.storage import abs_path

from .models import (
    Job,
    JobStatus,
    PipelineRun,
    ProcessingProfile,
    Project,
    ProjectStatus,
    RunStatus,
    Segment,
    Transcription,
    VideoAsset,
)
from .pipeline import ensure_builtin_profiles, start_pipeline
from .serializers import (
    JobSerializer,
    PipelineRunCreateSerializer,
    PipelineRunSerializer,
    ProfileSerializer,
    ProjectSerializer,
    SegmentSerializer,
    TranscriptionSerializer,
    VideoAssetSerializer,
)
from pipeline.progress import mark_job


class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()

    def perform_create(self, serializer):
        name = serializer.validated_data.get("name") or serializer.validated_data.get("source_url", "Projeto")[:60]
        serializer.save(name=name, status=ProjectStatus.EMPTY)


class ProjectDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = ProjectSerializer
    queryset = Project.objects.select_related("transcription").all()

    def retrieve(self, request, *args, **kwargs):
        project = self.get_object()
        data = ProjectSerializer(project).data
        data["assets"] = VideoAssetSerializer(
            project.assets.all().order_by("id"), many=True
        ).data
        data["segments"] = SegmentSerializer(
            project.segments.all().order_by("index"), many=True
        ).data
        data["pipeline_runs"] = PipelineRunSerializer(
            project.pipeline_runs.order_by("-id"), many=True
        ).data
        return Response(data)

    def perform_destroy(self, instance):
        # Clean up physical files referenced by assets
        for asset in instance.assets.all():
            try:
                path = abs_path(asset.storage_key)
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        instance.delete()


class AssetDetailView(generics.RetrieveAPIView):
    serializer_class = VideoAssetSerializer
    queryset = VideoAsset.objects.all()


class AssetListView(generics.ListAPIView):
    serializer_class = VideoAssetSerializer

    def get_queryset(self):
        return VideoAsset.objects.filter(project_id=self.kwargs["project_id"]).order_by("id")


def _serve_asset(request, asset_id, *, content_disposition: str):
    try:
        asset = VideoAsset.objects.get(id=asset_id)
    except VideoAsset.DoesNotExist:
        raise Http404
    path = abs_path(asset.storage_key)
    if not path.exists() or not path.is_file():
        raise Http404

    ctype = asset.mime_type or "application/octet-stream"
    name = asset.original_name or path.name
    import urllib.parse

    quoted = urllib.parse.quote(name)
    response = FileResponse(open(path, "rb"), content_type=ctype)
    response["Content-Disposition"] = f'{content_disposition}; filename="*; filename*=UTF-8\'\'{quoted}"'
    return response


class AssetDownloadView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, project_id, asset_id):
        return _serve_asset(request, asset_id, content_disposition="attachment")


class AssetContentView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, project_id, asset_id):
        return _serve_asset(request, asset_id, content_disposition="inline")


class IngestView(APIView):
    """POST /projects/{id}/ingest — enqueues ingestion or stores an upload.

    Body (youtube):   {source: "youtube", url, video_quality?, use_youtube_subs?}
    Body (upload):    multipart with file=…
    """

    def post(self, request, project_id):
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Projeto não encontrado."}, status=404)

        source = request.data.get("source", "upload")
        if source == "youtube":
            url = request.data.get("url", "")
            if not url:
                return Response({"error": True, "code": "validation_error", "detail": "url é obrigatória."}, status=400)
            from apps.ingestion.tasks import ingest_stage_direct

            ingest_stage_direct.delay(
                project_id=project.id,
                url=url,
                video_quality=request.data.get("video_quality", "1080p"),
                use_youtube_subs=bool(request.data.get("use_youtube_subs", False)),
            )
            return Response({
                "ok": True, "detail": "Ingestão do YouTube enfileirada.",
                "project": ProjectSerializer(project).data,
            }, status=202)

        # file upload
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": True, "code": "validation_error", "detail": "Envie um arquivo (form-data 'file')."}, status=400)
        if upload.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            return Response({"error": True, "code": "quota", "detail": f"Arquivo excede {settings.MAX_UPLOAD_MB} MB."}, status=413)

        from apps.ingestion.tasks import process_upload

        # MVP flow: save the upload to a source asset, then let the worker
        # normalize it (probe → recompute metadata → register normalized asset).
        upload_key = f"projects/{project.id}/uploads/{upload.name}"
        path = abs_path(upload_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb+") as dest:
            for chunk in upload.chunks():
                dest.write(chunk)

        asset = VideoAsset.objects.create(
            project=project, kind="source", storage_key=upload_key,
            original_name=upload.name,
            mime_type=upload.content_type or "video/mp4", size=upload.size,
        )
        process_upload.delay(asset_id=asset.id, project_id=project.id)
        return Response({
            "ok": True, "detail": "Upload recebido, enfileirando normalização.",
            "asset": VideoAssetSerializer(asset).data,
        }, status=202)


class PipelineRunCreateView(APIView):
    """POST /projects/{id}/pipeline-runs."""

    def post(self, request, project_id):
        if not Project.objects.filter(id=project_id).exists():
            return Response({"error": True, "code": "not_found", "detail": "Projeto não encontrado."}, status=404)
        ser = PipelineRunCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            run = start_pipeline(
                project_id=project_id,
                workflow=ser.validated_data["workflow"],
                profile_id=ser.validated_data.get("profile_id"),
                overrides=ser.validated_data.get("overrides") or {},
            )
        except ValueError as exc:
            return Response({"error": True, "code": "validation_error", "detail": str(exc)}, status=422)
        return Response(PipelineRunSerializer(run).data, status=201)


class PipelineRunDetailView(generics.RetrieveAPIView):
    serializer_class = PipelineRunSerializer
    queryset = PipelineRun.objects.prefetch_related("jobs").all()


class PipelineRunHistoryView(generics.ListAPIView):
    serializer_class = PipelineRunSerializer

    def get_queryset(self):
        return PipelineRun.objects.filter(project_id=self.kwargs["project_id"]).prefetch_related("jobs")


class PipelineRunJobListView(generics.ListAPIView):
    serializer_class = JobSerializer

    def get_queryset(self):
        return Job.objects.filter(pipeline_run_id=self.kwargs["id"]).order_by("id")


class PipelineRunCancelView(APIView):
    def post(self, request, id):
        try:
            run = PipelineRun.objects.get(id=id)
        except PipelineRun.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Run não encontrada."}, status=404)
        if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
            return Response({"error": True, "code": "conflict", "detail": "Run já encerrada."}, status=409)

        jobs = run.jobs.filter(status__in=["pending", "running"])
        for job in jobs:
            mark_job(job, JobStatus.CANCELLED, message="Cancelado pelo usuário.")
        from apps.media.engine import cancel_processes

        cancel_processes({f"run:{run.id}", f"job_any:{run.id}"})
        return Response({"ok": True, "detail": "Run cancelada.", "status": "cancelled"})


class JobCancelView(APIView):
    def post(self, request, id):
        try:
            job = Job.objects.get(id=id)
        except Job.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Job não encontrado."}, status=404)
        if job.status not in ["pending", "running"]:
            return Response({"error": True, "code": "conflict", "detail": "Job já encerrado."}, status=409)

        from apps.media.engine import cancel_job_processes

        cancel_job_processes(job.id)
        mark_job(job, JobStatus.CANCELLED, message="Cancelado pelo usuário.")
        return Response({"ok": True, "status": "cancelled"})


class JobRetryView(APIView):
    def post(self, request, id):
        try:
            job = Job.objects.get(id=id)
        except Job.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Job não encontrado."}, status=404)
        if job.status != "failed":
            return Response({"error": True, "code": "conflict", "detail": "Apenas jobs com falha podem ser reexecutados."}, status=409)

        from .pipeline import TASK_BY_STAGE

        job.status = "pending"
        job.error = ""
        job.attempt += 1
        job.progress = 0
        job.save(update_fields=["status", "error", "attempt", "progress"])

        from config.celery import app as celery_app

        task_name = TASK_BY_STAGE.get(job.stage)
        if not task_name:
            return Response({"error": True, "code": "conflict", "detail": "Job sem task associada."}, status=409)
        celery_app.send_task(task_name, args=[job.pipeline_run_id, job.id, {}])
        return Response({"ok": True, "detail": "Job reenfileirado."})


class TranscriptView(APIView):
    def get(self, request, project_id):
        try:
            transcription = Transcription.objects.get(project_id=project_id)
        except Transcription.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Transcrição não disponível."}, status=404)
        return Response(TranscriptionSerializer(transcription).data)


class SegmentsView(APIView):
    def get(self, request, project_id):
        segments = Segment.objects.filter(project_id=project_id).order_by("index")
        return Response(SegmentSerializer(segments, many=True).data)


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ProfileSerializer
    queryset = ProcessingProfile.objects.all()

    def get_queryset(self):
        ensure_builtin_profiles()
        return super().get_queryset()


class SegmentSubtitlesView(APIView):
    """GET/PUT /projects/{id}/segments/{idx}/subtitles — canonical §8.3."""

    def _segment(self, project_id, idx):
        try:
            return Segment.objects.get(project_id=project_id, index=idx)
        except Segment.DoesNotExist:
            return None

    def get(self, request, project_id, idx):
        segment = self._segment(project_id, idx)
        if segment is None:
            return Response({"error": True, "code": "not_found", "detail": "Segmento não encontrado."}, status=404)
        key = f"projects/{project_id}/subs/{segment.subs_stem()}.json"
        path = abs_path(key)
        if not path.exists():
            return Response({"error": True, "code": "not_found", "detail": "Legendas ainda não geradas para este segmento."}, status=404)
        import json

        with open(path, "r", encoding="utf-8") as f:
            return Response(json.load(f))

    def put(self, request, project_id, idx):
        segment = self._segment(project_id, idx)
        if segment is None:
            return Response({"error": True, "code": "not_found", "detail": "Segmento não encontrado."}, status=404)
        key = f"projects/{project_id}/subs/{segment.subs_stem()}.json"
        path = abs_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        with open(path, "w", encoding="utf-8") as f:
            json.dump(request.data, f, ensure_ascii=False, indent=2)
        return Response({"ok": True})


class SegmentRenderView(APIView):
    """POST /projects/{id}/segments/{idx}/render — re-render of a single segment."""

    def post(self, request, project_id, idx):
        from apps.rendering.tasks import render_single_segment

        try:
            segment = Segment.objects.get(project_id=project_id, index=idx)
        except Segment.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Segmento não encontrado."}, status=404)
        overrides = request.data or {}
        render_single_segment.delay(project_id=project_id, segment_index=idx, overrides=overrides)
        return Response({"ok": True, "detail": "Render enfileirado."}, status=202)


class SegmentExportView(APIView):
    """POST /projects/{id}/segments/{idx}/export  {format: premiere}."""

    def post(self, request, project_id, idx):
        fmt = request.data.get("format", "premiere")
        if fmt != "premiere":
            return Response({"error": True, "code": "validation_error", "detail": "Formato não suportado."}, status=400)
        from apps.export.tasks import export_premiere

        try:
            segment = Segment.objects.get(project_id=project_id, index=idx)
        except Segment.DoesNotExist:
            return Response({"error": True, "code": "not_found", "detail": "Segmento não encontrado."}, status=404)
        export_premiere.delay(project_id=project_id, segment_index=idx)
        return Response({"ok": True, "detail": "Exportação enfileirada."}, status=202)


class ExportAssetView(APIView):
    """Serves an exported premiere XML by asset id."""

    def get(self, request, asset_id):
        return _serve_asset(request, asset_id, content_disposition="attachment")


class FrontendConfigView(APIView):
    """GET /api/config/frontend — public configuration (models, profiles, limits)."""

    def get(self, request):
        ensure_builtin_profiles()
        profiles = ProfileSerializer(ProcessingProfile.objects.all(), many=True).data
        from apps.subtitles.presets import PRESETS as SUBTITLE_PRESETS

        fallback_order = [p for p in settings.AI_FAILOVER.split(",") if p]
        return Response({
            "auth_disabled": settings.AUTH_DISABLED,
            "limits": {
                "max_upload_mb": settings.MAX_UPLOAD_MB,
                "max_video_duration_s": settings.MAX_VIDEO_DURATION_S,
                "max_segments": settings.MAX_SEGMENTS,
                "storage_quota_mb": settings.STORAGE_QUOTA_MB,
            },
            "whisper_models": ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"],
            "providers": ["auto", "gemini", "openai", "ollama", "manual"],
            "ai_failover": fallback_order,
            "profiles": profiles,
            "subtitle_presets": list(SUBTITLE_PRESETS.keys()),
            "workflows": ["full", "cut_only", "subtitles_only"],
            "face_modes": ["auto", "one", "none"],
            "no_face_modes": ["padding", "zoom"],
            "languages": ["pt", "en", "es", "fr", "de", "it", "ru", "ja", "ko", "zh-CN"],
        })


def slugify(text: str) -> str:
    import re

    slug = re.sub(r"[^\w\s-]", "", text or "").lower().strip()
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug[:60] or "segment"