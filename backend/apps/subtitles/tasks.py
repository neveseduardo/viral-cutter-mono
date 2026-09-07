"""Subtitles stage + translation stage (AGENTS.md §7.5/§7.6/§7.8).

Queue: cpu.
"""

import json
import logging

from celery import shared_task
from django.conf import settings

from apps.editing.tasks import _segment_dirs  # reuse per-segment path helpers
from apps.projects.models import Job, Segment, SegmentStatus
from pipeline.messages import MESSAGES
from pipeline.progress import mark_job, report_job_progress

from .engine import build_canonical, reanchor, to_ass, to_srt, to_vtt
from .presets import resolve_preset
from .translation import translate_track

logger = logging.getLogger(__name__)

__all__ = ["subtitles_stage", "translate_stage"]


def _load_transcript(project) -> dict | None:
    if hasattr(project, "transcription"):
        tx = project.transcription
        return {
            "schema_version": "1.0",
            "language": tx.language,
            "source": tx.source,
            "model": tx.model,
            "segments": tx.segments,
        }
    return None


def _words_between(transcript: dict, start: float, end: float) -> list[dict]:
    words = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words") or []:
            if float(w["start"]) >= start - 0.05 and float(w["end"]) <= end + 0.2:
                if float(w["end"]) <= end:
                    words.append(w)
    return words


@shared_task(name="apps.subtitles.tasks.subtitles_stage")
def subtitles_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    snapshot = run.configuration_snapshot
    preset = resolve_preset(snapshot.get("subtitle_preset"))
    preset.update({k: v for k, v in (snapshot.get("subtitle_config") or {}).items() if not v in (None, "")})

    mark_job(job, "running", progress=1, message=MESSAGES["job.subtitles.started"])

    transcript = _load_transcript(project)
    if not transcript:
        mark_job(job, "failed", error="Transcrição indisponível para legendas.")
        raise ValueError("transcription missing")

    segments = list(Segment.objects.filter(project=project, status__in=[SegmentStatus.QUEUED, SegmentStatus.CUT, SegmentStatus.EDITED]).order_by("index"))
    if not segments:
        mark_job(job, "failed", error="Nenhum segmento validado para legendas.")
        raise ValueError("no segments")

    total = len(segments)
    canonical_paths = []
    for i, seg in enumerate(segments):
        progress = 5 + int(i / total * 80)
        report_job_progress(job, progress, f"Gerando legendas do segmento {seg.index + 1}...")
        words = _words_between(transcript, seg.start_time, seg.end_time)
        if not words:
            logger.warning("segmento %s: sem palavras na faixa; legendas vazias", seg.index)
            continue
        track = build_canonical(words, language=transcript.get("language", "pt"), preset=preset)
        track = reanchor(track, offset=-seg.start_time)
        dirs = _segment_dirs(project, seg)
        # store the canonical track
        stem = seg.subs_stem()
        canonical_path = dirs["subs"] / f"{stem}.json"
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        # derived artifacts
        derived = []
        outputs = {".ass": to_ass(track, preset), ".srt": to_srt(track), ".vtt": to_vtt(track)}
        for ext, rendered in outputs.items():
            out = dirs["subs"] / f"{stem}{ext}"
            with open(out, "w", encoding="utf-8") as f:
                f.write(rendered)
            derived.append(out.name)
        track["derived"] = derived
        with open(canonical_path, "w", encoding="utf-8") as f:
            json.dump(track, f, ensure_ascii=False)
        canonical_paths.append(str(canonical_path))

    report_job_progress(job, 95, "Legendas canônicas e formatos derivados gravados.")
    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.subtitles.done"])
    return {"segments": total}


@shared_task(name="apps.subtitles.tasks.translate_stage")
def translate_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    snapshot = run.configuration_snapshot
    target = snapshot.get("translate_to", "en")
    engine = settings.TRANSLATION_ENGINE

    mark_job(job, "running", progress=5, message=MESSAGES["job.translate.started"])

    segments = list(Segment.objects.filter(project=project, status__in=[SegmentStatus.QUEUED, SegmentStatus.CUT, SegmentStatus.EDITED]).order_by("index"))
    total = len(segments)
    done = 0
    for i, seg in enumerate(segments):
        dirs = _segment_dirs(project, seg)
        stem = seg.subs_stem()
        canonical_path = dirs["subs"] / f"{stem}.json"
        if not canonical_path.exists():
            continue
        with open(canonical_path, "r", encoding="utf-8") as f:
            track = json.load(f)
        translated = translate_track(track, target=target, engine=engine)
        trans_path = dirs["subs"] / f"{stem}.{target}.json"
        with open(trans_path, "w", encoding="utf-8") as f:
            json.dump(translated, f, ensure_ascii=False)
        done += 1
        report_job_progress(job, int((i + 1) / total * 90), f"Traduzindo segmento {seg.index + 1}...")

    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.translate.done"])
    return {"translated": done}