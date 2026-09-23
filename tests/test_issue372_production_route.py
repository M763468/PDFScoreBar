"""Focused production-route guards for Issue #372 compatibility behavior."""

from __future__ import annotations

import json
from pathlib import Path

from src.pipeline.detection.restored_orchestrator import DetectorOrchestrator
from src.pipeline.detector_routes.dense_full_pipeline import (
    build_late_raw_x4_union,
    inject_current_x4_gaps,
    load_frozen_hybrid_band_sources,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_production_late_raw_union_matches_retained_counterfactual_policy() -> None:
    raw = [
        [10, 10, 14, 110],
        [100, 10, 104, 110],
    ]
    x4 = [
        [10, 10, 14, 110],
        [200, 10, 204, 110],
        [200, 10, 204, 110],
    ]

    union, promoted = build_late_raw_x4_union(
        raw_boxes=raw,
        x4_boxes=x4,
    )

    assert promoted == [[200, 10, 204, 110]]
    assert union == [
        [10, 10, 14, 110],
        [100, 10, 104, 110],
        [200, 10, 204, 110],
    ]


def test_production_late_raw_injection_occurs_on_existing_raw_tree(tmp_path: Path) -> None:
    x4 = tmp_path / "x4.json"
    _write_json(
        x4,
        {
            "predictions": [
                {"orig_bbox": [10, 10, 14, 110]},
                {"orig_bbox": [200, 10, 204, 110]},
            ]
        },
    )
    inventory = tmp_path / "inventory.json"
    _write_json(
        inventory,
        {
            "records": [
                {
                    "score": "Score",
                    "page": "page_001",
                    "current_x4_detection": str(x4),
                }
            ]
        },
    )
    exclude = tmp_path / "exclude.json"
    _write_json(exclude, {"excluded_pages": []})

    raw = (
        tmp_path
        / "raw"
        / "Score"
        / "page_001"
        / "pipeline2_no_peak_candidates.json"
    )
    _write_json(raw, [[10, 10, 14, 110]])
    summary_path = tmp_path / "summary.json"

    summary = inject_current_x4_gaps(
        inventory=inventory,
        exclude=exclude,
        raw_root=tmp_path / "raw",
        summary_out=summary_path,
    )

    assert json.loads(raw.read_text(encoding="utf-8")) == [
        [10, 10, 14, 110],
        [200, 10, 204, 110],
    ]
    assert summary["processed"] == 1
    assert summary["total_promoted_x4_boxes"] == 1
    assert summary["injection_boundary"] == (
        "after initial raw generation, before candidate filter"
    )
    assert summary_path.is_file()


def test_frozen_cnn_band_sources_use_pre_probe_hybrid_inventory(tmp_path: Path) -> None:
    image = tmp_path / "Score" / "page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    hybrid = tmp_path / "hybrid.json"
    _write_json(hybrid, [[10, 20, 14, 120]])

    inventory = tmp_path / "inventory.json"
    _write_json(
        inventory,
        {
            "records": [
                {
                    "score": "Score",
                    "page": "page_001",
                    "image": str(image),
                    "hybrid_predictions": str(hybrid),
                }
            ]
        },
    )
    exclude = tmp_path / "exclude.json"
    _write_json(exclude, {"excluded_pages": []})

    sources = load_frozen_hybrid_band_sources(
        inventory=inventory,
        exclude=exclude,
    )

    assert sources == {image.resolve(): hybrid.resolve()}


def test_dense_inventory_records_current_x4_detection_from_physical_support_layout(
    tmp_path: Path,
) -> None:
    image = tmp_path / "physical_pages" / "Score_page_001.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")

    hybrid_root = tmp_path / "hybrid"
    stem = image.stem

    hybrid = hybrid_root / "hybrid_results" / f"{stem}_hybrid.json"
    _write_json(hybrid, [[10, 20, 14, 120]])

    baseline_page = hybrid_root / "baseline" / "batch" / stem
    baseline_page.mkdir(parents=True)
    (baseline_page / f"{stem}_debug_3_staff.png").write_bytes(b"staff")
    (baseline_page / f"{stem}_debug_7_clefs_keys.png").write_bytes(b"clef")

    x4 = tmp_path / "x4_detection.json"
    _write_json(x4, {"predictions": [{"orig_bbox": [10, 20, 14, 120]}]})

    support_result = (
        hybrid_root
        / "current_support"
        / image.parent.name
        / image.stem
        / "result.json"
    )
    _write_json(
        support_result,
        {
            "status": "completed",
            "historical_detector_artifact_runtime_input": False,
            "current_sr_detection": str(x4.resolve()),
        },
    )

    orchestrator = DetectorOrchestrator(
        config={
            "detection": {
                "detector_route": "dense_full_pipeline",
                "homr_profile": "maintained_original",
                "cnn_apply_nms": False,
            }
        },
        images=[image],
        run_id="issue372-production-route-test",
        run_dir=tmp_path / "run",
        dry_run=False,
    )
    orchestrator.hybrid_output_dir = hybrid_root

    inventory_path, _ = orchestrator._write_dense_inventory()
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    record = payload["records"][0]

    assert record["score"] == "Score"
    assert record["page"] == "page_001"
    assert Path(record["current_x4_detection"]) == x4.resolve()
    assert Path(record["hybrid_predictions"]) == hybrid.resolve()
