#!/usr/bin/env python3
"""Focused Issue #264 Phase B acceptance using retained detector artifacts only."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from src.measure_numbering.pipeline import MeasureNumberingPipeline
from src.measure_numbering.types import Score
from src.pipeline.mmr_geometry_handoff import build_mmr_page_context
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.utils.images import load_image
from src.pipeline.utils.io import load_json, score_to_dict, write_json

TARGET_STEM = "Va_Prokofiev_Symphony1_page_001"
EXPECTED_STAFF_SHA256 = (
    "7fa9d8dd4709ed28031e3b20c68eb97abb42f3f46ef5d8abe4835180aa40e660"
)
EXPECTED_PHYSICAL = [5, 5, 5, 7, 7, 8, 5, 7, 10, 8, 5, 6]
EXPECTED_OVERRIDES = [
    (7, 3, 5),
    (7, 6, 3),
    (8, 0, 2),
    (8, 2, 2),
    (8, 4, 4),
]
EXPECTED_ROW_STARTS = [1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_manifest_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    for entry in manifest.get("pages", []):
        if not isinstance(entry, dict):
            continue
        image = Path(str(entry.get("image_path", "")))
        page_id = str(entry.get("page_id", ""))
        if image.stem == TARGET_STEM or page_id == TARGET_STEM:
            return entry
        if image.stem == "page_001" and image.parent.name == "Va_Prokofiev_Symphony1":
            return entry
    raise ValueError(f"Manifest does not contain {TARGET_STEM}")


def build_numbering(
    pipeline: MeasureNumberingPipeline,
    image_path: Path,
    barlines_path: Path,
    staff_mask: Path,
    overrides: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], Score]:
    image = load_image(image_path)
    height, width = image.shape[:2]
    page = pipeline.process_page(
        normalize_barlines(load_json(barlines_path)),
        staff_mask,
        (width, height),
        page_number=1,
        assume_one_staff_per_system=False,
        image=image,
    )
    score = Score()
    score.pages.append(page)
    pipeline.numberer.number_score(score, start_number=1, overrides=overrides)
    return score_to_dict(score), score


def physical_counts(payload: dict[str, Any]) -> list[int]:
    return [len(system["measures"]) for system in payload["pages"][0]["systems"]]


def override_triples(payload: dict[str, Any]) -> list[tuple[int, int, int]]:
    return sorted(
        (
            int(item["system"]),
            int(item["measure"]),
            int(item.get("skip", 0)),
        )
        for item in payload.get("measure_overrides", [])
        if isinstance(item, dict)
    )


def run(detector_manifest: Path, run_dir: Path) -> Path:
    manifest = load_json(detector_manifest)
    entry = target_manifest_entry(manifest)
    image_path = Path(str(entry["image_path"]))
    barlines_path = Path(str(entry["barlines_json"]))
    staff_mask = Path(str(entry["staff_mask"]))
    for path in (image_path, barlines_path, staff_mask):
        if not path.is_file():
            raise FileNotFoundError(path)

    intermediate = run_dir / "intermediate" / TARGET_STEM
    outputs = run_dir / "outputs" / TARGET_STEM
    intermediate.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)

    config = {
        "steps": {"mmr_overrides": True},
        "detection": {"detector_route": "dense_full_pipeline"},
        "mmr": {
            "model_path": "tools/mmr_training/models/mmr_classifier_best.pth",
            "enable_rotation_tta": False,
        },
        "numbering": {"force_single_system": False},
    }
    orchestrator = PipelineOrchestrator(config, run_dir.name, run_dir)
    pipeline = MeasureNumberingPipeline()

    base_payload, _ = build_numbering(
        pipeline,
        image_path,
        barlines_path,
        staff_mask,
    )
    numbering_base = intermediate / "numbering_base.json"
    write_json(numbering_base, base_payload)
    resolved = {
        "page_id": TARGET_STEM,
        "page_run": TARGET_STEM,
        "barlines_json": str(barlines_path),
        "staff_mask": str(staff_mask),
    }
    page_ctx = {
        TARGET_STEM: {
            "index": 1,
            "image_path": image_path,
            "resolved": resolved,
            "intermediate_dir": intermediate,
            "outputs_dir": outputs,
            "barlines_path": barlines_path,
            "numbering_base": numbering_base,
        }
    }

    mmr_ctx = build_mmr_page_context(orchestrator, [TARGET_STEM], set(), page_ctx)
    orchestrator.run_mmr_batch_detection([TARGET_STEM], set(), mmr_ctx)
    overrides_payload = load_json(intermediate / "overrides_mmr.json")
    overrides = overrides_payload.get("measure_overrides")
    if not isinstance(overrides, list):
        raise ValueError("MMR output lacks measure_overrides")

    _, final_score = build_numbering(
        pipeline,
        image_path,
        barlines_path,
        staff_mask,
        overrides,
    )
    mmr_staff_mask = Path(page_ctx[TARGET_STEM]["mmr_staff_mask"])
    mmr_payload = load_json(Path(mmr_ctx[TARGET_STEM]["numbering_base"]))
    triples = override_triples(overrides_payload)
    row_starts = [
        system.measures[0].number
        for system in final_score.pages[0].systems
        if system.measures
    ]
    staff_sha = sha256(mmr_staff_mask)
    base_physical = physical_counts(base_payload)
    mmr_physical = physical_counts(mmr_payload)

    checks = {
        "staff_sha_exact": staff_sha == EXPECTED_STAFF_SHA256,
        "base_physical_exact": base_physical == EXPECTED_PHYSICAL,
        "mmr_layout_exact": mmr_physical == EXPECTED_PHYSICAL,
        "five_overrides_exact": triples == EXPECTED_OVERRIDES,
        "row_starts_exact": row_starts == EXPECTED_ROW_STARTS,
        "historical_runtime_input_absent": resolved["mmr_staff_geometry"][
            "historical_detector_artifact_runtime_input"
        ]
        is False,
    }
    report = {
        "status": "passed" if all(checks.values()) else "failed",
        "detector_reexecuted": False,
        "detector_manifest": str(detector_manifest),
        "mmr_staff_sha256": staff_sha,
        "physical": base_physical,
        "mmr_physical": mmr_physical,
        "overrides": [list(value) for value in triples],
        "row_starts": row_starts,
        "mmr_staff_geometry": resolved.get("mmr_staff_geometry"),
        "checks": checks,
    }
    report_path = run_dir / "phase_b_page001_acceptance.json"
    write_json(report_path, report)
    print(f"status: {report['status']}")
    print(f"staff_sha: {staff_sha}")
    print(f"physical: {base_physical}")
    print(f"overrides: {[list(value) for value in triples]}")
    print(f"row_starts: {row_starts}")
    print(f"report: {report_path}")
    return report_path
