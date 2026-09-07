from django.contrib import admin

from .models import (
    ArtifactCache,
    Job,
    PipelineRun,
    ProcessingProfile,
    Project,
    Segment,
    Transcription,
    VideoAsset,
)


class JobInline(admin.TabularInline):
    model = Job
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "owner", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name",)


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "workflow", "status", "progress", "created_at")
    list_filter = ("status", "workflow")
    inlines = [JobInline]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "pipeline_run", "stage", "queue", "status", "progress", "attempt")
    list_filter = ("stage", "queue", "status")


@admin.register(VideoAsset)
class VideoAssetAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "kind", "storage_key", "size", "created_at")
    list_filter = ("kind",)


@admin.register(Transcription)
class TranscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "language", "source", "model", "created_at")


@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "index", "title", "score", "start_time", "end_time", "status")
    list_filter = ("status",)


@admin.register(ProcessingProfile)
class ProcessingProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_builtin", "created_at")


@admin.register(ArtifactCache)
class ArtifactCacheAdmin(admin.ModelAdmin):
    list_display = ("id", "stage", "project", "fingerprint", "created_at")