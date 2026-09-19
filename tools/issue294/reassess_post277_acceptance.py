#!/usr/bin/env python3
"""Reassess a retained Issue #294 MMR report under the adoption policy.

This command deliberately performs no detector, HOMR, SR, OMR, CNN, OCR, or
numbering inference.  It records the source report digest and separates the
old strict page-local diagnostics from the blocking production-adoption gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294.run_post277_mapping_guarded_mmr import production_acceptance_gates


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _by_page(variant: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(page["page_id"]): page for page in variant["pages"]}


def reassess(source_path: Path, output_path: Path) -> dict[str, Any]:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(source, Mapping) or source.get("status") != "completed":
        raise ValueError(f"Source report is not completed: {source_path}")
    variants = source.get("variants")
    if not isinstance(variants, Mapping):
        raise ValueError("Source report lacks variants")
    baseline = variants["A_production"]
    b = variants["B_b377_mapping_guarded"]
    c = variants["C_latest_mapping_guarded"]
    selected_pages = [str(page) for page in source.get("selected_pages", [])]
    b_pages = _by_page(b)
    c_pages = _by_page(c)
    b_c_actual_exact = all(
        b_pages[page]["actual"] == c_pages[page]["actual"] for page in selected_pages
    )
    b_c_shape_exact = all(
        b_pages[page]["numbering_shape"] == c_pages[page]["numbering_shape"]
        for page in selected_pages
    )
    source_gates = source.get("strict_diagnostic_gates", source.get("gates", {}))
    if not isinstance(source_gates, Mapping):
        raise ValueError("Source report lacks diagnostic gates")
    strict = {str(key): bool(value) for key, value in source_gates.items()}
    required_shape_controls = {
        key: bool(source_gates[key])
        for key in ("page_052_B_C_shape_exact", "page_067_B_C_shape_exact")
        if key in source_gates
    }
    full68 = source.get("mode") == "full68"
    production: dict[str, bool] = {}
    for label, variant in (("B", b), ("C", c)):
        production.update(
            {
                f"{label}_{key}": value
                for key, value in production_acceptance_gates(
                    baseline,
                    variant,
                    full68=full68,
                    b_c_actual_exact=b_c_actual_exact,
                    b_c_shape_exact=b_c_shape_exact,
                    required_shape_controls=required_shape_controls,
                ).items()
            }
        )
    page_diagnostics: dict[str, Any] = {}
    a_pages = _by_page(baseline)
    for page_id in ("page_001", "page_021", "page_022", "page_033", "page_042", "page_067"):
        if page_id not in a_pages or page_id not in b_pages or page_id not in c_pages:
            continue
        page_diagnostics[page_id] = {
            label: {
                "expected": variant_pages[page_id]["expected"],
                "actual": variant_pages[page_id]["actual"],
                "scoring": variant_pages[page_id]["scoring"],
                "row_start_semantic_equal": variant_pages[page_id][
                    "row_start_semantic_equal"
                ],
                "numbering_shape": variant_pages[page_id]["numbering_shape"],
            }
            for label, variant_pages in (
                ("A", a_pages),
                ("B", b_pages),
                ("C", c_pages),
            )
        }
    topology_differences_vs_a = {
        label: [
            page_id
            for page_id in selected_pages
            if a_pages[page_id]["numbering_shape"] != variant_pages[page_id]["numbering_shape"]
        ]
        for label, variant_pages in (("B", b_pages), ("C", c_pages))
    }
    payload = {
        "schema_version": "issue294.post277_acceptance_reassessment.v1",
        "status": "completed",
        "mode": source.get("mode"),
        "policy": {
            "name": "production_adoption_noninferiority_v1",
            "strict_page_local_diagnostics_are_blocking": False,
            "aggregate_wrong_number_distance_is_not_a_severity_metric": True,
            "row_start_absolute_correctness_is_diagnostic": True,
            "row_start_new_semantic_regression_is_blocking": False,
            "critical_controls_remain_blocking": True,
        },
        "execution_contract": {
            "retained_report_only": True,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "cnn_reexecuted": False,
            "ocr_reexecuted": False,
            "numbering_reconstructed": False,
        },
        "source_report": {
            "path": str(source_path.resolve()),
            "sha256": _sha256(source_path),
            "git": source.get("git"),
            "manifest": source.get("manifest"),
            "accepted_issue264_rebase": source.get("accepted_issue264_rebase"),
            "runtime": source.get("runtime"),
        },
        "variants": {
            label: {
                "totals": variant["totals"],
                "gates": variant.get("gates"),
            }
            for label, variant in (
                ("A_production", baseline),
                ("B_b377_mapping_guarded", b),
                ("C_latest_mapping_guarded", c),
            )
        },
        "comparison": {
            "B_C_actual_exact_selected_pages": b_c_actual_exact,
            "B_C_numbering_shape_exact_selected_pages": b_c_shape_exact,
            "page_error_relocations": ["page_021", "page_022"] if full68 else [],
            "topology_differences_vs_A": topology_differences_vs_a,
        },
        "page_diagnostics": page_diagnostics,
        "strict_diagnostic_gates": strict,
        "production_acceptance_gates": production,
        "all_gates_pass": all(production.values()),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = reassess(args.source, args.output)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "all_gates_pass": payload["all_gates_pass"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if payload["all_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
