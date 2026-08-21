#!/usr/bin/env python3
"""Validate fresh Issue #274 numbering against the accepted current-production baseline.

The detector-only Issue #255 artifacts and the earlier Issue #274 retained semantic
reconstruction are not valid numbering baselines for this gate. In particular, the
old current-support tree predates PR #265's current-HOMR staff-mask coordinate fix.
Current ``MeasureNumberingPipeline`` falls back to the A/Proxy numbering geometry
when that sibling semantic staff mask extracts a different staff count, so the old
reconstruction and a fresh post-#265 run can take different connector-evidence
branches even when connector-mask bytes are identical.

The correct reference is the accepted Issue #264 Phase-C current-production full68
source report. That run explicitly regenerated current-HOMR Phase-A semantics from
retained x4 SR inputs after PR #265, kept detector inference frozen, and persisted
all 68 production ``numbering_base.json`` files with hashes.

This verifier performs no inference and no numbering recomputation. It verifies the
Phase-C baseline provenance/hash contract, then compares serialized production
numbering to serialized fresh production numbering page by page.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from tools.issue120.eval_full68_from_intermediates import SCORES
from tools.issue264.phase_c_acceptance_integrity import source_non_index_gate_failures

DEFAULT_BASELINE_ROOT = Path("logs/issue264_phase_c_mmr_regression")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _bbox(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    return tuple(int(item) for item in value)  # type: ignore[return-value]


def serialized_numbering_signature(page: Mapping[str, Any]) -> tuple[Any, ...]:
    """Compare the stable serialized numbering contract, excluding page ordinal only."""

    systems = page.get("systems", [])
    empty_systems = page.get("empty_systems", [])
    if not isinstance(systems, list) or not isinstance(empty_systems, list):
        return ()

    system_rows: list[Any] = []
    for system in systems:
        if not isinstance(system, Mapping):
            return ()
        staves = system.get("staves", [])
        measures = system.get("measures", [])
        if not isinstance(staves, list) or not isinstance(measures, list):
            return ()
        staff_boxes = tuple(
            _bbox(staff.get("bbox"))
            for staff in staves
            if isinstance(staff, Mapping)
        )
        measure_rows = tuple(
            (measure.get("number"), _bbox(measure.get("bbox")))
            for measure in measures
            if isinstance(measure, Mapping)
        )
        system_rows.append((staff_boxes, measure_rows))

    empty_rows: list[Any] = []
    for system in empty_systems:
        if not isinstance(system, Mapping):
            return ()
        staves = system.get("staves", [])
        if not isinstance(staves, list):
            return ()
        empty_rows.append(
            tuple(
                _bbox(staff.get("bbox"))
                for staff in staves
                if isinstance(staff, Mapping)
            )
        )

    return (
        int(page.get("width", -1)),
        int(page.get("height", -1)),
        tuple(system_rows),
        tuple(empty_rows),
    )


def _phase_c_contract(report: Mapping[str, Any]) -> dict[str, Any]:
    pages = report.get("pages")
    generated = report.get("generated_artifacts")
    evaluation_inputs = report.get("evaluation_inputs")
    acceptance = report.get("acceptance_provenance")

    semantic_support: Mapping[str, Any] = {}
    if isinstance(evaluation_inputs, Mapping):
        raw_support = evaluation_inputs.get("phase_a_semantic_support")
        if isinstance(raw_support, Mapping):
            semantic_support = raw_support

    failures: list[str] = []
    try:
        failures = source_non_index_gate_failures(report)
    except (KeyError, TypeError, ValueError) as error:
        failures = [f"invalid non-index gate contract: {error}"]

    ok = (
        isinstance(pages, list)
        and len(pages) == 68
        and isinstance(generated, list)
        and len(generated) == 68
        and isinstance(acceptance, Mapping)
        and int(semantic_support.get("pages", -1)) == 68
        and semantic_support.get("historical_detector_artifact_runtime_input") is False
        and semantic_support.get("detector_reexecuted") is False
        and semantic_support.get("real_esrgan_reexecuted") is False
        and semantic_support.get("omr_dln_reexecuted") is False
        and not failures
    )
    return {
        "ok": ok,
        "page_count": len(pages) if isinstance(pages, list) else None,
        "generated_artifact_count": len(generated) if isinstance(generated, list) else None,
        "has_acceptance_provenance": isinstance(acceptance, Mapping),
        "semantic_support": dict(semantic_support),
        "non_index_gate_failures": failures,
    }


def discover_baseline_report(
    *,
    workspace: Path,
    explicit: Path | None,
    baseline_root: Path,
) -> tuple[Path, Mapping[str, Any], dict[str, Any]]:
    if explicit is not None:
        candidates = [to_workspace(explicit, workspace)]
    else:
        root = to_workspace(baseline_root, workspace)
        candidates = sorted(root.rglob("phase_c_mmr_regression_report.json")) if root.is_dir() else []

    accepted: list[tuple[Path, Mapping[str, Any], dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for path in candidates:
        if not path.is_file():
            rejected.append({"path": str(path), "reason": "missing"})
            continue
        payload = load_json(path)
        if not isinstance(payload, Mapping):
            rejected.append({"path": str(path), "reason": "not a JSON object"})
            continue
        contract = _phase_c_contract(payload)
        if contract["ok"]:
            accepted.append((path, payload, contract))
        else:
            rejected.append({"path": str(path), "contract": contract})

    if len(accepted) != 1:
        raise RuntimeError(
            "Expected exactly one accepted Issue #264 Phase-C baseline report; "
            f"accepted={[str(item[0]) for item in accepted]} rejected={rejected}. "
            "Pass --baseline-report explicitly if multiple accepted reports are retained."
        )
    return accepted[0]


def baseline_numbering_map(
    report: Mapping[str, Any],
    *,
    workspace: Path,
) -> tuple[dict[tuple[str, str], Path], list[dict[str, Any]]]:
    pages = report.get("pages")
    generated = report.get("generated_artifacts")
    if not isinstance(pages, list) or not isinstance(generated, list):
        raise ValueError("Phase-C report lacks pages/generated_artifacts")

    identity_by_page_id: dict[str, tuple[str, str]] = {}
    for row in pages:
        if not isinstance(row, Mapping):
            continue
        page_id = str(row.get("page_id", ""))
        score = str(row.get("score", ""))
        score_page = str(row.get("score_page", ""))
        if page_id and score and score_page:
            identity_by_page_id[page_id] = (score, score_page)

    result: dict[tuple[str, str], Path] = {}
    invalid: list[dict[str, Any]] = []
    for row in generated:
        if not isinstance(row, Mapping):
            continue
        page_id = str(row.get("page_id", ""))
        identity = identity_by_page_id.get(page_id)
        detail = row.get("numbering_base")
        if identity is None or not isinstance(detail, Mapping):
            invalid.append({"page_id": page_id, "reason": "missing identity/numbering_base"})
            continue
        path = to_workspace(str(detail.get("path", "")), workspace)
        if not path.is_file():
            invalid.append({"page_id": page_id, "path": str(path), "reason": "missing file"})
            continue
        expected_size = detail.get("size")
        expected_hash = detail.get("sha256")
        if expected_size is not None and path.stat().st_size != int(expected_size):
            invalid.append({"page_id": page_id, "path": str(path), "reason": "size mismatch"})
            continue
        if expected_hash and sha256(path) != str(expected_hash):
            invalid.append({"page_id": page_id, "path": str(path), "reason": "sha256 mismatch"})
            continue
        if identity in result:
            invalid.append({"page_id": page_id, "identity": identity, "reason": "duplicate identity"})
            continue
        result[identity] = path
    return result, invalid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--baseline-report", type=Path)
    parser.add_argument("--baseline-root", type=Path, default=DEFAULT_BASELINE_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    summary_path = to_workspace(
        args.summary or (run_root / "two_homr_full68_fresh_summary.json"),
        workspace,
    )
    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)

    previous = load_json(summary_path)
    if not isinstance(previous, Mapping):
        raise ValueError(f"Summary must be an object: {summary_path}")

    baseline_report_path, baseline_report, baseline_contract = discover_baseline_report(
        workspace=workspace,
        explicit=args.baseline_report,
        baseline_root=args.baseline_root,
    )
    baseline_map, baseline_invalid = baseline_numbering_map(
        baseline_report,
        workspace=workspace,
    )

    expected = {(score, page) for score, pages in SCORES.items() for page in pages}
    rows: list[dict[str, Any]] = []
    missing_fresh: list[dict[str, str]] = []
    missing_baseline: list[dict[str, str]] = []
    changed: list[dict[str, Any]] = []

    for score, page_id in sorted(expected):
        fresh_path = run_root / "runs" / score / "intermediate" / page_id / "numbering_base.json"
        baseline_path = baseline_map.get((score, page_id))
        fresh_page = load_single_page(fresh_path)
        baseline_page = load_single_page(baseline_path) if baseline_path is not None else None
        row: dict[str, Any] = {
            "score": score,
            "page": page_id,
            "fresh_numbering_base": str(fresh_path),
            "baseline_numbering_base": str(baseline_path) if baseline_path else None,
            "fresh_exists": fresh_page is not None,
            "baseline_exists": baseline_page is not None,
        }
        if fresh_page is None:
            missing_fresh.append({"score": score, "page": page_id})
        if baseline_page is None:
            missing_baseline.append({"score": score, "page": page_id})
        if fresh_page is None or baseline_page is None:
            row["numbering_equal"] = None
            rows.append(row)
            continue

        fresh_signature = serialized_numbering_signature(fresh_page)
        baseline_signature = serialized_numbering_signature(baseline_page)
        equal = fresh_signature == baseline_signature
        row["numbering_equal"] = equal
        if not equal:
            changed.append(
                {
                    **row,
                    "fresh_signature": fresh_signature,
                    "baseline_signature": baseline_signature,
                }
            )
        rows.append(row)

    architecture_ok = bool((previous.get("architecture") or {}).get("contract_ok"))
    detector_ok = bool((previous.get("detector") or {}).get("coverage_ok"))
    page_identity_ok = bool(previous.get("page_identity_ok"))
    old_downstream = previous.get("downstream") or {}
    downstream_reuse_ok = (
        isinstance(old_downstream, Mapping)
        and not old_downstream.get("contract_bad_pages")
        and int(old_downstream.get("fallback_page_count", -1)) == 0
    )
    topology_ok = (
        baseline_contract["ok"]
        and len(baseline_map) == len(expected)
        and not baseline_invalid
        and len(rows) == len(expected)
        and not missing_fresh
        and not missing_baseline
        and not changed
    )
    gate_pass = all(
        (
            architecture_ok,
            detector_ok,
            page_identity_ok,
            downstream_reuse_ok,
            topology_ok,
        )
    )

    summary = {
        "schema_version": "issue274.two_homr_full68_fresh_gate.v5",
        "status": "completed",
        "run_root": str(run_root),
        "source_summary": str(summary_path),
        "expected_page_count": len(expected),
        "verification_contract": {
            "baseline": "accepted Issue #264 Phase-C current-production full68 numbering_base",
            "baseline_requires_pr265_semantics": True,
            "comparison": "serialized production numbering_base vs serialized production numbering_base",
            "page_number_ordinal_compared": False,
            "staff_bboxes_compared": True,
            "measure_numbers_compared": True,
            "measure_bboxes_compared": True,
            "empty_systems_compared": True,
            "rerun_inference": False,
            "rerun_numbering": False,
        },
        "architecture_ok": architecture_ok,
        "detector_coverage_ok": detector_ok,
        "page_identity_ok": page_identity_ok,
        "downstream_reuse_ok": downstream_reuse_ok,
        "baseline": {
            "report": str(baseline_report_path),
            "contract": baseline_contract,
            "mapped_page_count": len(baseline_map),
            "invalid_artifacts": baseline_invalid,
        },
        "fresh_numbering_base": {
            "page_count": sum(bool(row["fresh_exists"]) for row in rows),
            "missing_page_count": len(missing_fresh),
            "missing_pages": missing_fresh,
            "missing_baseline_page_count": len(missing_baseline),
            "missing_baseline_pages": missing_baseline,
            "changed_page_count": len(changed),
            "changed_pages": changed,
            "pages": rows,
        },
        "topology_ok": topology_ok,
        "gate_pass": gate_pass,
        "supersedes": {
            "v2": "invalid detector-only numbering baseline assumption",
            "v3": "same control-numbering assumption remained on the control side",
            "v4": (
                "used a pre-PR265 stale current-support semantic audit; production fallback "
                "therefore made it a different connector-evidence contract from fresh runs"
            ),
            "details": "tools/issue274/README_full68_verifier_contract.md",
        },
    }

    output = to_workspace(
        args.output or (run_root / "two_homr_full68_fresh_summary_v5.json"),
        workspace,
    )
    summary["output"] = str(output)
    write_json(output, summary)
    print(
        json.dumps(
            {
                "gate_pass": gate_pass,
                "architecture_ok": architecture_ok,
                "detector_coverage_ok": detector_ok,
                "downstream_reuse_ok": downstream_reuse_ok,
                "baseline_contract_ok": baseline_contract["ok"],
                "baseline_page_count": len(baseline_map),
                "fresh_numbering_page_count": summary["fresh_numbering_base"]["page_count"],
                "changed_page_count": len(changed),
                "topology_ok": topology_ok,
                "output": str(output),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if gate_pass else 4


if __name__ == "__main__":
    raise SystemExit(main())
