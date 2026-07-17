from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.issue245.analyze_issue36_v12_producer_boundary import (
    InventoryRecordAmbiguousError,
    _find_inventory_record,
    build_report,
    resolve_summary_inputs,
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _boxes(boxes: list[list[int]]) -> list[list[int]]:
    return boxes


def _fixture(
    tmp_path: Path,
    *,
    existing: list[list[int]],
    raw: list[list[int]],
    filtered: list[list[int]],
) -> tuple[dict[str, Path], list[dict[str, object]]]:
    root = tmp_path / "repo"
    score = "Score"
    page = "page_001"
    full_span = [10, 10, 14, 110]
    short = [10, 50, 14, 110]
    image = root / "images" / "page.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"image-bytes")
    staff_mask = root / "masks" / "staff.png"
    staff_mask.parent.mkdir(parents=True, exist_ok=True)
    staff_mask.write_bytes(b"mask-bytes")
    historical_hybrid = _write_json(root / "historical_hybrid.json", _boxes(existing))
    current_hybrid = _write_json(root / "current_hybrid.json", _boxes([short]))
    _write_json(
        root / "historical_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "image": str(image.relative_to(root)),
                    "staff_mask": str(staff_mask.relative_to(root)),
                    "hybrid_predictions": str(historical_hybrid.relative_to(root)),
                }
            ]
        },
    )
    current_inventory = _write_json(
        root / "current_inventory.json",
        {
            "records": [
                {
                    "score": score,
                    "page": page,
                    "image": str(image.relative_to(root)),
                    "staff_mask": str(staff_mask.relative_to(root)),
                    "hybrid_predictions": str(current_hybrid.relative_to(root)),
                }
            ]
        },
    )
    raw_root = root / "raw"
    filtered_root = root / "filtered"
    scoring_root = root / "scoring"
    historical_final = root / "historical_final"
    stage_e = root / "stage_e"
    _write_json(raw_root / score / page / "pipeline2_no_peak_candidates.json", _boxes(raw))
    _write_json(
        filtered_root / score / page / "pipeline2_no_peak_candidates.json", _boxes(filtered)
    )
    _write_json(scoring_root / score / page / "pipeline2_no_peak_candidates.json", _boxes(filtered))
    _write_json(
        historical_final / f"eval2_{score}_{page}" / "pipeline2_no_peak_candidates.json",
        _boxes(filtered),
    )
    _write_json(
        stage_e
        / "dense_candidate_reconstruction"
        / "probe_candidates_from_inventory"
        / score
        / page
        / "pipeline2_no_peak_candidates.json",
        _boxes([short]),
    )
    generation_summary = _write_json(
        root / "generation.json",
        {
            "inventory": "/workspace/historical_inventory.json",
            "output_root": "/workspace/raw",
        },
    )
    filter_summary = _write_json(
        root / "filter.json",
        {
            "inventory": "/workspace/historical_inventory.json",
            "candidates_root": "/workspace/raw",
            "output_root": "/workspace/filtered",
        },
    )
    paths = {
        "root": root,
        "generation_summary": generation_summary,
        "filter_summary": filter_summary,
        "historical_final": historical_final,
        "scoring_root": scoring_root,
        "current_inventory": current_inventory,
        "stage_e": stage_e,
    }
    targets = [{"score": score, "page": page, "full_span": full_span, "short": short}]
    return paths, targets


def _report(paths: dict[str, Path], targets: list[dict[str, object]]) -> dict[str, object]:
    return build_report(
        main_repo_root=paths["root"],
        generation_summary_path=paths["generation_summary"],
        filter_summary_path=paths["filter_summary"],
        historical_final_root=paths["historical_final"],
        v12_scoring_root=paths["scoring_root"],
        current_mixed_inventory_path=paths["current_inventory"],
        current_stage_e_root=paths["stage_e"],
        targets=targets,
    )


def test_generation_and_filter_summaries_resolve_inventory_and_roots(tmp_path: Path) -> None:
    paths, _ = _fixture(tmp_path, existing=[], raw=[], filtered=[])

    resolved = resolve_summary_inputs(
        paths["generation_summary"], paths["filter_summary"], paths["root"]
    )

    assert resolved["inventory"] == paths["root"] / "historical_inventory.json"
    assert resolved["raw_root"] == paths["root"] / "raw"
    assert resolved["filtered_root"] == paths["root"] / "filtered"


def test_full_span_in_existing_input_is_classified_as_carried(tmp_path: Path) -> None:
    full_span = [10, 10, 14, 110]
    paths, targets = _fixture(tmp_path, existing=[full_span], raw=[full_span], filtered=[full_span])

    report = _report(paths, targets)

    assert report["targets"][0]["classification"] == "full_span_carried_from_existing_input"


def test_full_span_only_in_raw_is_classified_as_probe_generated(tmp_path: Path) -> None:
    full_span = [10, 10, 14, 110]
    paths, targets = _fixture(tmp_path, existing=[], raw=[full_span], filtered=[full_span])

    report = _report(paths, targets)

    assert report["targets"][0]["classification"] == "full_span_generated_by_issue36_probe"


def test_full_span_only_in_filter_output_is_reported_as_contradiction(tmp_path: Path) -> None:
    full_span = [10, 10, 14, 110]
    paths, targets = _fixture(tmp_path, existing=[], raw=[], filtered=[full_span])

    report = _report(paths, targets)

    assert report["targets"][0]["classification"] == "full_span_first_seen_in_filter_output"


def test_duplicate_inventory_records_raise_ambiguity(tmp_path: Path) -> None:
    inventory = _write_json(
        tmp_path / "inventory.json",
        {"records": [{"score": "Score", "page": "page_001"}] * 2},
    )

    with pytest.raises(InventoryRecordAmbiguousError):
        _find_inventory_record(inventory, "Score", "page_001")


def test_report_records_paths_hashes_and_bbox_provenance(tmp_path: Path) -> None:
    full_span = [10, 10, 14, 110]
    short = [10, 50, 14, 110]
    paths, targets = _fixture(
        tmp_path, existing=[full_span], raw=[full_span, short], filtered=[full_span, short]
    )

    report = _report(paths, targets)

    target = report["targets"][0]
    assert target["producer_inventory_record"]["inventory_path"].endswith(
        "historical_inventory.json"
    )
    assert target["producer_inventory_record"]["inventory_sha256"]
    assert target["producer_inventory_record"]["image_sha256"]
    assert target["producer_inventory_record"]["hybrid_predictions_sha256"]
    assert target["stages"]["v12_raw_candidates"]["path"].endswith(
        "raw/Score/page_001/pipeline2_no_peak_candidates.json"
    )
    assert target["bbox_provenance"] == {
        "full_span": "existing_input",
        "short": "probe_generated_or_other_raw_input",
    }


def test_filter_and_generation_summary_mismatch_is_rejected(tmp_path: Path) -> None:
    paths, _ = _fixture(tmp_path, existing=[], raw=[], filtered=[])
    payload = json.loads(paths["filter_summary"].read_text())
    payload["candidates_root"] = "/workspace/other_raw"
    _write_json(paths["filter_summary"], payload)

    with pytest.raises(ValueError, match="different raw roots"):
        resolve_summary_inputs(paths["generation_summary"], paths["filter_summary"], paths["root"])
