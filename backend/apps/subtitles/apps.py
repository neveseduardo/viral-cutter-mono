from django.apps import AppConfig


class SubtitlesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.subtitles"
    label = "subtitles"


__all__ = ["SubtitlesConfig"]