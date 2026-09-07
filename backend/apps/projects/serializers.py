"""REST serializers for the project domain (AGENTS.md §11)."""

from rest_framework import serializers

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


class ProjectSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id", "name", "owner", "status", "status_display",
            "source_url", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]


class VideoAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = VideoAsset
        fields = [
            "id", "kind", "storage_key", "original_name", "mime_type", "size",
            "duration", "width", "height", "fps", "codec", "checksum",
            "segment_index", "parent_asset", "metadata", "created_at",
            "url", "download_url",
        ]
        read_only_fields = fields

    def get_url(self, obj):
        return f"/api/v1/projects/{obj.project_id}/assets/{obj.id}/content"

    def get_download_url(self, obj):
        return f"/api/v1/projects/{obj.project_id}/assets/{obj.id}/download"


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id", "stage", "queue", "status", "progress", "attempt",
            "message", "error", "logs", "segment_index",
            "started_at", "finished_at", "created_at",
        ]
        read_only_fields = fields


class PipelineRunSerializer(serializers.ModelSerializer):
    jobs = JobSerializer(many=True, read_only=True)

    class Meta:
        model = PipelineRun
        fields = [
            "id", "project", "workflow", "status", "configuration_snapshot",
            "profile", "progress", "started_at", "finished_at", "created_at",
            "jobs",
        ]
        read_only_fields = ["id", "status", "progress", "started_at", "finished_at", "created_at"]


class PipelineRunCreateSerializer(serializers.Serializer):
    workflow = serializers.ChoiceField(choices=["full", "cut_only", "subtitles_only"], default="full")
    profile_id = serializers.IntegerField(required=False, allow_null=True)
    overrides = serializers.JSONField(default=dict, required=False)


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Segment
        fields = [
            "id", "index", "title", "hook", "reasoning", "score", "scores",
            "start_time", "end_time", "status", "rejected", "rejection_reason",
        ]
        read_only_fields = ["id", "status"]


class TranscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transcription
        fields = [
            "id", "language", "source", "model", "segments",
            "schema_version", "fingerprint", "created_at",
        ]
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessingProfile
        fields = ["id", "name", "is_builtin", "config", "created_at"]
        read_only_fields = ["id", "is_builtin", "created_at"]


class ArtifactCacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArtifactCache
        fields = ["id", "fingerprint", "stage", "payload", "created_at"]