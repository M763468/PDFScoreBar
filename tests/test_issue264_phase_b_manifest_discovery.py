from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.utils.io import load_json
from tools.issue264 import run_phase_b_page001_acceptance as acceptance_entry


def test_matching_manifest_skips_non_mapping_json(tmp_path: Path) -> None:
    list_manifest = tmp_path / "list_manifest.json"
    list_manifest.write_text(
        json.dumps([{"run_id": acceptance_entry.CANONICAL_RUN}]) + "\n",
        encoding="utf-8",
    )

    canonical_manifest = tmp_path / "canonical_manifest.json"
    canonical_manifest.write_text(
        json.dumps({"run_id": acceptance_entry.CANONICAL_RUN}) + "\n",
        encoding="utf-8",
    )

    assert (
        acceptance_entry._matching_manifest([list_manifest, canonical_manifest])
        == canonical_manifest
    )


def test_materialize_canonical_artifact_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "page_001.png"
    barlines = tmp_path / "barlines.json"
    staff = tmp_path / "staff.png"
    image.write_bytes(b"image")
    barlines.write_text("[]\n", encoding="utf-8")
    staff.write_bytes(b"staff")

    monkeypatch.setattr(acceptance_entry, "CANONICAL_IMAGE", image)
    monkeypatch.setattr(acceptance_entry, "CANONICAL_BARLINES", barlines)
    monkeypatch.setattr(acceptance_entry, "CANONICAL_STAFF_MASK", staff)

    manifest_path = acceptance_entry.materialize_canonical_artifact_manifest(tmp_path / "run")
    payload = load_json(manifest_path)

    assert payload["run_id"] == acceptance_entry.CANONICAL_RUN
    assert payload["detector_reexecuted"] is False
    assert payload["artifact_source"] == "retained_canonical_detector_artifacts"
    assert payload["pages"] == [
        {
            "page_id": acceptance_entry.TARGET_STEM,
            "image_path": str(image),
            "barlines_json": str(barlines),
            "staff_mask": str(staff),
        }
    ]


def test_materialize_canonical_artifact_manifest_fails_on_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(acceptance_entry, "CANONICAL_IMAGE", tmp_path / "missing-image.png")
    monkeypatch.setattr(acceptance_entry, "CANONICAL_BARLINES", tmp_path / "missing-bars.json")
    monkeypatch.setattr(acceptance_entry, "CANONICAL_STAFF_MASK", tmp_path / "missing-staff.png")

    with pytest.raises(FileNotFoundError, match="required retained artifacts are missing"):
        acceptance_entry.materialize_canonical_artifact_manifest(tmp_path / "run")
