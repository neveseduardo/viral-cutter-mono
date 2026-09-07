from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from django.db import connection

from django.conf import settings


def health(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False

    import redis

    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        redis_ok = True
    except Exception:
        redis_ok = False

    status = 200 if (db_ok and redis_ok) else 503
    return JsonResponse({"status": "ok" if status == 200 else "degraded", "db": db_ok, "redis": redis_ok}, status=status)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.projects.urls", namespace="v1")),
    path("api/v1/auth/", include("apps.accounts.urls", namespace="auth")),
    path("api/v1/health", health, name="health"),
    # SSE de progresso no topo (contrato §11: GET /stream/pipeline-runs/{id}),
    # fora do namespace api/v1, para casar com o proxy nginx/vite.
    path("stream/", include("apps.projects.sse_urls")),
]