"""Configuration helpers for the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit("PyYAML is required. Install it in the current environment.") from exc
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("Config root must be a mapping.")
    # TODO: Replace with a schema-based config (pydantic/dataclasses) for validation.
    return data


def get_nested(config: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = config
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current
