"""Domain models — see AGENTS.md §4.

Project, PipelineRun, Job, VideoAsset, ProcessingProfile, Transcription,
Segment and the artifact fingerprint cache.
"""

from django.conf import settings
from django.db import models

# ---------------------------------------------------------------------------
# Status enums
# ---------------------------------------------------------------------------


class ProjectStatus(models.TextChoices):
    EMPTY = "empty", "Empty"
    INGESTED = "ingested", "Ingested"
    TRANSCRIBED = "transcribed", "Transcribed"
    ANALYZED = "analyzed", "Analyzed"
    READY = "ready", "Ready"
    ERROR = "error", "Error"


class Workflow(models.TextChoices):
    FULL = "full", "Full"
    CUT_ONLY = "cut_only", "Cut only"
    SUBTITLES_ONLY = "subtitles_only", "Subtitles only"


class RunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    PARTIAL = "partial", "Partial"


class JobStage(models.TextChoices):
    INGEST = "ingest", "Ingest"
    TRANSCRIBE = "transcribe", "Transcribe"
    ANALYZE = "analyze", "Analyze"
    ALIGN = "align", "Align"
    CUT = "cut", "Cut"
    EDIT = "edit", "Edit"
    SUBTITLES = "subtitles", "Subtitles"
    TRANSLATE = "translate", "Translate"
    RENDER = "render", "Render"


class QueueName(models.TextChoices):
    IO = "io", "IO"
    CPU = "cpu", "CPU"
    GPU = "gpu", "GPU"


class JobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    SKIPPED = "skipped", "Skipped"


class AssetKind(models.TextChoices):
    SOURCE = "source", "Source"
    DOWNLOADED = "downloaded", "Downloaded"
    NORMALIZED = "normalized", "Normalized"
    CUT = "cut", "Cut"
    EDITED = "edited", "Edited"
    SUBTITLED = "subtitled", "Subtitled"
    FINAL = "final", "Final"
    PREVIEW = "preview", "Preview"
    THUMBNAIL = "thumbnail", "Thumbnail"


class SegmentStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    CUT = "cut", "Cut"
    EDITED = "edited", "Edited"
    RENDERED = "rendered", "Rendered"
    FAILED = "failed", "Failed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Project(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE
    )
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.EMPTY
    )
    source_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Project({self.id}, {self.name})"

    def recompute_status(self) -> str:
        """Rolls up child state into a Project-level status (§4.1)."""
        if not self.assets.filter(kind=AssetKind.NORMALIZED).exists():
            self.status = ProjectStatus.EMPTY
        elif not hasattr(self, "transcription"):
            self.status = ProjectStatus.INGESTED
        elif not self.segments.exists():
            self.status = ProjectStatus.TRANSCRIBED
        elif self.assets.filter(kind=AssetKind.FINAL).exists():
            self.status = ProjectStatus.READY
        else:
            self.status = ProjectStatus.ANALYZED
        self.save(update_fields=["status", "updated_at"])
        return self.status


class ProcessingProfile(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE
    )
    name = models.CharField(max_length=120)
    is_builtin = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"Profile({self.name})"


class PipelineRun(models.Model):
    """One complete processing request (🔒 distinct from Job, §4.2)."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="pipeline_runs")
    workflow = models.CharField(max_length=20, choices=Workflow.choices, default=Workflow.FULL)
    status = models.CharField(
        max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING
    )
    configuration_snapshot = models.JSONField(default=dict, blank=True)
    profile = models.ForeignKey(
        ProcessingProfile, null=True, blank=True, on_delete=models.SET_NULL
    )
    progress = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"PipelineRun({self.id}, {self.workflow}, {self.status})"


class Job(models.Model):
    """A single pipeline stage (🔒 distinct from PipelineRun, §4.2)."""

    pipeline_run = models.ForeignKey(
        PipelineRun, on_delete=models.CASCADE, related_name="jobs"
    )
    stage = models.CharField(max_length=20, choices=JobStage.choices)
    queue = models.CharField(max_length=10, choices=QueueName.choices, default=QueueName.CPU)
    status = models.CharField(
        max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING
    )
    progress = models.IntegerField(default=0)
    attempt = models.IntegerField(default=0)
    message = models.CharField(max_length=255, blank=True, default="")
    error = models.TextField(blank=True, default="")
    logs = models.JSONField(default=list, blank=True)
    segment_index = models.IntegerField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Job({self.id}, {self.stage}, {self.status})"


class VideoAsset(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="assets")
    parent_asset = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    kind = models.CharField(max_length=20, choices=AssetKind.choices)
    storage_key = models.CharField(max_length=512)  # never an absolute path
    original_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=100, blank=True, default="video/mp4")
    size = models.BigIntegerField(default=0)
    duration = models.FloatField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    fps = models.FloatField(null=True, blank=True)
    codec = models.CharField(max_length=60, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    segment_index = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"Asset({self.id}, {self.kind}, {self.storage_key})"


class Transcription(models.Model):
    project = models.OneToOneField(
        Project, on_delete=models.CASCADE, related_name="transcription"
    )
    language = models.CharField(max_length=10, default="pt")
    source = models.CharField(max_length=20, default="whisper")  # whisper | youtube_subs
    model = models.CharField(max_length=120, default="")
    segments = models.JSONField(default=list)
    schema_version = models.CharField(max_length=10, default="1.0")
    fingerprint = models.CharField(max_length=64, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "fingerprint"], name="uniq_transcription_project_fingerprint"
            ),
        ]

    def __str__(self):
        return f"Transcription({self.project_id}, {self.language})"


class Segment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="segments")
    pipeline_run = models.ForeignKey(
        PipelineRun, null=True, blank=True, on_delete=models.SET_NULL
    )
    index = models.IntegerField(default=0)
    title = models.CharField(max_length=255, default="")
    hook = models.CharField(max_length=255, blank=True, default="")
    start_text = models.CharField(max_length=512, blank=True, default="")
    end_text = models.CharField(max_length=512, blank=True, default="")
    reasoning = models.TextField(blank=True, default="")
    score = models.FloatField(default=0)
    scores = models.JSONField(default=dict, blank=True)
    start_time = models.FloatField(default=0)
    end_time = models.FloatField(default=0)
    status = models.CharField(
        max_length=20, choices=SegmentStatus.choices, default=SegmentStatus.QUEUED
    )
    rejected = models.BooleanField(default=False)
    rejection_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["index"]

    def subs_stem(self, title: str | None = None) -> str:
        from django.utils.text import slugify

        return f"{self.index:03d}_{slugify(title or self.title) or 'seg'}"

    def __str__(self):
        return f"Segment({self.index}, {self.title})"


class ArtifactCache(models.Model):
    """Fingerprint → completed artifact mapping (se §4.5 idempotency)."""

    fingerprint = models.CharField(max_length=64, db_index=True)
    stage = models.CharField(max_length=20)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="cached_artifacts")
    asset = models.ForeignKey(
        VideoAsset, null=True, blank=True, on_delete=models.SET_NULL
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "stage", "fingerprint"], name="uniq_artifactcache_project_stage_fingerprint"
            ),
        ]

    def __str__(self):
        return f"ArtifactCache({self.stage}, {self.fingerprint[:12]}…)"