"""E2E smoke test: synthetic video → ingest → fake transcribe → analyze/align
(manual provider) → cut → edit → subtitles → render. Driven with Celery eager.

Run (from backend/):
  CELERY_TASK_ALWAYS_EAGER=true DB_ENGINE=sqlite STORAGE_ROOT=/tmp/vc-e2e \
    python tests/smoke_pipeline.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("STORAGE_ROOT", "/tmp/vc-e2e-data")

import django

django.setup()

from celery import signature  # noqa: E402

from apps.analysis.selection import _call_with_failover  # noqa: E402
from apps.media.engine import probe  # noqa: E402
from apps.media.storage import abs_path  # noqa: E402
from apps.projects.models import (  # noqa: E402
    ArtifactCache,
    Job,
    PipelineRun,
    Project,
    Segment,
    SegmentStatus,
    VideoAsset,
)
from pipeline.progress import refresh_run_status  # noqa: E402


def make_video(duration: float = 6.0, fps: int = 30, size: tuple = (1920, 1080)):
    """Creates a synthetic color-bars video with a tone."""
    path = Path(tempfile.mkdtemp(prefix="vc-test-")) / "source.mov"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", str(path),
    ], check=True, capture_output=True)
    return path


CANNED_JSON = """{
  "segments": [
    {"title":"Hook A","hook":"Hello world","start_text":"Hello",
     "end_text":"world","start_time_ref":"(0s)","reasoning":"open",
     "score":80,"scores":{"hook":90,"story":80,"emotion":70,"standalone":85,"shareability":75}},
    {"title":"Hook B","hook":"Second phrase","start_text":"Second",
     "end_text":"phrase","start_time_ref":"(3s)","reasoning":"mid",
     "score":70,"scores":{"hook":70,"story":70,"emotion":60,"standalone":80,"shareability":65}}
  ]
}"""


def fake_call(order, system, user, cfg):
    return "manual", CANNED_JSON


def main():
    shutil.rmtree("/tmp/vc-e2e-data", ignore_errors=True)
    data_root = Path("/tmp/vc-e2e-data")
    data_root.mkdir(parents=True, exist_ok=True)

    video = make_video()
    info = probe(str(video))
    print("[0] vídeo sintético:", info.get("duration"), "s", info.get("width"), "x", info.get("height"))

    # Patch the provider failover to return canned output (manual path works too,
    # but we bypass provider IO entirely for a deterministic test).
    _call_with_failover.__code__  # ensure import resolved

    project = Project.objects.create(name="E2E smoke")
    print("[1] project created:", project.id)

    # register the synthetic video as the source asset (kind=source)
    src = VideoAsset.objects.create(
        project=project, kind="source", storage_key="test/source.mov",
        mime_type="video/quicktime", size=info.get("size", 0),
        duration=info.get("duration", 6), width=info.get("width"), height=info.get("height"),
        fps=info.get("fps"), codec=info.get("codec"), checksum="fake-checksum-1",
    )
    Path(abs_path("test")).mkdir(parents=True, exist_ok=True)
    shutil.copy(video, abs_path("test/source.mov"))
    # normalized asset (same file) so cut/edit/render find a source
    VideoAsset.objects.create(
        project=project, kind="normalized", parent_asset=src,
        storage_key="test/normalized.mp4", mime_type="video/mp4",
        size=info.get("size", 0), duration=info.get("duration", 6),
        width=info.get("width"), height=info.get("height"), fps=info.get("fps"),
        codec=info.get("codec"), checksum="fake-checksum-1",
    )
    Path(abs_path("test")).mkdir(parents=True, exist_ok=True)
    shutil.copy(video, abs_path("test/source.mov"))
    shutil.copy(video, abs_path("test/normalized.mp4"))

    # inject the transcription (eager tasks will skip transcribe via cache? No —
    # transcribe task still runs, so we create the Transcription object and run
    # the pipeline from the analyze stage by building jobs manually).
    from apps.projects.models import Transcription

    tx = Transcription.objects.create(
        project=project, language="en", source="whisper", model="base",
        segments=[
            {"id": 0, "start": 0.0, "end": 0.5, "text": "Hello world",
             "words": [{"word": "Hello", "start": 0.0, "end": 0.25, "score": 0.9},
                        {"word": "world", "start": 0.3, "end": 0.5, "score": 0.9}]},
            {"id": 1, "start": 0.6, "end": 0.9, "text": "Second phrase",
             "words": [{"word": "Second", "start": 0.6, "end": 0.75, "score": 0.9},
                        {"word": "phrase", "start": 0.78, "end": 0.9, "score": 0.9}]},
            {"id": 2, "start": 1.2, "end": 1.5, "text": "Wrap up",
             "words": [{"word": "Wrap", "start": 1.2, "end": 1.35, "score": 0.9},
                        {"word": "up", "start": 1.38, "end": 1.5, "score": 0.9}]},
            {"id": 3, "start": 1.8, "end": 2.1, "text": "Final line",
             "words": [{"word": "Final", "start": 1.8, "end": 1.95, "score": 0.9},
                        {"word": "line", "start": 1.98, "end": 2.1, "score": 0.9}]},
        ],
    )
    print("[2] transcription injected:", tx.id)

    # Build a run from the analyze stage (bypass ingest/transcribe tasks).
    run = PipelineRun.objects.create(
        project=project, workflow="full",
        configuration_snapshot={
            "segments": 2, "min_duration": 1, "max_duration": 3,
            "whisper_model": "base", "ai_provider": "manual",
            "face_mode": "none", "no_face_mode": "zoom",
            "subtitle_preset": "hormozi-classic",
        },
    )
    from apps.analysis.selection import manual_segments
    import apps.analysis.tasks as analysis_tasks

    orig = analysis_tasks.select_viral_segments
    import apps.analysis.selection as selection_mod

    selection_mod._call_with_failover = fake_call

    stages = ["analyze", "align", "cut", "edit", "subtitles", "render"]
    jobs = {}
    from apps.projects.models import QueueName

    for i, stage in enumerate(stages):
        jobs[stage] = Job.objects.create(
            pipeline_run=run, stage=stage, queue="cpu",
            status="pending",
        )

    from apps.analysis.tasks import analyze_stage, align_stage
    from apps.editing.tasks import cut_stage, edit_stage
    from apps.subtitles.tasks import subtitles_stage
    from apps.rendering.tasks import render_stage

    print("[3] analyze ...")
    analyze_stage(run.id, jobs["analyze"].id)
    segs = list(Segment.objects.filter(project=project).order_by("index"))
    print("    segments:", [(s.index, s.title, s.start_time, s.end_time) for s in segs])

    print("[4] align ...")
    align_stage(run.id, jobs["align"].id)

    print("[5] cut ...")
    cut_stage(run.id, jobs["cut"].id)
    cuts = VideoAsset.objects.filter(project=project, kind="cut")
    print("    cut assets:", cuts.count())
    for c in cuts:
        assert c.duration > 0, "corte sem duração"

    print("[6] edit (9:16) ...")
    edit_stage(run.id, jobs["edit"].id)
    edited = VideoAsset.objects.filter(project=project, kind="edited")
    print("    edited assets:", edited.count(), "->", (edited.first().width, edited.first().height) if edited else None)

    print("[7] subtitles ...")
    subtitles_stage(run.id, jobs["subtitles"].id)

    print("[8] render ...")
    render_stage(run.id, jobs["render"].id)
    finals = VideoAsset.objects.filter(project=project, kind="final")
    print("    final assets:", finals.count())
    for f in finals:
        assert Path(abs_path(f.storage_key)).exists()
        assert f.checksum, "checksum ausente"

    refresh_run_status(run)
    run.refresh_from_db()
    print("[9] run status:", run.status)
    for job in run.jobs.order_by("id"):
        print(f"    {job.stage:10s} -> {job.status}")

    assert run.status in ("succeeded", "partial")
    assert finals.count() >= 1
    print("OK: pipeline E2E passou")


if __name__ == "__main__":
    main()