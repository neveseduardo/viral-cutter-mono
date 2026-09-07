"""Live E2E over the real REST API + Celery + Redis + SSE stack.

Assumes backend on :8010 and worker consuming io,cpu,gpu. No API keys needed:
the analyze stage is served by a tiny mock OpenAI-compatible HTTP server started
by this script; the transcribe stage is skipped by pre-seeding a Transcription
row whose fingerprint matches the one the transcribe job will compute.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, "/home/eduardo/projetos/viral-cutter/backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DB_ENGINE", "sqlite")
os.environ.setdefault("STORAGE_ROOT", "/tmp/opencode/vcdata")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import django

django.setup()

from apps.projects.models import Transcription, Project, ArtifactCache, VideoAsset  # noqa: E402
from pipeline.fingerprints import asset_fingerprint  # noqa: E402

BASE = "http://localhost:8010"


def http_json(method, path, data=None, raw=None):
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    req = urllib.request.Request(f"{BASE}{path}", data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())


def unwrap(payload):
    return payload.get("results", payload) if isinstance(payload, dict) else payload


def make_video(duration=6.0):
    path = Path(tempfile.mkdtemp(prefix="vc-live-")) / "source.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=30:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
        str(path),
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


class MockLLMOk(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        payload = {"choices": [{"message": {"content": CANNED_JSON}}]}
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def seed_transcription(project, normalized):
    fp = asset_fingerprint(normalized, stage="transcribe", model="base", config={"language": "pt"})
    tx, _ = Transcription.objects.update_or_create(
        project=project,
        defaults={
            "language": "pt", "source": "whisper", "model": "base",
            "segments": [
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
        },
    )
    ArtifactCache.objects.update_or_create(
        fingerprint=fp,
        defaults={"stage": "transcribe", "project": project, "payload": {"transcription_id": tx.id}},
    )
    return fp


def main():
    mock = HTTPServer(("127.0.0.1", 9101), MockLLMOk)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    print("[0] mock LLM ouvindo em :9101")

    video = make_video()
    checksum = subprocess.run(["sha256sum", str(video)], capture_output=True, text=True).stdout.split()[0]
    print("[1] vídeo sintético:", video.name, "size", video.stat().st_size)

    proj = http_json("POST", "/api/v1/projects", {"name": "Live E2E"})
    pid = proj["id"]
    print("[2] project:", pid)

    import requests
    with open(video, "rb") as f:
        r = requests.post(f"{BASE}/api/v1/projects/{pid}/ingest",
                          files={"file": ("source.mp4", f, "video/mp4")})
    print("[3] ingest upload:", r.status_code)
    assert r.status_code in (202, 200), r.text[:300]

    # wait for ingest worker job to finish (project becomes "ingested")
    for _ in range(120):
        j = http_json("GET", f"/api/v1/projects/{pid}")
        if j.get("status") in ("ingested", "analyzed", "ready", "error"):
            break
        time.sleep(1)
    print("[4] project status após ingest:", j["status"])

    assets = unwrap(http_json("GET", f"/api/v1/projects/{pid}/assets"))
    norm = next((a for a in assets if a["kind"] == "normalized"), None)
    assert norm, "sem asset normalized"
    dba = VideoAsset.objects.get(id=norm["id"])
    fp = seed_transcription(Project.objects.get(id=pid), dba)
    print("[5] transcrição pré-seedada (fingerprint)", fp[:12])

    run = http_json("POST", f"/api/v1/projects/{pid}/pipeline-runs", {
        "workflow": "full",
        "overrides": {
            "segments": 2, "min_duration": 1, "max_duration": 3,
            "whisper_model": "base", "ai_provider": "openai",
            "face_mode": "none", "no_face_mode": "zoom",
            "subtitle_preset": "hormozi-classic",
        },
    })
    run_id = run["id"]
    print("[6] pipeline-run", run_id, "-> status", run.get("status"))

    sse_events = []
    keep = True

    def sse_thread():
        req = urllib.request.Request(f"http://localhost:8010/stream/pipeline-runs/{run_id}",
                                     method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                for raw in r:
                    line = raw.decode().strip()
                    if line.startswith("event:"):
                        sse_events.append(line[6:].strip())
                    elif line.startswith("data:"):
                        try:
                            sse_events.append(json.dumps(json.loads(line[5:].strip())))
                        except Exception:
                            sse_events.append(line[5:].strip())
        except Exception as exc:
            sse_events.append(f"__sse_close__ {type(exc).__name__}")

    threading.Thread(target=sse_thread, daemon=True).start()

    status = ""
    for i in range(240):
        time.sleep(1)
        detail = http_json("GET", f"/api/v1/pipeline-runs/{run_id}")
        status = detail.get("status", "")
        if status in ("succeeded", "failed", "cancelled", "partial"):
            break

    print("[7] run final:", status)
    jobs = unwrap(http_json("GET", f"/api/v1/pipeline-runs/{run_id}/jobs"))
    for jb in jobs:
        print("   job:", jb["stage"], jb["status"], f'progress={jb.get("progress")}', jb.get("message") or "")
    assert status == "succeeded", f"expected succeeded, got {status}"
    assert any(jb["stage"] == "analyze" and jb["status"] == "succeeded" for jb in jobs)

    fins = unwrap(http_json("GET", f"/api/v1/projects/{pid}/assets"))
    finals = [a for a in fins if a["kind"] == "final"]
    print("[8] finais:", [(a["name"], a.get("duration")) for a in finals])
    assert len(finals) >= 2, "esperávamos >=2 assets finais"

    segs = http_json("GET", f"/api/v1/projects/{pid}/segments")
    print("[9] segmentos:", [(s["index"], s["title"], s["start_time"], s["end_time"], s["score"]) for s in segs])

    subs = http_json("GET", f"/api/v1/projects/{pid}/segments/0/subtitles")
    print("[10] legendas (segmento 0):", subs.get("schema_version"), len(subs.get("segments", [])), "blocos")

    print("[11] eventos SSE:", len(sse_events))
    kinds = [e for e in sse_events if not e.startswith("__")]
    print("     amostra:", kinds[:4])
    assert any("job.progress" in k for k in kinds), "esperavam-se eventos pipeline/job no SSE"

    # download final
    dl = finals[0]
    req = urllib.request.Request(f"{BASE}/api/v1/projects/{pid}/assets/{dl['id']}/download")
    with urllib.request.urlopen(req) as r:
        blob = r.read()
    print("[12] download final:", dl["name"], len(blob), "bytes")
    assert len(blob) > 10000

    print("\nOK: pipeline ao vivo via REST+Celery+Redis+SSE completo.")


if __name__ == "__main__":
    main()