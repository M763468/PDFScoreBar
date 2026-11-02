"""Keep the configuration reference in sync with the canonical production config."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "dense_full_pipeline.yaml"
REFERENCE = ROOT / "docs" / "dev" / "CONFIGURATION_REFERENCE.md"


def _leaf_keys(mapping: dict, prefix: tuple[str, ...] = ()) -> list[str]:
    keys: list[str] = []
    for key, value in mapping.items():
        path = prefix + (str(key),)
        if isinstance(value, dict) and value:
            keys.extend(_leaf_keys(value, path))
        else:
            keys.append(".".join(path))
    return keys


def missing_reference_keys(config: dict, reference_text: str) -> list[str]:
    return [key for key in _leaf_keys(config) if f"`{key}`" not in reference_text]


def test_every_canonical_config_key_is_documented() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    reference = REFERENCE.read_text(encoding="utf-8")
    assert missing_reference_keys(config, reference) == []


def test_new_canonical_key_is_reported_as_missing() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["detection"]["undocumented_new_key"] = True
    reference = REFERENCE.read_text(encoding="utf-8")
    assert missing_reference_keys(config, reference) == ["detection.undocumented_new_key"]
