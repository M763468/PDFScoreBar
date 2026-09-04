#!/usr/bin/env python3
"""Temporary Issue #296 audit of clean-lineage v5/v6/v7 checkpoints.

Diagnostic-only. Delete before PR preparation.

This reuses the frozen full68 scorer/matcher from diagnostic_07 and compares
all three contamination-free checkpoints. The historical production accepted
artifact is used only as the control contract; no contaminated checkpoint is
part of the candidate inference path.
"""
from __future__ import annotations

import json
from pathlib import Path

import tools.issue296.evaluate_clean_full68 as audit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "logs/issue296/diagnostic_12_clean_stage_full68"
CHECKPOINTS = {
    "v5": ROOT / "logs/cnn_barline_classification/issue296_clean_lineage_v5/cnn_classifier_best.pth",
    "v6": ROOT / "logs/cnn_barline_classification/issue296_clean_lineage_v6/cnn_classifier_best.pth",
    "v7": ROOT / "logs/cnn_barline_classification/issue296_clean_lineage_v7/cnn_classifier_best.pth",
}


def stage_gate(payload: dict) -> bool:
    control = payload["control"]
    clean = payload["clean"]
    target = payload.get("target_x580_acceptance_delta")
    p3 = payload["p3"]
    return bool(
        payload.get("control_reproduces_canonical_contract") is True
        and target is not None
        and target.get("control_accept") is True
        and target.get("clean_accept") is False
        and clean["tp"] >= control["tp"]
        and clean["hard_fp"] <= 2
        and clean["fn"] <= control["fn"]
        and p3["pair_count"] == 51
        and p3["clean_complete_pairs"] == 51
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": "issue296.clean_lineage_stage_full68.v1",
        "purpose": "compare contamination-free v5/v6/v7 checkpoints before changing architecture",
        "stages": {},
    }

    for stage, checkpoint in CHECKPOINTS.items():
        if not checkpoint.is_file():
            raise FileNotFoundError(checkpoint)
        stage_out = OUT / stage
        stage_out.mkdir(parents=True, exist_ok=True)
        audit.CLEAN_CKPT = checkpoint
        audit.OUT = stage_out
        print(f"==> full68 {stage}: {checkpoint}")
        rc = audit.main()
        if rc not in (None, 0):
            raise RuntimeError(f"full68 audit failed for {stage}: {rc}")
        summary_path = stage_out / "clean_full68_summary.json"
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        result["stages"][stage] = {
            "checkpoint": str(checkpoint),
            "control": payload["control"],
            "clean": payload["clean"],
            "delta_vs_control": payload["delta_vs_control"],
            "target_x580_acceptance_delta": payload.get("target_x580_acceptance_delta"),
            "p007_known_fp_acceptance_deltas": payload.get("p007_known_fp_acceptance_deltas", []),
            "acceptance_delta_count": payload.get("acceptance_delta_count"),
            "p3": payload["p3"],
            "residuals": payload.get("residuals", []),
            "detector_gate_pass": stage_gate(payload),
        }

    passes = [name for name, row in result["stages"].items() if row["detector_gate_pass"]]
    result["passing_stages"] = passes
    result["any_stage_passes"] = bool(passes)
    out = OUT / "clean_stage_full68_summary.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "passing_stages": passes,
        "stages": {
            name: {
                "clean": row["clean"],
                "delta_vs_control": row["delta_vs_control"],
                "detector_gate_pass": row["detector_gate_pass"],
                "acceptance_delta_count": row["acceptance_delta_count"],
            }
            for name, row in result["stages"].items()
        },
        "result": str(out),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
