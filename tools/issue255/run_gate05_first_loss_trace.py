#!/usr/bin/env python3
"""Replay all Issue #255 gate05 targets through the production probe stages."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH = (
    ROOT
    / "logs/issue255_focused_fresh/issue255_focused_fresh_batch_issue255_gate_05.json"
)
DEFAULT_TARGETS = ROOT / "tools/issue255/gate05_targets.json"
DEFAULT_OUTPUT = ROOT / "logs/issue255_first_loss/issue255_gate_05_trace"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_record_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT / path.relative_to("/workspace")
    return path if path.is_absolute() else ROOT / path


def _artifact_path(contract: Mapping[str, Any], name: str) -> Path:
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Run contract lacks artifacts")
    record = artifacts.get(name)
    if not isinstance(record, Mapping) or record.get("exists") is not True:
        raise ValueError(f"Run contract lacks completed artifact: {name}")
    path = _resolve_record_path(str(record["path"]))
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _run_trace(
    *,
    run: Mapping[str, Any],
    page_spec: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    contract = run.get("contract")
    if not isinstance(contract, Mapping) or contract.get("status") != "completed":
        raise ValueError(f"Incomplete gate05 contract: {run.get('label')}")
    fresh = contract.get("detector_input_contract")
    if not isinstance(fresh, Mapping) or any(
        fresh.get(key) != value
        for key, value in {
            "mode": "fresh_upstream",
            "fresh_upstream_authoritative": True,
            "override_keys": [],
        }.items()
    ):
        raise ValueError(f"Non-authoritative detector contract: {fresh}")

    page_root = output_root / str(run["label"])
    page_root.mkdir(parents=True)
    metadata_path = page_root / "target_metadata.json"
    _write_json(metadata_path, {"targets": page_spec["targets"]})

    image_record = contract["artifacts"]["image"]
    coordinate = contract.get("coordinate_space")
    if not isinstance(coordinate, Mapping):
        raise ValueError("Run contract lacks coordinate-space metadata")
    input_scale = float(coordinate.get("sr_scale", 1))
    accepted_barlines = _resolve_record_path(str(page_spec["accepted_barlines"]))
    if not accepted_barlines.is_file():
        raise FileNotFoundError(accepted_barlines)

    command = [
        sys.executable,
        str(ROOT / "tools/issue255/run_focused_detector_inventory.py"),
        "--input-contract",
        str(_artifact_path(contract, "input_contract")),
        "--image",
        str(_artifact_path(contract, "image")),
        "--probe-image",
        str(_artifact_path(contract, "probe_image")),
        "--input-image-scale",
        str(input_scale),
        "--expected-image-sha256",
        str(image_record["sha256"]),
        "--fresh-baseline",
        str(_artifact_path(contract, "fresh_baseline")),
        "--current-sr",
        str(_artifact_path(contract, "current_sr")),
        "--current-omr",
        str(_artifact_path(contract, "current_omr")),
        "--hybrid",
        str(_artifact_path(contract, "hybrid")),
        "--staff-mask",
        str(_artifact_path(contract, "staff_mask")),
        "--allow-zero-clef-mask",
        "--cnn-scored",
        str(_artifact_path(contract, "cnn_scored")),
        "--cnn-accepted",
        str(_artifact_path(contract, "cnn_accepted")),
        "--final-barlines",
        str(_artifact_path(contract, "final_barlines")),
        "--accepted-barlines",
        str(accepted_barlines),
        "--target-metadata",
        str(metadata_path),
        "--score",
        str(page_spec["score"]),
        "--page",
        str(page_spec["page"]),
        "--output-root",
        str(page_root / "inventory"),
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    (page_root / "trace.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (page_root / "trace.stderr.txt").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(
            f"Focused first-loss trace failed for {run['label']}: "
            f"exit={result.returncode}; stderr={result.stderr[-2000:]}"
        )
    report_path = page_root / "inventory/focused_detector_inventory.json"
    report = _load_json(report_path)
    if not isinstance(report, Mapping) or report.get("status") != "completed":
        raise ValueError(f"Invalid focused inventory: {report_path}")
    return dict(report)


def build_report(*, batch: Path, targets: Path, output_root: Path) -> dict[str, Any]:
    batch = batch.resolve()
    targets = targets.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(output_root)

    batch_payload = _load_json(batch)
    target_payload = _load_json(targets)
    if not isinstance(batch_payload, Mapping) or batch_payload.get("status") != "completed":
        raise ValueError("gate05 batch must be completed")
    if not isinstance(target_payload, Mapping):
        raise ValueError("target manifest must be an object")
    pages = target_payload.get("pages")
    runs = batch_payload.get("runs")
    if not isinstance(pages, Mapping) or not isinstance(runs, list):
        raise ValueError("invalid batch or target manifest")

    output_root.mkdir(parents=True)
    inventories = []
    try:
        runs_by_label = {
            str(run["label"]): run for run in runs if isinstance(run, Mapping) and run.get("label")
        }
        for label, page_spec in pages.items():
            if label not in runs_by_label or not isinstance(page_spec, Mapping):
                raise ValueError(f"Missing run or page specification: {label}")
            inventories.append(
                _run_trace(
                    run=runs_by_label[label],
                    page_spec=page_spec,
                    output_root=output_root,
                )
            )

        rows = [item for report in inventories for item in report.get("inventory", [])]
        boundaries = Counter(
            str(item.get("first_loss_boundary")) for item in rows if isinstance(item, Mapping)
        )
        summary = {
            "schema_version": "issue255.gate05_first_loss_trace.v1",
            "status": "completed",
            "gate_commit": batch_payload.get("expected_commit"),
            "analysis_commit": _git_head(),
            "detector_input_contract": {
                "mode": "fresh_upstream",
                "fresh_upstream_authoritative": True,
                "override_keys": [],
            },
            "target_count": len(rows),
            "first_loss_counts": dict(sorted(boundaries.items())),
            "targets": rows,
        }
        _write_json(output_root / "issue255_gate05_first_loss_summary.json", summary)
        archive_path = output_root.with_suffix(".tar.gz")
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(output_root, arcname=output_root.name)
        return {**summary, "archive": str(archive_path), "archive_size_bytes": archive_path.stat().st_size}
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def _git_head() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return result.stdout.strip() or None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        report = build_report(batch=args.batch, targets=args.targets, output_root=args.output_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
