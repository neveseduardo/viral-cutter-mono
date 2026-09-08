"""pytest / Django test-suite configuration.

Patches settings so that tests run without Redis or any external services:
- Celery runs in eager/synchronous mode (no broker needed).
- Celery result backend uses in-memory cache (no Redis needed).
- Storage uses a per-session temp directory.
"""

import os
import tempfile

import django
from django.test.utils import override_settings


def pytest_configure(config):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


# The manage.py test runner picks up these settings via the module-level
# override below. pytest-django users get it from pytest.ini / pyproject.toml.
TEST_OVERRIDES = {
    "CELERY_TASK_ALWAYS_EAGER": True,
    "CELERY_TASK_EAGER_PROPAGATES": True,
    # Use in-memory result backend so no Redis is needed in unit/integration tests.
    "CELERY_RESULT_BACKEND": "cache+memory://",
    "CELERY_BROKER_URL": "memory://",
    "AUTH_DISABLED": True,
}
