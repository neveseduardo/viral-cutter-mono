"""Celery application for ViralCutter.

Queues are defined by task *nature* (io / cpu / gpu), see AGENTS.md §5.3.
Routing happens in settings.CELERY_TASK_ROUTES plus a dynamic router in
`pipeline.routing`.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("viralcutter")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, name="viralcutter.debug.echo")
def debug_task(self, *args, **kwargs):
    print(f"Request: {self.request!r}")
    return {"ok": True}