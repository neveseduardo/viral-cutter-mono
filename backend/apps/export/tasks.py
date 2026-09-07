"""Export task (🎁 §7.12) — job fila `cpu`."""

import json
import logging

from celery import shared_task
from django.conf import settings

from apps.media.storage import abs_path
from apps.projects.models import Job, Segment, VideoAsset

from .premiere import build_premiere_xml, export_zip

logger = logging.getLogger(__name__)

__all__ = ["export_premiere"]


@shared_task(name="apps.export.tasks.export_premiere")
def export_premiere(project_id: int, segment_index: int):
    from apps.editing.tasks import _segment_dirs

    seg = Segment.objects.get(project_id=project_id, index=segment_index)
    project = seg.project
    dirs = _segment_dirs(project, seg)
    stem = seg.subs_stem()

    asset = (
        VideoAsset.objects.filter(project=project, kind="final", segment_index=seg.index)
        .order_by("-created_at")
        .first()
    )
    if asset is None:
        asset = (
            VideoAsset.objects.filter(project=project, kind="edited", segment_index=seg.index)
            .order_by("-created_at")
            .first()
        )
    if asset is None:
        raise ValueError("sem asset final/edited para exportar")

    timeline = None
    timeline_path = dirs["editions"] / f"{seg.index}_timeline.json"
    if timeline_path.exists():
        with open(timeline_path, "r", encoding="utf-8") as f:
            timeline = json.load(f)

    xml = build_premiere_xml(
        video_path=str(abs_path(asset.storage_key)),
        duration=float(seg.end_time - seg.start_time),
        start_offset=float(seg.start_time),
        source_width=(timeline or {}).get("width") or asset.width or 1920,
        source_height=(timeline or {}).get("height") or asset.height or 1080,
        timeline=timeline,
        vertical_width=1080,
        vertical_height=1920,
    )

    out_key = f"projects/{project_id}/exports/{stem}.zip"
    out_path = abs_path(out_key)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = export_zip(project_id, segment_index, items=[
        (f"{stem}.xml", xml),
        (f"{stem}.json", json.dumps(timeline or {}, ensure_ascii=False).encode("utf-8")),
    ])
    with open(out_path, "wb") as f:
        f.write(data)
    return {"key": out_key, "size": len(data)}