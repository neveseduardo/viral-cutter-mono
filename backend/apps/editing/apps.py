from django.apps import AppConfig


class EditingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.editing"
    label = "editing"


__all__ = ["EditingConfig"]