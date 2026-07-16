import json
from pathlib import Path

from tools.issue245 import build_current_inventory_from_cross as builder


def _write_inventory(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"records": records}), encoding="utf-8")


def test_resolve_host_path_maps_workspace_to_main_repo(tmp_path: Path) -> None:
    assert builder.resolve_host_path(tmp_path, "/workspace/logs/a.json") == tmp_path / "logs/a.json"
    assert builder.resolve_host_path(tmp_path, "logs/b.json") == tmp_path / "logs/b.json"


def test_build_current_inventory_combines_current_mask_and_prediction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(builder, "EXPECTED_PAGES", 1)
    main_repo = tmp_path / "repo"
    staff_mask = main_repo / "logs/current_mask.png"
    current_hybrid = main_repo / "logs/current_hybrid.json"
    historical_hybrid = main_repo / "logs/historical_hybrid.json"
    historical_mask = main_repo / "logs/historical_mask.png"
    for path in (staff_mask, current_hybrid, historical_hybrid, historical_mask):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]", encoding="utf-8")

    mask_inventory = tmp_path / "cross_c.json"
    pred_inventory = tmp_path / "cross_d.json"
    _write_inventory(
        mask_inventory,
        [
            {
                "score": "score",
                "page": "page_001",
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
                "score": "score",
                "page": "page_001",
                "image": "/workspace/data/page_001.png",
                "staff_mask": "/workspace/logs/historical_mask.png",
                "hybrid_predictions": "/workspace/logs/current_hybrid.json",
            }
        ],
    )

    payload = builder.build_current_inventory(
        main_repo=main_repo,
        current_mask_inventory=mask_inventory,
        current_prediction_inventory=pred_inventory,
    )

    record = payload["records"][0]
    assert record["staff_mask"] == str(staff_mask)
    assert record["hybrid_predictions"] == str(current_hybrid)
    assert record["image"] == str(main_repo / "data/page_001.png")
