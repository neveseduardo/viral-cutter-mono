"""Users and optional authentication.

In default local single-user mode (`AUTH_DISABLED=true`) every request is
treated as belonging to a global anonymous owner and auth endpoints return
a guest token.
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"