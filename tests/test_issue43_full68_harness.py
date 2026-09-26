import json
from pathlib import Path

import pytest

from experiments.issue43.compare_full68_x_domain import (
    UPSTREAM_MANIFEST_SCHEMA,
    _group_images_by_score,
    _source_commit,
    _validate_inventory,
    _validate_upstream_manifest,
)


def _write_inventory(path: Path, *, score: str, image: Path) -> Path:
    page = image.stem
    artifacts = {}
    for field, suffix in (
        ("hybrid_predictions", "hybrid.json"),
        ("staff_mask", "staff.png"),
        ("clef_mask", "clef.png"),
    ):
        artifact = path.parent / f"{score}_{page}_{suffix}"
        artifact.write_bytes(b"x")
        artifacts[field] = str(artifact)

    path.write_text(
        json.dumps(
            {
                "schema_version": "pipeline.detector_routes.current_run_inventory.v1",
                "historical_detector_artifact_runtime_input": False,
                "records": [
                    {
                        "score": score,
                        "page": page,
                        "image": str(image),
                        **artifacts,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_group_images_keeps_duplicate_page_stems_score_isolated(tmp_path):
    image_a = tmp_path / "ScoreA" / "page_001.png"
    image_b = tmp_path / "ScoreB" / "page_001.png"
    image_a.parent.mkdir()
    image_b.parent.mkdir()
    image_a.write_bytes(b"a")
    image_b.write_bytes(b"b")

    groups = _group_images_by_score([image_a, image_b])

    assert list(groups) == ["ScoreA", "ScoreB"]
    assert groups["ScoreA"] == [image_a]
    assert groups["ScoreB"] == [image_b]


def test_upstream_manifest_accepts_same_page_stem_in_separate_scores(tmp_path):
    image_a = tmp_path / "images" / "ScoreA" / "page_001.png"
    image_b = tmp_path / "images" / "ScoreB" / "page_001.png"
    image_a.parent.mkdir(parents=True)
    image_b.parent.mkdir(parents=True)
    image_a.write_bytes(b"a")
    image_b.write_bytes(b"b")

    inventory_a = _write_inventory(
        tmp_path / "inventory_a.json",
        score="ScoreA",
        image=image_a,
    )
    inventory_b = _write_inventory(
        tmp_path / "inventory_b.json",
        score="ScoreB",
        image=image_b,
    )

    _validate_inventory(inventory_a, images=[image_a])
    _validate_inventory(inventory_b, images=[image_b])

    import hashlib

    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": UPSTREAM_MANIFEST_SCHEMA,
                "groups": [
                    {
                        "score": "ScoreA",
                        "page_count": 1,
                        "inventory": str(inventory_a),
                        "inventory_sha256": sha256(inventory_a),
                    },
                    {
                        "score": "ScoreB",
                        "page_count": 1,
                        "inventory": str(inventory_b),
                        "inventory_sha256": sha256(inventory_b),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    groups = _validate_upstream_manifest(
        manifest,
        image_groups={
            "ScoreA": [image_a],
            "ScoreB": [image_b],
        },
    )

    assert [group["score"] for group in groups] == ["ScoreA", "ScoreB"]
    assert [group["page_count"] for group in groups] == [1, 1]


def test_source_commit_comes_from_host_environment(monkeypatch):
    commit = "a" * 40
    monkeypatch.setenv("ISSUE43_SOURCE_COMMIT", commit)

    assert _source_commit() == commit


def test_source_commit_rejects_missing_or_invalid_value(monkeypatch):
    monkeypatch.delenv("ISSUE43_SOURCE_COMMIT", raising=False)
    with pytest.raises(RuntimeError, match="ISSUE43_SOURCE_COMMIT"):
        _source_commit()

    monkeypatch.setenv("ISSUE43_SOURCE_COMMIT", "not-a-commit")
    with pytest.raises(RuntimeError, match="ISSUE43_SOURCE_COMMIT"):
        _source_commit()
