#!/usr/bin/env python3
"""Validate fresh Issue #274 topology without inventing a control numbering run.

This verifier supersedes the first post-hoc v3 attempt. The retained Issue #255
``DEFAULT_CONTROL_ROOT`` is a detector-only baseline: it contains accepted control
barlines but does not promise ``outputs/<page>/numbering_final.json``. Treating
those nonexistent files as a topology regression was an artifact-contract error.

The corrected gate uses a two-link evidence chain:

1. the independent retained CPU-only B-vs-control semantic audit must prove that
   retained current-x4/B base-numbering topology equals control topology on all 68
   canonical pages; and
2. the actual fresh production ``intermediate/<page>/numbering_base.json`` files
   must match the retained B topology signatures on all 68 pages.

No HOMR, SR, detector, CNN, MMR, OCR, or numbering computation is rerun here.
See ``README_full68_verifier_contract.md`` for the failure history and rationale.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from tools.issue120.eval_full68_from_intermediates import SCORES

DEFAULT_SEMANTIC_AUDIT = Path(
    "logs/issue274_homr_unification_analysis/"
    "b_downstream_semantic_equivalence_01/"
    "issue274_b_downstream_semantic_equivalence.json"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


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
    if (
        not isinstance(pages, list)
        or len(pages) != 1
        or not isinstance(pages[0], Mapping)
    ):
        return None
    return pages[0]


def serialized_topology_signature(page: Mapping[str, Any]) -> tuple[Any, ...]:
    systems = page.get("systems", [])
    if not isinstance(systems, list):
        return ()
    valid_systems = [system for system in systems if isinstance(system, Mapping)]
    staves_per_system = tuple(len(system.get("staves", [])) for system in valid_systems)
    measures_per_system = tuple(
        len(system.get("measures", [])) for system in valid_systems
    )
    measure_numbers = tuple(
        tuple(
            measure.get("number")
            for measure in system.get("measures", [])
            if isinstance(measure, Mapping)
        )
        for system in valid_systems
    )
    return (
        len(valid_systems),
        staves_per_system,
        measures_per_system,
        sum(measures_per_system),
        measure_numbers,
    )


def retained_topology_signature(signature: Mapping[str, Any]) -> tuple[Any, ...]:
    systems = signature.get("systems", [])
    if not isinstance(systems, list):
        return ()
    return (
        int(signature.get("system_count", -1)),
        tuple(int(value) for value in signature.get("staves_per_system", [])),
        tuple(int(value) for value in signature.get("measures_per_system", [])),
        int(signature.get("total_measures", -1)),
        tuple(
            tuple(system.get("measure_numbers", []))
            for system in systems
            if isinstance(system, Mapping)
        ),
    )


def semantic_audit_map(
    payload: Mapping[str, Any], expected_page_count: int
) -> tuple[dict[tuple[str, str], Mapping[str, Any]], dict[str, Any]]:
    summary = payload.get("summary")
    pages = payload.get("pages")
    if not isinstance(summary, Mapping) or not isinstance(pages, list):
        return {}, {"ok": False, "reason": "missing summary/pages contract"}

    mapping: dict[tuple[str, str], Mapping[str, Any]] = {}
    duplicate_keys: list[dict[str, str]] = []
    for row in pages:
        if not isinstance(row, Mapping):
            continue
        key = (str(row.get("score")), str(row.get("page")))
        signature = row.get("candidate_signature")
        if not isinstance(signature, Mapping):
            continue
        if key in mapping:
            duplicate_keys.append({"score": key[0], "page": key[1]})
        mapping[key] = signature

    topology_exact = int(summary.get("topology_exact", -1))
    topology_changed = int(summary.get("topology_changed_page_count", -1))
    reported_pages = int(summary.get("pages", -1))
    ok = (
        payload.get("status") == "completed"
        and reported_pages == expected_page_count
        and topology_exact == expected_page_count
        and topology_changed == 0
        and len(mapping) == expected_page_count
        and not duplicate_keys
    )
    return mapping, {
        "ok": ok,
        "status": payload.get("status"),
        "reported_pages": reported_pages,
        "topology_exact": topology_exact,
        "topology_changed_page_count": topology_changed,
        "mapped_page_count": len(mapping),
        "duplicate_pages": duplicate_keys,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--semantic-audit", type=Path, default=DEFAULT_SEMANTIC_AUDIT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    run_root = to_workspace(args.run_root, workspace)
    summary_path = to_workspace(
        args.summary or (run_root / "two_homr_full68_fresh_summary.json"),
        workspace,
    )
    semantic_audit_path = to_workspace(args.semantic_audit, workspace)

    if not summary_path.is_file():
        raise FileNotFoundError(summary_path)
    if not semantic_audit_path.is_file():
        raise FileNotFoundError(semantic_audit_path)

    previous = load_json(summary_path)
    semantic_audit = load_json(semantic_audit_path)
    if not isinstance(previous, Mapping):
        raise ValueError(f"Summary must be an object: {summary_path}")
    if not isinstance(semantic_audit, Mapping):
        raise ValueError(f"Semantic audit must be an object: {semantic_audit_path}")

    expected = {(score, page) for score, pages in SCORES.items() for page in pages}
    expected_page_count = len(expected)
    retained_map, retained_contract = semantic_audit_map(
        semantic_audit, expected_page_count
    )

    rows: list[dict[str, Any]] = []
    missing_fresh: list[dict[str, str]] = []
    missing_retained: list[dict[str, str]] = []
    changed: list[dict[str, Any]] = []

    for score, page_id in sorted(expected):
        fresh_path = (
            run_root
            / "runs"
            / score
            / "intermediate"
            / page_id
            / "numbering_base.json"
        )
        fresh_page = load_single_page(fresh_path)
        retained_signature = retained_map.get((score, page_id))
        row: dict[str, Any] = {
            "score": score,
            "page": page_id,
            "fresh_numbering_base": str(fresh_path),
            "fresh_exists": fresh_page is not None,
            "retained_b_signature_exists": retained_signature is not None,
        }
        if fresh_page is None:
            missing_fresh.append({"score": score, "page": page_id})
        if retained_signature is None:
            missing_retained.append({"score": score, "page": page_id})
        if fresh_page is None or retained_signature is None:
            row["topology_equal"] = None
            rows.append(row)
            continue

        fresh_signature = serialized_topology_signature(fresh_page)
        expected_signature = retained_topology_signature(retained_signature)
        equal = fresh_signature == expected_signature
        row["topology_equal"] = equal
        if not equal:
            changed.append(
                {
                    **row,
                    "fresh_signature": fresh_signature,
                    "retained_b_signature": expected_signature,
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
    fresh_topology_ok = (
        len(rows) == expected_page_count
        and not missing_fresh
        and not missing_retained
        and not changed
    )
    topology_ok = bool(retained_contract["ok"]) and fresh_topology_ok
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
        "schema_version": "issue274.two_homr_full68_fresh_gate.v4",
        "status": "completed",
        "run_root": str(run_root),
        "source_summary": str(summary_path),
        "semantic_audit": str(semantic_audit_path),
        "expected_page_count": expected_page_count,
        "verification_contract": {
            "control_source": (
                "retained detector control accepted barlines are not assumed to "
                "contain numbering outputs"
            ),
            "retained_link": (
                "independent CPU-only semantic audit proves control == retained B "
                "topology"
            ),
            "fresh_link": (
                "actual fresh numbering_base topology must equal retained B topology"
            ),
            "rerun_inference": False,
            "rerun_numbering": False,
        },
        "architecture_ok": architecture_ok,
        "detector_coverage_ok": detector_ok,
        "page_identity_ok": page_identity_ok,
        "downstream_reuse_ok": downstream_reuse_ok,
        "retained_semantic_audit": retained_contract,
        "fresh_numbering_base": {
            "page_count": sum(bool(row["fresh_exists"]) for row in rows),
            "missing_page_count": len(missing_fresh),
            "missing_pages": missing_fresh,
            "missing_retained_signature_count": len(missing_retained),
            "missing_retained_signatures": missing_retained,
            "topology_changed_page_count": len(changed),
            "topology_changed_pages": changed,
            "topology_ok": fresh_topology_ok,
            "pages": rows,
        },
        "topology_ok": topology_ok,
        "gate_pass": gate_pass,
        "supersedes": {
            "v2_problem": (
                "assumed score-level numbering artifacts existed under a detector-only "
                "control root"
            ),
            "v3_problem": (
                "fixed the fresh per-page path but retained the same nonexistent "
                "control-numbering assumption"
            ),
            "details": "tools/issue274/README_full68_verifier_contract.md",
        },
    }

    output = to_workspace(
        args.output or (run_root / "two_homr_full68_fresh_summary_v4.json"),
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
                "retained_semantic_audit_ok": retained_contract["ok"],
                "fresh_numbering_base_page_count": summary["fresh_numbering_base"][
                    "page_count"
                ],
                "fresh_numbering_missing_page_count": len(missing_fresh),
                "topology_changed_page_count": len(changed),
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
