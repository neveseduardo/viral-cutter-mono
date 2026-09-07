from rest_framework.permissions import BasePermission

from django.conf import settings


class LocalFirstPermission(BasePermission):
    """When AUTH_DISABLED=true every request is authenticated as guest."""

    def has_permission(self, request, view):
        if settings.AUTH_DISABLED:
            request.user = getattr(request, "user", None)
            return True
        return bool(request.user and request.user.is_authenticated)