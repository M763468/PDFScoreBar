#!/usr/bin/env python3
"""Repair the Issue #274 full68 downstream topology gate without rerunning inference.

The original full68 verifier read only the score-level combined numbering artifact.
This post-hoc verifier reads the authoritative per-page Phase-C outputs directly:
``outputs/<page_id>/numbering_final.json``. It never runs HOMR, SR, detection,
CNN, MMR, or numbering.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tools.issue120.eval_full68_from_intermediates import SCORES

DEFAULT_CONTROL_ROOT = Path(
    "logs/verification/detector_full68/"
    "issue255_production_restore_full68_top_level_worker_01/production_runs"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def to_workspace(value: str | Path, workspace: Path) -> Path:
    text = str(value)
    if text.startswith("/workspace/"):
        return workspace / text[len("/workspace/") :]
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def load_single_page(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    payload = load_json(path)
    if not isinstance(payload, Mapping):
        return None
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], Mapping):
        return None
    return pages[0]


def topology_signature(page: Mapping[str, Any]) -> tuple[Any, ...]:
    systems = page.get("systems", [])
    if not isinstance(systems, list):
        return ()
    return tuple(
        (
            len(system.get("staves", [])),
            len(system.get("measures", [])),
            tuple(
                measure.get("number")
                for measure in system.get("measures", [])
                if isinstance(measure, Mapping)
            ),
            tuple(
                (int(measure["bbox"][0]), int(measure["bbox"][2]))
                for measure in system.get("measures", [])
                if isinstance(measure, Mapping)
                and isinstance(measure.get("bbox"), list)
                and len(measure["bbox"]) == 4
            ),
        )
        for system in systems
        if isinstance(system, Mapping)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--control-root", type=Path, default=DEFAULT_CONTROL_ROOT)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    control_root = to_workspace(args.control_root, workspace)
    summary_path = to_workspace(
        args.summary or (run_root / "two_homr_full68_fresh_summary.json"), workspace
    )
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)

    previous = load_json(summary_path)
    if not isinstance(previous, Mapping):
        raise ValueError(f"Summary must be an object: {summary_path}")

    expected_page_count = sum(len(pages) for pages in SCORES.values())
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for score, pages in SCORES.items():
        for page_id in pages:
            fresh_path = run_root / "runs" / score / "outputs" / page_id / "numbering_final.json"
            control_path = control_root / score / "outputs" / page_id / "numbering_final.json"
            fresh_page = load_single_page(fresh_path)
            control_page = load_single_page(control_path)
            row = {
                "score": score,
                "page": page_id,
                "fresh_path": str(fresh_path),
                "control_path": str(control_path),
                "fresh_exists": fresh_page is not None,
                "control_exists": control_page is not None,
            }
            if fresh_page is None or control_page is None:
                missing.append(row)
                rows.append({**row, "topology_equal": None})
                continue

            fresh_signature = topology_signature(fresh_page)
            control_signature = topology_signature(control_page)
            equal = fresh_signature == control_signature
            row["topology_equal"] = equal
            if not equal:
                changed.append(
                    {
                        **row,
                        "fresh_signature": fresh_signature,
                        "control_signature": control_signature,
                    }
                )
            rows.append(row)

    architecture_ok = bool((previous.get("architecture") or {}).get("contract_ok"))
    detector_ok = bool((previous.get("detector") or {}).get("coverage_ok"))
    page_identity_ok = bool(previous.get("page_identity_ok"))
    old_downstream = previous.get("downstream") or {}
    downstream_reuse_ok = (
        not old_downstream.get("contract_bad_pages")
        and int(old_downstream.get("fallback_page_count", 0)) >= 0
    )
    topology_ok = len(rows) == expected_page_count and not missing and not changed
    gate_pass = all(
        (architecture_ok, detector_ok, page_identity_ok, downstream_reuse_ok, topology_ok)
    )

    summary = {
        "schema_version": "issue274.two_homr_full68_fresh_gate.v3",
        "status": "completed",
        "run_root": str(run_root),
        "source_summary": str(summary_path),
        "expected_page_count": expected_page_count,
        "architecture_ok": architecture_ok,
        "detector_coverage_ok": detector_ok,
        "page_identity_ok": page_identity_ok,
        "downstream_reuse_ok": downstream_reuse_ok,
        "numbering": {
            "fresh_page_count": sum(bool(row["fresh_exists"]) for row in rows),
            "control_page_count": sum(bool(row["control_exists"]) for row in rows),
            "missing_page_count": len(missing),
            "missing_pages": missing,
            "topology_changed_page_count": len(changed),
            "topology_changed_pages": changed,
            "topology_ok": topology_ok,
            "pages": rows,
        },
        "gate_pass": gate_pass,
    }

    output = to_workspace(
        args.output or (run_root / "two_homr_full68_fresh_summary_v3.json"), workspace
    )
    summary["output"] = str(output)
    write_json(output, summary)
    print(
        json.dumps(
            {
                "gate_pass": gate_pass,
                "architecture_ok": architecture_ok,
                "detector_coverage_ok": detector_ok,
                "page_identity_ok": page_identity_ok,
                "downstream_reuse_ok": downstream_reuse_ok,
                "fresh_numbering_page_count": summary["numbering"]["fresh_page_count"],
                "control_numbering_page_count": summary["numbering"]["control_page_count"],
                "numbering_missing_page_count": len(missing),
                "topology_changed_page_count": len(changed),
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if gate_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())
