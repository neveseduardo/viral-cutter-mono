"""Celery tasks for ingestion (AGENTS.md §7.1).

Queues: `io` (yt-dlp, file operations).
"""

import hashlib
import logging
import os

from celery import shared_task
from django.utils import timezone

from apps.media import engine
from apps.media.storage import abs_path, make_random_key
from apps.projects.models import AssetKind, Job, Project, VideoAsset
from pipeline.messages import MESSAGES
from pipeline.progress import mark_job, report_job_progress

logger = logging.getLogger(__name__)

__all__ = ["ingest_stage", "ingest_stage_direct", "process_upload"]


def checksum_file(path, block_size=1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(block_size):
            h.update(chunk)
    return h.hexdigest()


def normalize_asset(project: Project, source_asset: VideoAsset, job=None, filename: str = "input.mp4") -> VideoAsset:
    """Probes a source asset and registers a `normalized` VideoAsset."""
    src_path = abs_path(source_asset.storage_key)
    meta = engine.probe(str(src_path))

    if job:
        report_job_progress(job, 50, "Validando arquivo...")
    if meta["duration"] == 0:
        raise engine.MediaEngineError("Arquivo sem stream de vídeo válido.")

    key = make_random_key(project.id, "normalized", "mp4")
    dest = abs_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # MVP: normalization copies bytes to a stable location and recomputes metadata.
    import shutil

    shutil.copyfile(src_path, dest)
    checksum = checksum_file(str(dest))

    asset = VideoAsset.objects.create(
        project=project,
        parent_asset=source_asset,
        kind=AssetKind.NORMALIZED,
        storage_key=key,
        original_name=filename,
        mime_type="video/mp4" if filename.endswith(".mp4") else source_asset.mime_type,
        size=os.path.getsize(dest),
        duration=meta["duration"],
        width=meta["width"],
        height=meta["height"],
        fps=meta["fps"],
        codec=meta["codec"],
        checksum=checksum,
    )
    project.status = "ingested"
    project.save(update_fields=["status", "updated_at"])
    return asset


@shared_task(name="apps.ingestion.tasks.process_upload")
def process_upload(asset_id: int, project_id: int):
    """Normalizes an uploaded asset outside a pipeline run."""
    source = VideoAsset.objects.get(id=asset_id, project_id=project_id)
    project = source.project
    normalize_asset(project, source, filename=source.original_name or "input.mp4")
    return {"ok": True, "asset_id": source.id}


@shared_task(name="apps.ingestion.tasks.ingest_stage_direct")
def ingest_stage_direct(project_id: int, url: str, video_quality: str = "1080p",
                        use_youtube_subs: bool = False):
    """Downloads a YouTube video immediately (no pipeline job attached)."""
    project = Project.objects.get(id=project_id)
    download_youtube(project, url, video_quality, use_youtube_subs)
    return {"ok": True}


def download_youtube(project: Project, url: str, video_quality: str, use_youtube_subs: bool):
    import yt_dlp

    key = make_random_key(project.id, "downloaded", "mp4")
    dest = abs_path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Prefer H.264/MP4 to avoid huge VP9/AV1 streams that bloat storage and
    # slow transcription. Fallback chain: h264 mp4 → any mp4 → best available.
    format_map = {
        "best": "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio/best",
        "1080p": "bestvideo[height<=1080][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080]",
        "720p": "bestvideo[height<=720][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=720][ext=mp4]+bestaudio/best[height<=720]",
        "480p": "bestvideo[height<=480][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480]",
    }
    ydl_opts = {
        "format": format_map.get(video_quality, format_map["720p"]),
        "outtmpl": str(dest),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    subs_dir = abs_path(make_random_key(project.id, "ytsubs", ""))
    subs_dir.parent.mkdir(parents=True, exist_ok=True)
    sub_path = abs_path(f"projects/{project.id}/ytsubs/input")

    if use_youtube_subs:
        ydl_opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["pt", "en"],
            "subtitlesformat": "srt",
        })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.extract_info(url, download=True)

    # yt-dlp may output .mkv/.webm depending on the source format
    merged = next(dest.parent.glob("*.*"), None) or dest
    if merged.suffix not in (".mp4", ".mkv", ".webm"):
        merged = dest

    source = VideoAsset.objects.create(
        project=project,
        kind=AssetKind.DOWNLOADED,
        storage_key=f"projects/{project.id}/downloaded/{merged.name}",
        original_name=merged.name,
        mime_type="video/mp4",
        size=os.path.getsize(merged),
    )
    if use_youtube_subs:
        try:
            for lang_dir in subs_dir.glob("*"):
                for srt in lang_dir.glob("*.srt"):
                    sub_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(srt, sub_path)
        except FileNotFoundError:
            pass
    return normalize_asset(project, source, filename="input.mp4")


@shared_task(name="apps.ingestion.tasks.ingest_stage", queue="io")
def ingest_stage(run_id, job_id, context=None):
    """Pipeline stage: produces a `normalized` VideoAsset (AGENTS.md §7.1)."""
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project

    mark_job(job, "running", progress=1, message=MESSAGES["job.ingest.started"])

    # Reuse an existing normalized asset if present (idempotency, §4.3)
    existing = project.assets.filter(kind=AssetKind.NORMALIZED).order_by("-id").first()
    if existing:
        mark_job(job, "succeeded", progress=100, message=MESSAGES["job.ingest.done"])
        return {"asset_id": existing.id, "reused": True}

    try:
        # Case 1: a source/upload asset waiting to be normalized
        source = project.assets.filter(kind=AssetKind.SOURCE).order_by("-id").first()
        if source:
            report_job_progress(job, 30, "Normalizando upload...")
            asset = normalize_asset(project, source, job=job)
            mark_job(job, "succeeded", progress=100, message=MESSAGES["job.ingest.done"])
            return {"asset_id": asset.id, "reused": False}

        # Case 2: YouTube download
        url = project.source_url or run.configuration_snapshot.get("url", "")
        if url:
            report_job_progress(job, 5, "Baixando vídeo do YouTube...")
            asset = download_youtube(
                project,
                url,
                run.configuration_snapshot.get("video_quality", "1080p"),
                run.configuration_snapshot.get("use_youtube_subs", False),
            )
            mark_job(job, "succeeded", progress=100, message=MESSAGES["job.ingest.done"])
            return {"asset_id": asset.id, "reused": False}

        raise engine.MediaEngineError("Nenhuma fonte de vídeo disponível (upload ou URL).")
    except engine.ProcessCancelled as exc:
        mark_job(job, "cancelled", error=f"Cancelled: {exc}")
        raise
    except Exception as exc:
        logger.exception("ingest_stage failed")
        mark_job(job, "failed", error=str(exc), message=MESSAGES["job.ingest.failed"])
        raise


import shutil  # noqa: E402  (used by download_youtube)