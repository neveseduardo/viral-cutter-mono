from django.urls import path

from . import views

app_name = "v1"

urlpatterns = [
    path("projects", views.ProjectListCreateView.as_view(), name="project-list"),
    path("projects/<int:pk>", views.ProjectDetailView.as_view(), name="project-detail"),
    path("projects/<int:project_id>/ingest", views.IngestView.as_view(), name="project-ingest"),
    path("projects/<int:project_id>/assets", views.AssetListView.as_view(), name="project-assets"),
    path("projects/<int:project_id>/assets/<int:asset_id>/download", views.AssetDownloadView.as_view(), name="asset-download"),
    path("projects/<int:project_id>/assets/<int:asset_id>/content", views.AssetContentView.as_view(), name="asset-content"),
    path("projects/<int:project_id>/transcript", views.TranscriptView.as_view(), name="project-transcript"),
    path("projects/<int:project_id>/segments", views.SegmentsView.as_view(), name="project-segments"),
    path("projects/<int:project_id>/segments/<int:idx>/subtitles", views.SegmentSubtitlesView.as_view(), name="segment-subtitles"),
    path("projects/<int:project_id>/segments/<int:idx>/render", views.SegmentRenderView.as_view(), name="segment-render"),
    path("projects/<int:project_id>/segments/<int:idx>/export", views.SegmentExportView.as_view(), name="segment-export"),
    path("projects/<int:project_id>/pipeline-runs", views.PipelineRunCreateView.as_view(), name="pipeline-run-create"),
    path("projects/<int:project_id>/pipeline-runs/history", views.PipelineRunHistoryView.as_view(), name="pipeline-run-history"),
    path("pipeline-runs/<int:pk>", views.PipelineRunDetailView.as_view(), name="pipeline-run-detail"),
    path("pipeline-runs/<int:id>/cancel", views.PipelineRunCancelView.as_view(), name="pipeline-run-cancel"),
    path("pipeline-runs/<int:id>/jobs", views.PipelineRunJobListView.as_view(), name="pipeline-run-jobs"),
    path("jobs/<int:id>/cancel", views.JobCancelView.as_view(), name="job-cancel"),
    path("jobs/<int:id>/retry", views.JobRetryView.as_view(), name="job-retry"),
    path("profiles", views.ProfileViewSet.as_view({"get": "list", "post": "create"}), name="profile-list"),
    path("profiles/<int:pk>", views.ProfileViewSet.as_view({"get": "retrieve", "put": "update", "delete": "destroy"}), name="profile-detail"),
    path("exports/<int:asset_id>", views.ExportAssetView.as_view(), name="export-asset"),
    path("config/frontend", views.FrontendConfigView.as_view(), name="frontend-config"),
]