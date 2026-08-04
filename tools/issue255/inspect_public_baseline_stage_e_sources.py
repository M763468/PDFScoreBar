#!/usr/bin/env python3
"""Inspect retained fresh public-baseline artifacts for Stage E replay.

This is an offline restoration check. It does not run HOMR, SR, OMR-DLN,
consensus, dense generation, filtering, or CNN inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STAFF_PATTERNS = (
    "*_staff_mask.png",
    "*_proxy_debug_3_staff.png",
    "*_debug_3_staff.png",
    "*_debug_staff_resized_overlay.png",
)
CLEF_PATTERNS = (
    "*_clef_mask.png",
    "*_clefs_keys_mask.png",
    "*_proxy_debug_7_clefs_keys.png",
    "*_debug_7_clefs_keys.png",
    "*_proxy_debug_2_clefs.png",
    "*_debug_2_clefs.png",
)


def _resolve(value: str | Path, root: Path = ROOT) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return root / path.relative_to("/workspace")
    return path if path.is_absolute() else root / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.is_file(),
    }
    if path.is_file():
        result.update({"size_bytes": path.stat().st_size, "sha256": _sha256(path)})
    return result


def _artifact_path(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Run contract lacks artifacts")
    record = artifacts.get(name)
    if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
        raise ValueError(f"Run contract lacks artifact path: {name}")
    return _resolve(record["path"])


def _find_masks(page_dirs: list[Path], patterns: tuple[str, ...]) -> list[Path]:
    matches: set[Path] = set()
    for directory in page_dirs:
        if not directory.is_dir():
            continue
        for pattern in patterns:
            matches.update(path.resolve() for path in directory.glob(pattern) if path.is_file())
    return sorted(matches)


def _page_report(run: Mapping[str, Any]) -> dict[str, Any]:
    contract = run.get("contract")
    if not isinstance(contract, Mapping) or contract.get("status") != "completed":
        raise ValueError("Public-baseline run contract is incomplete")
    if contract.get("variant") != "public_baseline":
        raise ValueError("Expected public-baseline run contract")

    handoff = contract.get("baseline_profile_handoff")
    if not isinstance(handoff, Mapping) or handoff.get("status") != "completed":
        raise ValueError("Public baseline handoff is incomplete")
    if handoff.get("freshly_generated") is not True:
        raise ValueError("Public baseline was not freshly generated")
    if handoff.get("historical_artifact_used_as_runtime_input") is not False:
        raise ValueError("Historical runtime input is forbidden")

    baseline = _artifact_path(contract, "fresh_baseline")
    current_sr = _artifact_path(contract, "current_sr")
    current_omr = _artifact_path(contract, "current_omr")
    hybrid = _artifact_path(contract, "hybrid")
    image = _artifact_path(contract, "image")
    baseline_page = baseline.parent
    sr_page = current_sr.parent
    staff_masks = _find_masks([baseline_page, sr_page], STAFF_PATTERNS)
    clef_masks = _find_masks([baseline_page, sr_page], CLEF_PATTERNS)

    expected_baseline_hash = str(handoff.get("detection_sha256"))
    actual_baseline_hash = _sha256(baseline) if baseline.is_file() else None
    contract_payload = contract.get("detector_input_contract")
    fresh_contract_exact = isinstance(contract_payload, Mapping) and all(
        contract_payload.get(key) == value
        for key, value in {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
        }.items()
    )

    return {
        "label": run.get("label"),
        "score": run.get("score"),
        "page": run.get("page"),
        "run_id": run.get("run_id"),
        "public_profile": {
            "homr_commit": handoff.get("homr_commit"),
            "pdfscore_evaluator_commit": handoff.get("pdfscore_evaluator_commit"),
            "provenance_path": handoff.get("provenance_path"),
        },
        "baseline_preserved": actual_baseline_hash == expected_baseline_hash,
        "fresh_contract_exact": fresh_contract_exact,
        "artifacts": {
            "image": _artifact(image),
            "baseline": _artifact(baseline),
            "current_sr": _artifact(current_sr),
            "current_omr": _artifact(current_omr),
            "hybrid": _artifact(hybrid),
            "staff_masks": [_artifact(path) for path in staff_masks],
            "clef_masks": [_artifact(path) for path in clef_masks],
        },
        "stage_e_replay_inputs_complete": all(
            (
                baseline.is_file(),
                current_sr.is_file(),
                current_omr.is_file(),
                hybrid.is_file(),
                bool(staff_masks),
                bool(clef_masks),
            )
        ),
    }


def build_report(batch_path: Path) -> dict[str, Any]:
    payload = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError("Public-baseline batch is incomplete")
    if payload.get("variant") != "public_baseline":
        raise ValueError("Expected a public-baseline batch")
    runs = payload.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("Expected exactly two focused public-baseline runs")

    pages = {
        str(run.get("label")): _page_report(run)
        for run in runs
        if isinstance(run, Mapping)
    }
    if len(pages) != 2:
        raise ValueError("Public-baseline batch lacks two valid runs")

    all_complete = all(page["stage_e_replay_inputs_complete"] for page in pages.values())
    return {
        "schema_version": "issue255.public_baseline_stage_e_sources.v1",
        "status": "completed",
        "analysis_only": True,
        "restoration_scope_only": True,
        "source_batch": str(batch_path.resolve()),
        "historical_detector_candidate_runtime_inputs": [],
        "pages": pages,
        "gates": {
            "all_public_baselines_preserved": all(
                page["baseline_preserved"] for page in pages.values()
            ),
            "all_fresh_contracts_exact": all(
                page["fresh_contract_exact"] for page in pages.values()
            ),
            "all_stage_e_replay_inputs_complete": all_complete,
            "next_gpu_run_required": not all_complete,
        },
        "new_recovery_direction_introduced": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-batch", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args.public_batch.resolve())
    output = args.output or args.public_batch.resolve().parent / (
        "stage_e_public_baseline_source_inventory.json"
    )
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(output)}))


if __name__ == "__main__":
    main()
