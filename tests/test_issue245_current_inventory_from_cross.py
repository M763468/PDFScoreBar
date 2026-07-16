import json
from pathlib import Path

from tools.issue245 import build_current_inventory_from_cross as builder


def _write_inventory(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"records": records}), encoding="utf-8")


def _write_json(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")


def test_resolve_host_path_maps_workspace_to_main_repo(tmp_path: Path) -> None:
    assert builder.resolve_host_path(tmp_path, "/workspace/logs/a.json") == tmp_path / "logs/a.json"
    assert builder.resolve_host_path(tmp_path, "logs/b.json") == tmp_path / "logs/b.json"


def test_resolve_current_layers_supports_score_qualified_layout(tmp_path: Path) -> None:
    score = "Example_Score"
    page = "page_001"
    stem = f"{score}_{page}"
    run_root = tmp_path / "production_default_full68"
    source_layers = {
        "baseline": run_root / "baseline" / "batch" / stem / f"{stem}_detections.json",
        "sr": run_root / "sr" / "batch" / stem / f"{stem}_detections.json",
        "omr": run_root / "omr_sr" / stem / "predictions.json",
        "hybrid": run_root / "hybrid_results" / f"{stem}_hybrid.json",
    }
    for path in source_layers.values():
        _write_json(path)

    assert builder.resolve_current_layers(source_layers["hybrid"], score, page) == {
        name: path.resolve() for name, path in source_layers.items()
    }


def test_build_current_inventory_combines_and_normalizes_cross_sources(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(builder, "EXPECTED_PAGES", 1)
    main_repo = tmp_path / "repo"
    score = "Example_Score"
    page = "page_001"
    stem = f"{score}_{page}"
    run_root = main_repo / "logs/current/production_default_full68"

    staff_mask = main_repo / "logs/current_mask.png"
    historical_hybrid = main_repo / "logs/historical_hybrid.json"
    historical_mask = main_repo / "logs/historical_mask.png"
    for path in (staff_mask, historical_hybrid, historical_mask):
        _write_json(path)

    source_layers = {
        "baseline": run_root / "baseline" / "batch" / stem / f"{stem}_detections.json",
        "sr": run_root / "sr" / "batch" / stem / f"{stem}_detections.json",
        "omr": run_root / "omr_sr" / stem / "predictions.json",
        "hybrid": run_root / "hybrid_results" / f"{stem}_hybrid.json",
    }
    for path in source_layers.values():
        _write_json(path)

    mask_inventory = tmp_path / "cross_c.json"
    pred_inventory = tmp_path / "cross_d.json"
    _write_inventory(
        mask_inventory,
        [
            {
                "score": score,
                "page": page,
                "image": "/workspace/data/page_001.png",
                "staff_mask": "/workspace/logs/current_mask.png",
                "hybrid_predictions": "/workspace/logs/historical_hybrid.json",
            }
        ],
    )
    _write_inventory(
        pred_inventory,
        [
            {
                "score": score,
                "page": page,
                "image": "/workspace/data/page_001.png",
                "staff_mask": "/workspace/logs/historical_mask.png",
                "hybrid_predictions": (
                    "/workspace/logs/current/production_default_full68/"
                    f"hybrid_results/{stem}_hybrid.json"
                ),
            }
        ],
    )

    normalized_root = main_repo / "logs/normalized"
    payload = builder.build_current_inventory(
        main_repo=main_repo,
        current_mask_inventory=mask_inventory,
        current_prediction_inventory=pred_inventory,
        normalized_root=normalized_root,
    )

    record = payload["records"][0]
    normalized_page_root = normalized_root / score / page
    expected_hybrid = normalized_page_root / "hybrid_results" / f"{page}_hybrid.json"
    assert record["staff_mask"] == str(staff_mask)
    assert record["hybrid_predictions"] == str(expected_hybrid)
    assert record["image"] == str(main_repo / "data/page_001.png")
    assert expected_hybrid.is_symlink()
    assert expected_hybrid.resolve() == source_layers["hybrid"].resolve()
    assert (
        normalized_page_root / "baseline" / "batch" / page / f"{page}_detections.json"
    ).resolve() == source_layers["baseline"].resolve()
    assert (
        normalized_page_root / "sr" / "batch" / page / f"{page}_detections.json"
    ).resolve() == source_layers["sr"].resolve()
    assert (normalized_page_root / "omr_sr" / page / "predictions.json").resolve() == source_layers[
        "omr"
    ].resolve()
