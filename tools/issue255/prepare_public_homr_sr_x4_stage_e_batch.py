#!/usr/bin/env python3
"""Prepare an Issue #255 Stage E source batch from fresh public-HOMR SR x4 hybrids.

The source public-baseline contracts are preserved except for ``artifacts.hybrid``,
which is replaced by the fresh recomputed hybrid produced by
``run_public_homr_on_sr_x4.py``. Historical SR/hybrid artifacts referenced by the
analysis report are never copied into this derived runtime batch.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = (
    ROOT
    / "logs/issue255_public_homr_on_sr_x4/issue255_public_homr_on_sr_x4_01"
    / "public_homr_on_sr_x4_report.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "logs/issue255_public_homr_on_sr_x4/issue255_public_homr_on_sr_x4_01"
    / "stage_e_public_batch.json"
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_artifact(value: str | Path) -> Path:
    path = Path(value)
    if path.exists():
        return path.resolve()
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return (ROOT / path.relative_to("/workspace")).resolve()
    parts = path.parts
    indices = [index for index, part in enumerate(parts) if part == ROOT.name]
    if indices:
        return (ROOT / Path(*parts[indices[-1] + 1 :])).resolve()
    for marker in ("logs", "data", "configs", "tools", "external"):
        if marker in parts:
            index = parts.index(marker)
            return (ROOT / Path(*parts[index:])).resolve()
    return path.resolve()


def _artifact_record(path: Path, source: Any) -> dict[str, Any]:
    result = dict(source) if isinstance(source, Mapping) else {}
    result["path"] = str(path.resolve())
    result["sha256"] = _sha256(path)
    result["size_bytes"] = path.stat().st_size
    return result


def build_batch(report_path: Path) -> dict[str, Any]:
    report_path = report_path.resolve()
    report = _load(report_path)
    if not isinstance(report, Mapping) or report.get("status") != "completed":
        raise ValueError("Public HOMR on SR x4 report is incomplete")
    if report.get("historical_artifact_used_as_runtime_input") is not False:
        raise ValueError("Source experiment used historical runtime artifacts")
    summary = report.get("summary")
    if (
        not isinstance(summary, Mapping)
        or summary.get("all_recomputed_hybrids_exact_historical") is not True
    ):
        raise ValueError("Fresh recomputed hybrids are not exact historical matches")

    source_batch_value = report.get("source_public_batch")
    if not isinstance(source_batch_value, str):
        raise ValueError("Source experiment lacks public-baseline batch path")
    source_batch_path = _resolve_repo_artifact(source_batch_value)
    source_batch = _load(source_batch_path)
    if (
        not isinstance(source_batch, Mapping)
        or source_batch.get("status") != "completed"
    ):
        raise ValueError("Source public-baseline batch is incomplete")
    if source_batch.get("variant") != "public_baseline":
        raise ValueError("Expected public-baseline source batch")

    pages = report.get("pages")
    source_runs = source_batch.get("runs")
    if not isinstance(pages, Mapping) or not isinstance(source_runs, list):
        raise ValueError("Source reports lack pages or runs")

    hybrids: dict[str, Path] = {}
    for label, page in pages.items():
        value = page.get("recomputed_hybrid") if isinstance(page, Mapping) else None
        if not isinstance(value, str):
            raise ValueError(f"Fresh recomputed hybrid path missing: {label}")
        path = _resolve_repo_artifact(value)
        if not path.is_file():
            raise FileNotFoundError(path)
        hybrids[str(label)] = path

    derived_runs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_run in source_runs:
        if not isinstance(source_run, Mapping):
            raise ValueError("Source batch contains an invalid run")
        label = str(source_run.get("label"))
        hybrid = hybrids.get(label)
        if hybrid is None:
            raise ValueError(f"No restored hybrid for source run: {label}")
        derived = copy.deepcopy(dict(source_run))
        contract = derived.get("contract")
        if not isinstance(contract, dict):
            raise ValueError(f"Source run lacks mutable contract: {label}")
        artifacts = contract.get("artifacts")
        if not isinstance(artifacts, dict):
            raise ValueError(f"Source run lacks artifact mapping: {label}")
        artifacts["hybrid"] = _artifact_record(hybrid, artifacts.get("hybrid"))
        contract["issue255_stage_e_hybrid_override"] = {
            "kind": "fresh_public_homr_on_sr_x4_recomputed_hybrid",
            "path": str(hybrid.resolve()),
            "historical_artifact_used_as_runtime_input": False,
        }
        derived_runs.append(derived)
        seen.add(label)

    missing = sorted(set(hybrids) - seen)
    if missing:
        raise ValueError(f"Restored hybrids lack source public runs: {missing}")

    batch = copy.deepcopy(dict(source_batch))
    batch["schema_version"] = "issue255.public_homr_sr_x4_stage_e_batch.v1"
    batch["runs"] = derived_runs
    batch["derived_for_stage_e_reconstruction"] = True
    batch["source_public_batch"] = str(source_batch_path.resolve())
    batch["source_public_homr_sr_x4_report"] = str(report_path)
    batch["historical_artifact_used_as_runtime_input"] = False
    batch["hybrid_override_labels"] = sorted(hybrids)
    return batch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    batch = build_batch(args.report)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(batch, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(output),
                "hybrid_override_labels": batch["hybrid_override_labels"],
                "historical_artifact_used_as_runtime_input": False,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
