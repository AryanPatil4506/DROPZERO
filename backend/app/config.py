"""Versioned YAML config (thresholds, dictionaries). No inline magic constants."""

import hashlib
import json
from functools import lru_cache
from typing import Any

import yaml

from backend.app.settings import get_settings


@lru_cache
def load_config(name: str) -> dict[str, Any]:
    path = get_settings().config_dir / f"{name}.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def config_hash(obj: Any) -> str:
    """Stable short hash of a JSON-serialisable config object."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
