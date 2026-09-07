"""Fingerprints for idempotent artifact processing (AGENTS.md §4.5).

fingerprint = hash(input_asset_checksum + stage + model + relevant_configuration)
"""

import hashlib
import json


def _stable(value) -> str:
    """Render any config value into a stable string."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def compute_fingerprint(*, input_checksum: str, stage: str, model: str = "", config: dict | None = None) -> str:
    raw = "|".join([
        _stable(input_checksum),
        _stable(stage),
        _stable(model),
        _stable(config or {}),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def asset_fingerprint(asset, stage: str, model: str = "", config: dict | None = None) -> str:
    """Fingerprint for a stage that consumes a VideoAsset."""
    return compute_fingerprint(
        input_checksum=asset.checksum or asset.storage_key,
        stage=stage,
        model=model,
        config=config,
    )