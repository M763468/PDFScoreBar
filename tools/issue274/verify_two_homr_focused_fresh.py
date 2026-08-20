#!/usr/bin/env python3
"""Verify an existing Issue #274 fresh focused run without rerunning inference."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def command_strings(manifest: Mapping[str, Any]) -> list[str]:
    commands = manifest.get("commands")
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
        return []
    result: list[str] = []
    for entry in commands:
        if not isinstance(entry, Mapping):
            continue
        cmd = entry.get("cmd")
        if isinstance(cmd, Sequence) and not isinstance(cmd, (str, bytes)):
            result.append(" ".join(str(part) for part in cmd))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-pages", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.run_root.resolve()
    run_id = args.run_id
    manifest_path = root / "runs" / run_id / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)

    manifest_raw = load_json(manifest_path)
    if not isinstance(manifest_raw, Mapping):
        raise ValueError(f"Manifest must be a mapping: {manifest_path}")
    manifest = manifest_raw

    config = as_mapping(manifest.get("config"))
    detection = as_mapping(config.get("detection"))
    hybrid_root_value = detection.get("hybrid_output_root")
    if not hybrid_root_value:
        raise ValueError("Manifest lacks config.detection.hybrid_output_root")
    hybrid = Path(str(hybrid_root_value)).resolve() / run_id

    pages = manifest.get("pages")
    manifest_pages = (
        list(pages) if isinstance(pages, Sequence) and not isinstance(pages, (str, bytes)) else []
    )
    expected_pages = args.expected_pages if args.expected_pages is not None else len(manifest_pages)

    source_results = sorted((hybrid / "source_page_workers" / "inputs").glob("*/result.json"))
    support_results = sorted((hybrid / "current_support" / "inputs").glob("*/result.json"))

    source_pages: list[dict[str, Any]] = []
    source_contract_ok = True
    for path in source_results:
        payload_raw = load_json(path)
        payload = as_mapping(payload_raw)
        detection_path = Path(str(payload.get("current_sr_detection", "")))
        row = {
            "result": str(path),
            "status": payload.get("status"),
            "homr_neural_inference_count": payload.get("homr_neural_inference_count"),
            "x4_homr_neural_inference_count": payload.get("x4_homr_neural_inference_count"),
            "x4_detector_support_owner": payload.get("x4_detector_support_owner"),
            "historical_detector_artifact_runtime_input": payload.get(
                "historical_detector_artifact_runtime_input"
            ),
            "current_sr_detection": str(detection_path),
            "current_sr_detection_exists": detection_path.is_file(),
        }
        row["ok"] = (
            row["status"] == "completed"
            and row["homr_neural_inference_count"] == 2
            and row["x4_homr_neural_inference_count"] == 1
            and row["x4_detector_support_owner"] == "current_x4_support"
            and row["historical_detector_artifact_runtime_input"] is False
            and row["current_sr_detection_exists"]
        )
        source_contract_ok = source_contract_ok and bool(row["ok"])
        source_pages.append(row)

    support_pages: list[dict[str, Any]] = []
    support_contract_ok = True
    for path in support_results:
        payload_raw = load_json(path)
        payload = as_mapping(payload_raw)
        detection_path = Path(str(payload.get("current_sr_detection", "")))
        row = {
            "result": str(path),
            "status": payload.get("status"),
            "current_homr_executed": payload.get("current_homr_executed"),
            "historical_detector_artifact_runtime_input": payload.get(
                "historical_detector_artifact_runtime_input"
            ),
            "current_sr_detection": str(detection_path),
            "current_sr_detection_exists": detection_path.is_file(),
        }
        row["ok"] = (
            row["status"] == "completed"
            and row["current_homr_executed"] is True
            and row["historical_detector_artifact_runtime_input"] is False
            and row["current_sr_detection_exists"]
        )
        support_contract_ok = support_contract_ok and bool(row["ok"])
        support_pages.append(row)

    commands = command_strings(manifest)
    source_worker_calls = sum(
        "src.pipeline.detection.verified_source_page_worker" in command for command in commands
    )
    pinned_profile_calls = sum("homr_profile_compat.py" in command for command in commands)
    current_support_calls = sum(
        "src.pipeline.detection.current_support_worker" in command for command in commands
    )
    command_contract_ok = (
        source_worker_calls == expected_pages
        and pinned_profile_calls == expected_pages
        and current_support_calls == expected_pages
    )

    downstream_pages: list[dict[str, Any]] = []
    downstream_contract_ok = True
    for page in manifest_pages:
        page_mapping = as_mapping(page)
        connector = as_mapping(page_mapping.get("connector_evidence"))
        mmr = as_mapping(page_mapping.get("mmr_support"))
        row = {
            "image_path": page_mapping.get("image_path"),
            "connector_source": connector.get("source"),
            "mmr_source": mmr.get("source"),
            "original_image_homr": mmr.get("original_image_homr"),
            "second_numbering_rebuild": mmr.get("second_numbering_rebuild"),
            "staff_slot_count": mmr.get("staff_slot_count"),
            "mapped_count": mmr.get("mapped_count"),
            "fallback_count": mmr.get("fallback_count"),
            "union_count": mmr.get("union_count"),
        }
        row["ok"] = (
            row["connector_source"] == "proxy_symbol_layers"
            and row["mmr_source"] == "current_x4_support"
            and row["original_image_homr"] is False
            and row["second_numbering_rebuild"] is False
            and row["mapped_count"] == row["staff_slot_count"]
            and row["fallback_count"] == 0
        )
        downstream_contract_ok = downstream_contract_ok and bool(row["ok"])
        downstream_pages.append(row)

    summary: dict[str, Any] = {
        "schema_version": "issue274.two_homr_focused_fresh_gate.v3",
        "run_id": run_id,
        "run_root": str(root),
        "hybrid_root": str(hybrid),
        "expected_page_count": expected_pages,
        "source_page_result_count": len(source_results),
        "current_support_result_count": len(support_results),
        "manifest_page_count": len(manifest_pages),
        "command_counts": {
            "source_page_worker": source_worker_calls,
            "pinned_homr_profile": pinned_profile_calls,
            "current_support_worker": current_support_calls,
        },
        "source_contract_ok": source_contract_ok and len(source_results) == expected_pages,
        "support_contract_ok": support_contract_ok and len(support_results) == expected_pages,
        "command_contract_ok": command_contract_ok,
        "downstream_contract_ok": downstream_contract_ok and len(manifest_pages) == expected_pages,
        "source_pages": source_pages,
        "support_pages": support_pages,
        "downstream_pages": downstream_pages,
    }
    summary["gate_pass"] = all(
        summary[key]
        for key in (
            "source_contract_ok",
            "support_contract_ok",
            "command_contract_ok",
            "downstream_contract_ok",
        )
    )

    output = args.output or (root / "two_homr_focused_fresh_summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote: {output}")
    return 0 if summary["gate_pass"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
