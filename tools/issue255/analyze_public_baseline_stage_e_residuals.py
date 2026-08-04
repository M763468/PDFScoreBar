#!/usr/bin/env python3
"""Analyze retained public-baseline Stage E replay residuals offline.

This adapter reuses the existing focused Stage E residual analyzer. It does not
run HOMR, SR HOMR, OMR-DLN, consensus, dense generation, filtering, Issue53
reconstruction, or CNN inference.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.issue252.probe_boundary import write_json
from tools.issue255.analyze_stage_e_reconstruction_residuals import (
    build_report as _build_focused_report,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_ROOT = ROOT / "logs/issue255_stage_e_public_baseline/issue255_public_stage_e_01"
PUBLIC_REPORT_NAME = "public_baseline_stage_e_reconstruction_report.json"
COMPAT_REPORT_NAME = "focused_stage_e_reconstruction_report.json"
OUTPUT_NAME = "public_baseline_stage_e_residuals.json"
FRESH_CONTRACT_REQUIRED = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _fresh_contract_matches(value: Any) -> bool:
    return isinstance(value, Mapping) and all(
        value.get(key) == expected for key, expected in FRESH_CONTRACT_REQUIRED.items()
    )


def _compat_page(page: Mapping[str, Any], label: str) -> dict[str, Any]:
    artifacts = page.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError(f"Public Stage E page lacks artifacts: {label}")
    public_final = artifacts.get("public_pipeline_final")
    if not isinstance(public_final, Mapping):
        raise ValueError(f"Public Stage E page lacks public_pipeline_final: {label}")
    result = dict(page)
    compat_artifacts = dict(artifacts)
    compat_artifacts["control_final"] = dict(public_final)
    result["artifacts"] = compat_artifacts
    return result


def build_report(run_root: Path) -> dict[str, Any]:
    run_root = run_root.resolve()
    public_path = run_root / PUBLIC_REPORT_NAME
    public = _load(public_path)
    if not isinstance(public, Mapping) or public.get("status") != "completed":
        raise ValueError(f"Public Stage E replay is not completed: {public_path}")
    raw_pages = public.get("pages")
    if not isinstance(raw_pages, Mapping):
        raise ValueError("Public Stage E report lacks pages")

    compat_pages = {
        str(label): _compat_page(page, str(label))
        for label, page in raw_pages.items()
        if isinstance(page, Mapping)
    }
    if len(compat_pages) != len(raw_pages):
        raise ValueError("Public Stage E report contains an invalid page row")

    compat = {
        "status": "completed",
        "repository": public.get("repository", {}),
        "gates": public.get("gates", {}),
        "pages": compat_pages,
    }
    with tempfile.TemporaryDirectory(prefix="issue255_public_stage_e_") as temp:
        temp_root = Path(temp)
        (temp_root / COMPAT_REPORT_NAME).write_text(
            json.dumps(compat, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report = _build_focused_report(temp_root)

    contract_rows = []
    for label, page in raw_pages.items():
        source = page.get("source_contract") if isinstance(page, Mapping) else None
        contract = source.get("fresh_contract") if isinstance(source, Mapping) else None
        contract_rows.append(
            {
                "label": str(label),
                "required_fields_match": _fresh_contract_matches(contract),
                "contract": contract,
            }
        )
    required_match = all(row["required_fields_match"] for row in contract_rows)
    original_gate = public.get("gates", {}).get("fresh_contract_exact")

    report.update(
        {
            "schema_version": "issue255.public_baseline_stage_e_residuals.v1",
            "source_run": str(run_root),
            "source_report": str(public_path),
            "control_role": "public_pipeline_final",
            "fresh_contract_gate": {
                "original_report_value": original_gate,
                "required_fields": FRESH_CONTRACT_REQUIRED,
                "required_fields_match": required_match,
                "pages": contract_rows,
                "interpretation": (
                    "The replay runner validated the required fresh-contract "
                    "fields before execution. Its original summary gate compared "
                    "the full metadata-rich contract to a three-key dictionary."
                ),
            },
            "public_baselines_preserved": public.get("gates", {}).get("public_baselines_preserved"),
            "upstream_gpu_rerun_performed": public.get("gates", {}).get(
                "upstream_gpu_rerun_performed"
            ),
            "historical_runtime_artifact_dependency_absent": public.get("gates", {}).get(
                "historical_runtime_artifact_dependency_absent"
            ),
            "next_gpu_run_required": False,
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(args.run_root)
    output = args.output or args.run_root / OUTPUT_NAME
    write_json(output.resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(output.resolve()),
                "combined": report["combined"],
                "fresh_contract_required_fields_match": report["fresh_contract_gate"][
                    "required_fields_match"
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
