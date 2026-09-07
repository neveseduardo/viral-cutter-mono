"""Burn-in render tasks (§7.9) — job `render`, fila gpu/cpu.

Burns the derived .ass (or a preset-based one) into the edited 9:16 video,
writing a checksummed `final` asset per segment.
"""

import hashlib
import logging
from pathlib import Path

from celery import shared_task

from apps.media.engine import burn_subtitles as engine_burn
from apps.media.engine import probe
from apps.media.storage import abs_path
from apps.projects.models import Job, Segment, SegmentStatus, VideoAsset
from apps.subtitles.ass import build_ass
from apps.subtitles.engine import to_srt, to_vtt
from apps.subtitles.presets import resolve_preset
from pipeline.messages import MESSAGES
from pipeline.progress import mark_job, report_job_progress

logger = logging.getLogger(__name__)

__all__ = ["render_stage", "render_single_segment"]


def _render_one(project, seg, job, snapshot) -> dict:
    """Renders a single segment to `final`. Returns info dict or raises."""

    def _progress(p, msg):
        if job is not None:
            report_job_progress(job, p, msg)

    from apps.editing.tasks import _segment_dirs

    dirs = _segment_dirs(project, seg)
    stem = seg.subs_stem()

    # input = edited asset if present, else cut
    asset = (
        VideoAsset.objects.filter(project=project, kind="edited", segment_index=seg.index)
        .order_by("-created_at")
        .first()
    ) or (
        VideoAsset.objects.filter(project=project, kind="cut", segment_index=seg.index)
        .order_by("-created_at")
        .first()
    )
    if asset is None:
        raise FileNotFoundError(f"sem asset editado/cortado para o segmento {seg.index}")
    input_path = abs_path(asset.storage_key)
    if not Path(input_path).exists():
        raise FileNotFoundError(f"asset ausente no storage: {asset.storage_key}")

    # ensure .ass exists (from canonical track or recompute words)
    ass_path = dirs["subs"] / f"{stem}.ass"
    if not ass_path.exists():
        _ensure_ass(project, seg, snapshot, ass_path)

    _progress(30, f"Renderizando segmento {seg.index + 1}...")
    key = f"projects/{project.id}/final/{stem}.mp4"
    out_path = abs_path(key)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    info = probe(str(input_path))
    duration = info.get("duration") or (seg.end_time - seg.start_time)
    engine_burn(
        asset.storage_key,
        f"projects/{project.id}/subs/{stem}.ass",
        key,
        job_id=job.id if job else None,
        total_duration=duration,
        on_progress=lambda p: _progress(30 + int(p * 60), f"Queimando legendas do segmento {seg.index + 1}..."),
    )
    info = probe(str(out_path))
    checksum = _checksum(str(out_path))
    VideoAsset.objects.create(
        project=project,
        parent_asset=asset,
        kind="final",
        segment_index=seg.index,
        storage_key=key,
        mime_type="video/mp4",
        size=info.get("size", 0),
        duration=info.get("duration", duration),
        width=info.get("width"),
        height=info.get("height"),
        fps=info.get("fps"),
        codec=info.get("codec"),
        checksum=checksum,
    )
    seg.status = SegmentStatus.RENDERED
    seg.save()
    _progress(100, MESSAGES["job.render.done"])
    return {"key": key, "size": info.get("size", 0), "duration": duration, "checksum": checksum}


def _ensure_ass(project, seg, snapshot, ass_path: Path) -> None:
    import json

    dirs = _segment_dirs(project, seg)
    stem = seg.subs_stem()
    canonical = dirs["subs"] / f"{stem}.json"
    if not canonical.exists():
        # rebuild from transcript words (best effort)
        if hasattr(project, "transcription"):
            words = _words_from_transcript(project, seg)
            track = {
                "schema_version": "1.0",
                "language": project.transcription.language,
                "derived": [],
                "segments": [{"start": 0.0, "end": w[-1]["end"], "text": " ".join(x["word"] for x in words), "words": words}],
            }
        else:
            raise FileNotFoundError("sem transcrição para reconstruir legendas")
    else:
        with open(canonical, "r", encoding="utf-8") as f:
            track = json.load(f)
    preset = resolve_preset(snapshot.get("subtitle_preset"))
    preset.update(snapshot.get("subtitle_config") or {})
    w = int(snapshot.get("output_width", 1080))
    h = int(snapshot.get("output_height", 1920))
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(build_ass(track, preset=preset, width=w, height=h))
    # also derive srt/vtt for completeness
    with open(dirs["subs"] / f"{stem}.srt", "w", encoding="utf-8") as f:
        f.write(to_srt(track))
    with open(dirs["subs"] / f"{stem}.vtt", "w", encoding="utf-8") as f:
        f.write(to_vtt(track))


def _words_from_transcript(project, seg) -> list[dict]:
    words = []
    for tseg in project.transcription.segments:
        for w in tseg.get("words", []):
            if float(w["start"]) >= float(seg.start_time) - 0.05 and float(w["end"]) <= float(seg.end_time) + 0.2:
                words.append({
                    "word": w["word"],
                    "start": round(float(w["start"]) - float(seg.start_time), 3),
                    "end": round(float(w["end"]) - float(seg.start_time), 3),
                    "score": round(float(w.get("score", 0.0)), 2),
                })
    words.sort(key=lambda x: x["start"])
    return words


def _checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@shared_task(name="apps.rendering.tasks.render_stage")
def render_stage(run_id, job_id, context=None):
    context = context or {}
    job = Job.objects.get(id=job_id)
    run = job.pipeline_run
    project = run.project
    snapshot = run.configuration_snapshot

    mark_job(job, "running", progress=1, message=MESSAGES["job.render.started"])

    segments = list(
        Segment.objects.filter(project=project, status__in=[SegmentStatus.EDITED, SegmentStatus.CUT])
        .order_by("index")
    )
    if not segments:
        mark_job(job, "failed", error="Nenhum segmento com edição/corte para render.")
        raise ValueError("no segments to render")

    rendered = failed = 0
    for i, seg in enumerate(segments):
        try:
            _render_one(project, seg, job, snapshot)
            rendered += 1
        except Exception as exc:
            logger.exception("render do segmento %s falhou", seg.index)
            seg.status = SegmentStatus.FAILED
            seg.save()
            failed += 1
        report_job_progress(job, int((i + 1) / len(segments) * 100), f"{rendered}/{len(segments)} segmentos renderizados")

    if failed and not rendered:
        mark_job(job, "failed", error="Todos os renders falharam.", message=MESSAGES["job.render.failed"])
        raise RuntimeError("all renders failed")
    mark_job(job, "succeeded", progress=100, message=MESSAGES["job.render.done"])
    return {"rendered": rendered, "failed": failed}


@shared_task(name="apps.rendering.tasks.render_single_segment")
def render_single_segment(project_id: int, segment_index: int, overrides: dict | None = None):
    from apps.projects.models import Project

    overrides = overrides or {}
    project = Project.objects.get(id=project_id)
    seg = Segment.objects.get(project_id=project_id, index=segment_index)
    snapshot = {"subtitle_preset": overrides.get("subtitle_preset", "hormozi-classic"), **overrides}
    try:
        _render_one(project, seg, None, snapshot)
        seg.status = SegmentStatus.RENDERED
        seg.save()
    except Exception as exc:
        logger.exception("re-render do segmento %s falhou", segment_index)
        seg.status = SegmentStatus.FAILED
        seg.save()
        raise