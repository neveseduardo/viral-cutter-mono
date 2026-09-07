"""Cut + vertical reframe tasks (AGENTS.md §7.5/§7.7 / Fase 4).

Queue routing:
- `cut_stage`  → `io`/`cpu`? No: re-encode heavy → `cpu`, or `gpu` when FFMPEG_ENCODER is NVENC.
- `edit_stage` → `cpu` (cv2) or `gpu` when USE_GPU (face model).
"""

import json
import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings

from apps.media.engine import cut as engine_cut
from apps.media.engine import probe
from apps.media.storage import abs_path
from apps.projects.models import Job, Segment, SegmentStatus, VideoAsset
from pipeline.messages import MESSAGES
from pipeline.progress import mark_job, report_job_progress

from .face_tracking import compute_face_timeline
from .vertical import process_vertical

logger = logging.getLogger(__name__)

__all__ = ["cut_stage", "edit_stage"]


def _segment_dirs(project, seg) -> dict:
    base = Path(abs_path("")) / "projects" / str(project.id)
    return {
        "cuts": base / "cuts",
        "subs": base / "subs",
        "editions": base / "editions",
        "final": base / "final",
    }


def _source_asset(project) -> VideoAsset | None:
    return (
        VideoAsset.objects
        .filter(project=project, kind__in=("normalized", "source", "downloaded"))
        .order_by("-created_at")
        .first()
    )


def _re_anchor_words(transcript, start: float, end: float) -> list[dict]:
    words = []
    segs = transcript.get("segments", []) if hasattr(transcript, "get") else transcript
    for seg in segs:
        for w in seg.get("words") or []:
            if float(w["start"]) >= start - 0.05 and float(w["end"]) <= end + 0.2:
                words.append({
                    "word": w.get("word", ""),
                    "start": round(float(w["start"]) - start, 3),
                    "end": round(float(w["end"]) - start, 3),
                    "score": round(float(w.get("score", 0.0)), 2),
                })
    words.sort(key=lambda x: x["start"])
    return words


@shared_task(name="apps.editing.tasks.cut_stage")
def cut_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project

    mark_job(job, "running", progress=1, message=MESSAGES["job.cut.started"])

    source = _source_asset(project)
    if not source:
        mark_job(job, "failed", error="Sem asset de origem para cortar.")
        raise ValueError("no source asset")

    source_info = probe(abs_path(source.storage_key))

    transcript = None
    if hasattr(project, "transcription"):
        tx = project.transcription
        transcript = tx.segments

    segments = list(Segment.objects.filter(project=project, status=SegmentStatus.QUEUED).order_by("index"))
    if not segments:
        mark_job(job, "failed", error="Nenhum segmento para cortar.")
        raise ValueError("no segments")

    total = len(segments)
    cut_count = failed = 0
    for i, seg in enumerate(segments):
        try:
            report_job_progress(job, int(i / total * 90), f"Cortando segmento {seg.index + 1}...")
            key = f"projects/{project.id}/cuts/{seg.index}_cut.mp4"
            out_path = abs_path(key)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            engine_cut(
                source.storage_key,
                key,
                float(seg.start_time),
                float(seg.end_time) - float(seg.start_time),
                job_id=job.id,
            )
            info = probe(out_path.as_posix())
            checksum = _checksum(out_path.as_posix())
            VideoAsset.objects.create(
                project=project,
                parent_asset=source,
                kind="cut",
                segment_index=seg.index,
                storage_key=key,
                mime_type="video/mp4",
                size=info.get("size", 0),
                duration=info.get("duration", seg.end_time - seg.start_time),
                width=info.get("width", source_info.get("width")),
                height=info.get("height", source_info.get("height")),
                fps=info.get("fps", source_info.get("fps")),
                codec=info.get("codec"),
                checksum=checksum,
            )
            # per-cut word metadata (times relative to the cut, §7.5)
            if transcript:
                dirs = _segment_dirs(project, seg)
                dirs["subs"].mkdir(parents=True, exist_ok=True)
                words = _re_anchor_words(transcript, seg.start_time, seg.end_time)
                with open(dirs["subs"] / f"{seg.subs_stem()}_words.json", "w", encoding="utf-8") as f:
                    json.dump({"schema_version": "1.0", "words": words}, f, ensure_ascii=False)
            seg.status = SegmentStatus.CUT
            seg.save()
            cut_count += 1
        except Exception as exc:
            logger.exception("cut do segmento %s falhou", seg.index)
            seg.status = SegmentStatus.FAILED
            seg.save()
            failed += 1

    # fingerprint: subsequent runs will skip cut for these segments (idempotence)
    if cut_count:
        job.logs = job.logs if job.logs else []
        job.logs.append({"msg": f"{cut_count} cortes ok, {failed} falhas", "stage": "cut"})
        job.save(update_fields=["logs"])
    if failed and not cut_count:
        mark_job(job, "failed", error="Todos os cortes falharam.", message=MESSAGES["job.cut.failed"])
        raise RuntimeError("all cuts failed")
    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.cut.done"])
    return {"cut": cut_count, "failed": failed}


def _checksum(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@shared_task(name="apps.editing.tasks.edit_stage")
def edit_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    snapshot = run.configuration_snapshot

    mark_job(job, "running", progress=1, message=MESSAGES["job.edit.started"])

    cut_assets_map = {
        a.segment_index: a
        for a in VideoAsset.objects.filter(project=project, kind="cut", segment_index__isnull=False)
    }
    segments = list(Segment.objects.filter(project=project, status=SegmentStatus.CUT).order_by("index"))
    if not segments:
        # nothing to edit but the stage had cuts → mark skipped success
        report_job_progress(job, 100, "Nenhum segmento com corte; etapa pulada.")
        mark_job(job, "succeeded", progress=100)
        return {"edited": 0, "failed": 0}

    face_mode = snapshot.get("face_mode", "auto")
    no_face_mode = snapshot.get("no_face_mode", "zoom")
    dead_zone = float(snapshot.get("dead_zone", 0.03))

    total = len(segments)
    edited = failed = 0
    for i, seg in enumerate(segments):
        try:
            report_job_progress(job, int(i / total * 90), f"Enquadrando segmento {seg.index + 1}...")
            dirs = _segment_dirs(project, seg)
            asset = cut_assets_map.get(seg.index)
            if asset is None:
                raise FileNotFoundError(f"asset cut do segmento {seg.index} não encontrado")
            input_path = abs_path(asset.storage_key)
            if not Path(input_path).exists():
                raise FileNotFoundError(f"asset cut do segmento {seg.index} não encontrado")

            timeline_path = dirs["editions"] / f"{seg.index}_timeline.json"
            timeline_path.parent.mkdir(parents=True, exist_ok=True)
            timeline = compute_face_timeline(
                str(input_path),
                sample_period=0.5 if face_mode in ("auto", "track") else 0,
                backend="auto",
                on_progress=lambda p: report_job_progress(job, 10 + int(p * 0.3), "Detectando rostos..."),
            )
            with open(timeline_path, "w", encoding="utf-8") as f:
                json.dump(timeline, f, ensure_ascii=False)

            out_key = f"projects/{project.id}/editions/{seg.index}_edited.mp4"
            out_path = abs_path(out_key)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            process_vertical(
                str(input_path),
                str(out_path),
                timeline if face_mode in ("auto", "track") else None,
                target_w=int(snapshot.get("output_width", 1080)),
                target_h=int(snapshot.get("output_height", 1920)),
                face_mode=face_mode,
                no_face_mode=no_face_mode,
                dead_zone=dead_zone,
                job_id=job.id,
                on_progress=lambda p: report_job_progress(job, 35 + int(p * 0.6), "Renderizando enquadramento 9:16..."),
            )
            info = probe(str(out_path))
            VideoAsset.objects.create(
                project=project,
                parent_asset=asset,
                kind="edited",
                segment_index=seg.index,
                storage_key=out_key,
                mime_type="video/mp4",
                size=info.get("size", 0),
                duration=info.get("duration"),
                width=info.get("width"),
                height=info.get("height"),
                fps=info.get("fps"),
                codec=info.get("codec"),
                checksum=_checksum(str(out_path)),
            )
            seg.status = SegmentStatus.EDITED
            seg.save()
            edited += 1
        except Exception as exc:
            logger.exception("edit do segmento %s falhou", seg.index)
            seg.status = SegmentStatus.FAILED
            seg.save()
            failed += 1

    if failed and not edited:
        mark_job(job, "failed", error="Todos os enquadramentos falharam.", message=MESSAGES["job.edit.failed"])
        raise RuntimeError("all edits failed")
    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.edit.done"])
    return {"edited": edited, "failed": failed}