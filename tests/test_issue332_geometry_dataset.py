import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from tools.mmr_training.issue332.materialize_geometry_dataset import freeze_split, materialize


def _sample(sample_id, score_id, page_id, label=0, tags=None):
    return {
        "sample_id": sample_id,
        "score_id": score_id,
        "page_id": page_id,
        "image_path": "page.png",
        "bbox": [20, 20, 60, 60],
        "label": label,
        "tags": tags or [],
    }


def test_freeze_split_keeps_score_siblings_together_and_is_deterministic():
    samples = [
        _sample("a1", "score-a", "page-1"),
        _sample("a2", "score-a", "page-2", 1),
        _sample("b1", "score-b", "page-1"),
        _sample("c1", "score-c", "page-1"),
    ]
    first = freeze_split(samples, seed=42, validation_ratio=0.25, group_level="score")
    assert first == freeze_split(samples, seed=42, validation_ratio=0.25, group_level="score")
    assert first["a1"] == first["a2"]


def test_materialize_excludes_acceptance_controls_and_pairs_datasets(tmp_path: Path):
    cv2.imwrite(str(tmp_path / "page.png"), np.full((100, 100, 3), 255, dtype=np.uint8))
    source_manifest = tmp_path / "source.json"
    source_manifest.write_text(
        json.dumps(
            {
                "samples": [
                    _sample("train", "score-a", "page-1", 1),
                    _sample("control", "score-b", "page-1", tags=["issue277-control"]),
                ]
            }
        ),
        encoding="utf-8",
    )
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"deltas_px": [1], "split": {"validation_ratio": 0.5}}), encoding="utf-8"
    )
    result = materialize(
        manifest_path=source_manifest, output_root=tmp_path / "out", config_path=config
    )
    rows = result["rows"]
    assert rows and all(row["sample_id"] != "control" for row in rows)
    assert {row["dataset"] for row in rows} == {"baseline", "candidate"}
    assert {row["split"] for row in rows} == {result["split_contract"]["assignments"]["train"]}
    assert result["data_contract"]["acceptance_controls_excluded_from_training"] is True


def test_materialize_rejects_missing_source_page(tmp_path: Path):
    manifest = tmp_path / "source.json"
    manifest.write_text(json.dumps({"samples": [_sample("x", "s", "p")]}), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        materialize(manifest_path=manifest, output_root=tmp_path / "out")
