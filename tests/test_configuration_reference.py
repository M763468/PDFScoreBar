"""Keep the configuration reference in sync with the canonical production config.

Every leaf key of ``configs/dense_full_pipeline.yaml`` must appear exactly once as a
table row ``| `key` | `value` | ...`` in both the English original and the Japanese
translation, and the documented value must equal the canonical YAML value.
Meanings in the third column are prose and are not checked here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "dense_full_pipeline.yaml"
REFERENCES = (
    ROOT / "docs" / "dev" / "CONFIGURATION_REFERENCE.md",
    ROOT / "docs" / "dev" / "CONFIGURATION_REFERENCE.ja.md",
)

_ROW = re.compile(r"^\|\s*`(?P<key>[A-Za-z0-9_.]+)`\s*\|\s*`(?P<value>[^`]*)`\s*\|", re.MULTILINE)


def _leaf_values(mapping: dict, prefix: tuple[str, ...] = ()) -> dict[str, Any]:
    leaves: dict[str, Any] = {}
    for key, value in mapping.items():
        path = prefix + (str(key),)
        if isinstance(value, dict) and value:
            leaves.update(_leaf_values(value, path))
        else:
            leaves[".".join(path)] = value
    return leaves


def documented_values(reference_text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for match in _ROW.finditer(reference_text):
        rows.setdefault(match["key"], []).append(match["value"])
    return rows


def reference_drift(config: dict, reference_text: str) -> list[str]:
    """Return human-readable drift messages; an empty list means in sync."""
    rows = documented_values(reference_text)
    problems: list[str] = []
    for key, expected in _leaf_values(config).items():
        values = rows.get(key, [])
        if not values:
            problems.append(f"missing: {key}")
            continue
        if len(values) > 1:
            problems.append(f"duplicate rows: {key}")
        documented = yaml.safe_load(values[0])
        if documented != expected or type(documented) is not type(expected):
            problems.append(f"value drift: {key}: documented {values[0]!r}, config {expected!r}")
    return problems


def _load_config() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_every_canonical_config_key_and_value_is_documented() -> None:
    config = _load_config()
    for reference in REFERENCES:
        assert reference_drift(config, reference.read_text(encoding="utf-8")) == [], reference.name


def test_new_canonical_key_is_reported_as_missing() -> None:
    config = _load_config()
    config["detection"]["undocumented_new_key"] = True
    reference = REFERENCES[0].read_text(encoding="utf-8")
    assert reference_drift(config, reference) == ["missing: detection.undocumented_new_key"]


def test_changed_canonical_value_is_reported_as_drift() -> None:
    config = _load_config()
    config["detection"]["sr_scale"] = 2
    config["filters"]["blank_page"] = False
    reference = REFERENCES[1].read_text(encoding="utf-8")
    assert reference_drift(config, reference) == [
        "value drift: detection.sr_scale: documented '4', config 2",
        "value drift: filters.blank_page: documented 'auto', config False",
    ]
