#!/usr/bin/env python3
"""Summarize Issue #142 CNN NMS policy evidence from canonical eval outputs.

This tool reads existing Issue #120 canonical evaluation directories and writes
one compact JSON/Markdown record for the NMS policy decision.  It does not run
CNN scoring, detector evaluation, or downstream measure numbering.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NmsEvidenceCase:
    label: str
    eval_dir: str
    cnn_apply_nms: bool | None
    tp: int | None
    fp: int | None
    fn: int | None
    pred: int | None
    gt: int | None
    measure_count_status: str
    measure_count_net_delta: int | None
    measure_count_abs_delta_sum: int | None
    measure_count_delta_pages: int | None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_case_arg(value: str) -> tuple[str, Path]:
    label, sep, eval_dir = value.partition("=")
    if not sep or not label or not eval_dir:
        raise argparse.ArgumentTypeError("case must be LABEL=EVAL_DIR")
    return label, Path(eval_dir)


def _nms_from_provenance(eval_dir: Path) -> bool | None:
    candidates = [
        eval_dir / "stage_b_provenance.json",
        eval_dir / "intermediate_provenance.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        payload = load_json(path)
        if "pipeline_nms_enabled" in payload:
            return bool(payload["pipeline_nms_enabled"])
        cnn_scoring = payload.get("cnn_scoring")
        if isinstance(cnn_scoring, dict) and "cnn_apply_nms" in cnn_scoring:
            return bool(cnn_scoring["cnn_apply_nms"])
    return None


def _measure_count_summary(eval_dir: Path) -> dict[str, Any]:
    contract_path = eval_dir / "evaluation_contract.json"
    if not contract_path.exists():
        return {"status": "missing_evaluation_contract"}
    contract = load_json(contract_path)
    summary = contract.get("measure_count_summary")
    if not isinstance(summary, dict):
        return {"status": "missing_measure_count_summary"}
    return summary


def load_case(label: str, eval_dir: Path) -> NmsEvidenceCase:
    detector_path = eval_dir / "detector_metrics.json"
    detector = load_json(detector_path) if detector_path.exists() else {}
    measure = _measure_count_summary(eval_dir)
    return NmsEvidenceCase(
        label=label,
        eval_dir=str(eval_dir),
        cnn_apply_nms=_nms_from_provenance(eval_dir),
        tp=detector.get("tp"),
        fp=detector.get("fp"),
        fn=detector.get("fn"),
        pred=detector.get("pred"),
        gt=detector.get("gt"),
        measure_count_status=str(measure.get("status", "unknown")),
        measure_count_net_delta=measure.get("net_delta"),
        measure_count_abs_delta_sum=measure.get("abs_delta_sum"),
        measure_count_delta_pages=measure.get("delta_pages"),
    )


def write_json(path: Path, cases: list[NmsEvidenceCase], decision: str) -> None:
    payload = {
        "schema_version": "issue142.nms_policy_evidence.v1",
        "issue": 142,
        "parent_issue": 120,
        "decision": decision,
        "cases": [asdict(case) for case in cases],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def format_nullable(value: object) -> str:
    if value is None:
        return "not_provided"
    return str(value)


def write_markdown(path: Path, cases: list[NmsEvidenceCase], decision: str) -> None:
    lines = [
        "# Issue 142 NMS Policy Evidence",
        "",
        f"Decision: {decision}",
        "",
        "| Case | cnn_apply_nms | TP | FP | FN | Pred | GT | measure-count status | net delta | abs delta sum | delta pages |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for case in cases:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.label,
                    format_nullable(case.cnn_apply_nms),
                    format_nullable(case.tp),
                    format_nullable(case.fp),
                    format_nullable(case.fn),
                    format_nullable(case.pred),
                    format_nullable(case.gt),
                    case.measure_count_status,
                    format_nullable(case.measure_count_net_delta),
                    format_nullable(case.measure_count_abs_delta_sum),
                    format_nullable(case.measure_count_delta_pages),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Detector metrics and downstream measure-count metrics are reported separately.",
            "A missing measure-count value means no downstream numbering summary was attached to that eval contract.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        type=parse_case_arg,
        required=True,
        metavar="LABEL=EVAL_DIR",
        help="Evaluation case to summarize. May be provided multiple times.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/issue142_nms_policy/evidence_summary.json"),
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/issue142_nms_policy/evidence_summary.md"),
    )
    parser.add_argument(
        "--decision",
        default=(
            "Set general CNN scoring NMS default to off. Keep NMS available as an "
            "explicit opt-in setting until canonical detector and measure-count "
            "evidence supports making it default again."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    cases = [load_case(label, eval_dir) for label, eval_dir in args.case]
    write_json(args.output_json, cases, args.decision)
    write_markdown(args.output_md, cases, args.decision)
    print(f"Wrote: {args.output_json}")
    print(f"Wrote: {args.output_md}")


if __name__ == "__main__":
    main()
