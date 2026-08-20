#!/usr/bin/env python3
"""Issue #274 pinned/current primary-HOMR boundary comparison, API-compat v2.

The pinned Stage-E PDFScore evaluator predates `DEFAULT_TUNING`.  Its production
entrypoint built the primary-HOMR tuning dictionary directly from argparse
values.  The stage_e_verified profile supplies no barline/generator override,
so this wrapper injects those historical CLI defaults before delegating to the
v1 comparison harness.

The failed v1 output is intentionally retained.  A normal v2 master run writes
to `pinned_current_primary_boundary_02` by default.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from tools.issue274 import compare_pinned_current_primary_boundary as v1

# Exact primary-stage defaults constructed by bd6ae56.../homr_evaluator.py::main
# when stage_e_verified invokes the evaluator without barline/generator tuning
# flags.  These are the only keys consumed before detect_staff() in that
# historical primary path.
HISTORICAL_PRIMARY_DEFAULT_TUNING: dict[str, Any] = {
    "barline_min_height_factor": 1.0,
    "barline_max_width_factor": 1.0,
    "barline_staff_overlap_min": 0.0,
    "barline_edge_margin_x": 0,
    "barline_edge_margin_y": 0,
    "gen_vertical_run": False,
    "gen_vertical_run_weak": False,
    "gen_barline_cc_relaxed": False,
    "gen_barline_cc_dilated": False,
    "gen_sobel_vertical": False,
    "gen_sobel_vertical_weak": False,
    "gen_column_sum_staff": False,
    "gen_column_sum_weak": False,
    "gen_column_sum_no_staff": False,
    "gen_hough_vertical": False,
    "gen_hough_vertical_weak": False,
    "gen_vertical_run_no_staff": False,
    "gen_barline_cc_tiny": False,
    "gen_sobel_no_staff": False,
}

V2_DEFAULT_OUT = Path("logs/issue274_homr_unification_analysis/pinned_current_primary_boundary_02")


def _prepare_tuning_contract() -> dict[str, Any]:
    evaluator = importlib.import_module("src.homr_eval_scripts.homr_evaluator")
    existing = getattr(evaluator, "DEFAULT_TUNING", None)
    if existing is not None:
        return {
            "source": "evaluator.DEFAULT_TUNING",
            "injected": False,
            "values": dict(existing),
        }

    # v1 imports this same module through importlib, so setting the attribute on
    # the cached module is sufficient and does not alter the pinned source tree.
    evaluator.DEFAULT_TUNING = dict(HISTORICAL_PRIMARY_DEFAULT_TUNING)
    return {
        "source": (
            "bd6ae56_homr_evaluator_main_argparse_defaults_stage_e_verified_no_tuning_overrides"
        ),
        "injected": True,
        "values": dict(HISTORICAL_PRIMARY_DEFAULT_TUNING),
    }


def _run_cell(runtime: str, proxy: Path, out: Path) -> int:
    contract = _prepare_tuning_contract()
    result = v1.run_cell(runtime, proxy, out)

    report_path = out / "cell_report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["primary_tuning_contract"] = contract
    report_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    args = v1.parser().parse_args()
    try:
        if args.cell_runtime:
            if args.proxy is None or args.cell_output is None:
                raise ValueError("--cell-runtime requires --proxy and --cell-output")
            return _run_cell(
                args.cell_runtime,
                args.proxy.resolve(),
                args.cell_output.resolve(),
            )

        # v1's child launcher resolves Path(__file__) from its own module. Point
        # it at this wrapper so pinned/current child processes both get the v2
        # compatibility behavior.
        v1.__file__ = str(Path(__file__).resolve())
        if args.output_root == v1.OUT_DEFAULT:
            args.output_root = V2_DEFAULT_OUT
        return v1.run_master(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
