"""Storage helpers for the Media Engine (AGENTS.md §6).

All filesystem access goes through here — never expose absolute paths
outside this module.
"""

import os
import uuid
from pathlib import Path

from django.conf import settings


def _root() -> Path:
    """Absolute path to the configured storage root."""
    root = getattr(settings, "STORAGE_ROOT", None) or getattr(settings, "MAIN_STORAGE_ROOT", None)
    if root is None:
        root = Path(settings.BASE_DIR).parent / "data"
    return Path(root)


def abs_path(key: str) -> Path:
    """Convert a storage key (relative) to an absolute filesystem Path.

    The key must never be an absolute path; callers that try to pass one
    will get a ValueError so the contract is enforced everywhere.
    """
    if not key:
        # Callers that need the storage root itself (e.g. to build paths)
        return _root()
    key = key.lstrip("/")
    if os.path.isabs(key):
        raise ValueError(f"abs_path received an absolute path: {key!r}")
    return _root() / key


def make_random_key(project_id: int | str, category: str, ext: str) -> str:
    """Generate a unique, collision-resistant storage key for a new file.

    Example: ``projects/42/cuts/a3f9c1b2.mp4``

    Args:
        project_id: Project primary key.
        category:   Sub-folder (e.g. ``cuts``, ``normalized``, ``subs``).
        ext:        File extension *with* the leading dot (e.g. ``".mp4"``)
                    or *without* (e.g. ``"mp4"``). Empty string is allowed.
    """
    uid = uuid.uuid4().hex
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    return f"projects/{project_id}/{category}/{uid}{ext}"
