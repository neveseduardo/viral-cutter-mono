from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Minimal user model; `owner` on Project may be null for local mode."""

    locale = models.CharField(max_length=10, default="pt-br")
    api_keys = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]