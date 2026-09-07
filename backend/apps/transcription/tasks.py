"""Celery task for transcription (AGENTS.md §7.2).

Queue: `gpu` when USE_GPU, else `cpu` (degradação graciosa).
"""

import logging
import os

from celery import shared_task
from django.conf import settings

from apps.ingestion.tasks import checksum_file
from apps.media import engine
from apps.media.storage import abs_path, make_random_key
from apps.projects.models import ArtifactCache, Job, Project, Transcription, VideoAsset
from pipeline.fingerprints import asset_fingerprint
from pipeline.messages import MESSAGES
from pipeline.progress import mark_job, report_job_progress

from . import engine as tx

logger = logging.getLogger(__name__)

__all__ = ["transcribe_stage"]


def _srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int((t % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _write_srt(transcript: dict, project: Project, language: str) -> str:
    srt_key = f"projects/{project.id}/transcript/input.srt"
    path = abs_path(srt_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, seg in enumerate(transcript["segments"], start=1):
        lines.append(str(i))
        lines.append(f"{_srt_time(seg['start'])} --> {_srt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return srt_key


@shared_task(name="apps.transcription.tasks.transcribe_stage")
def transcribe_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    config = run.configuration_snapshot

    mark_job(job, "running", progress=1, message=MESSAGES["job.transcribe.started"])

    normalized = context.get("normalized_asset_id") or project.assets.filter(
        kind="normalized", segment_index__isnull=True
    ).order_by("-id").first()
    if isinstance(normalized, int) or isinstance(normalized, str):
        normalized = VideoAsset.objects.get(id=normalized)
    if normalized is None:
        normalized = project.assets.filter(kind="normalized").order_by("-id").first()
    if normalized is None:
        mark_job(job, "failed", error="Nenhum asset normalizado disponível.")
        raise ValueError("normalized asset missing")

    # Fingerprint + idempotency (§4.5): skip if a matching artifact exists
    fp = asset_fingerprint(
        normalized,
        stage="transcribe",
        model=str(config.get("whisper_model") or settings.WHISPER_MODEL),
        config={"language": config.get("language", "pt")},
    )
    cached = ArtifactCache.objects.filter(project=project, fingerprint=fp, stage="transcribe").first()
    if cached and hasattr(project, "transcription"):
        mark_job(job, "succeeded", progress=100, message="Transcrição reutilizada do cache.",
                 )
        return {"transcription_id": project.transcription.id}

    language = config.get("language") or "pt"

    try:
        # YouTube subs fast path
        if config.get("use_youtube_subs"):
            sub_candidates = list(abs_path(f"projects/{project.id}/ytsubs").rglob("*.srt"))
            sub_candidates += list(abs_path(f"projects/{project.id}/ytsubs").rglob("*.vtt"))
            if sub_candidates:
                report_job_progress(job, 40, "Usando legendas oficiais do YouTube...")
                transcript = tx.youtube_subs_to_transcript(str(sub_candidates[0]), language)
                transcript["source"] = "youtube_subs"
                transcript["model"] = "youtube_subs"
                return _save_transcript(project, transcript, fp, job)

        # Whisper / WhisperX
        audio_key = f"projects/{project.id}/transcript/audio.wav"
        report_job_progress(job, 10, "Extraindo áudio...")
        engine.extract_audio(normalized.storage_key, audio_key, job_id=job.id,
                             log_sink=job.logs,
                             on_progress=lambda p: report_job_progress(job, 10 + int(p * 0.15)))
        audio_path = abs_path(audio_key)

        device = "cuda" if settings.USE_GPU else "cpu"  # upgrade via whisperx load_model device
        model_name = config.get("whisper_model") or settings.WHISPER_MODEL

        if tx.has_whisperx():
            result = tx.transcribe_whisperx(
                str(audio_path), model_name, device,
                progress_cb=lambda p, msg=None: report_job_progress(job, int(25 + p * 0.7), msg or ""),
            )
        elif tx.has_whisper():
            result = tx.transcribe_whisper(
                str(audio_path), model_name, device,
                progress_cb=lambda p, msg=None: report_job_progress(job, int(25 + p * 0.7), msg or ""),
            )
        else:
            mark_job(job, "failed", error="Nenhum motor de transcrição instalado (whisperx ou openai-whisper).")
            raise RuntimeError("whisper engines not installed")

        report_job_progress(job, 97, "Salvando transcrição...")
        transcript = {
            "language": result["language"],
            "source": "whisper",
            "model": model_name,
            "segments": result["segments"],
        }
        return _save_transcript(project, transcript, fp, job)

    except engine.ProcessCancelled as exc:
        mark_job(job, "cancelled", error=f"Cancelled: {exc}")
        raise
    except Exception as exc:
        logger.exception("transcribe_stage failed")
        mark_job(job, "failed", error=str(exc), message=MESSAGES["job.transcribe.failed"])
        raise


def _save_transcript(project: Project, transcript: dict, fp: str, job: Job) -> dict:
    transcript.setdefault("schema_version", "1.0")
    language = transcript.get("language") or "pt"
    source = transcript.get("source", "whisper")
    model = transcript.get("model", "")

    tx_inst, created = Transcription.objects.update_or_create(
        project=project,
        defaults={
            "language": language,
            "source": source,
            "model": model,
            "segments": transcript["segments"],
            "fingerprint": fp,
        },
    )
    _write_srt(transcript, project, language)
    ArtifactCache.objects.update_or_create(
        project=project, stage="transcribe", fingerprint=fp,
        defaults={"payload": {"transcription_id": tx_inst.id}},
    )
    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.transcribe.done"])
    return {"transcription_id": tx_inst.id, "created": created}