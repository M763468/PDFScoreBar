#!/usr/bin/env python3
"""Integrity checks for the Issue #264 Phase C acceptance/replay contract.

The full-68 source runner intentionally retains direct historical-index scoring as
raw diagnostic evidence. Canonical acceptance may ignore only those index-dependent
score gates after geometry rebasing. All other source gates, the current invocation
identity, and resume producer provenance remain mandatory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

DIRECT_INDEX_SCORE_GATES = frozenset(
    {
        "unexpected_fp_zero",
        "missed_fn_not_above_3",
        "skip_mismatch_not_above_6",
    }
)

REQUIRED_NON_INDEX_GATES = frozenset(
    {
        "page_count_68",
        "expected_fixture_total_182",
        "zero_expected_pages_scored",
        "page_033_one_bar_veto",
        "fresh_current_homr_mmr_geometry_all_pages",
        "focused_physical",
        "phase_b_page_042_five_overrides",
        "final_numbering_files_68",
        "phase_a_fresh_current_homr_semantics_68",
    }
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _describe_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def build_producer_contract(runner: Any, *, git_head: str) -> dict[str, Any]:
    """Describe the revision/config/input bytes allowed to produce resumed artifacts."""

    specs = runner.build_page_specs()
    runner.validate_page_specs(specs)
    page_inputs: list[dict[str, Any]] = []
    for spec in specs:
        x4_sr_image = spec.staff_mask.parent / f"{spec.page_name}.png"
        page_inputs.append(
            {
                "page_id": spec.page_id,
                "image": _describe_file(spec.image),
                "barlines": _describe_file(spec.barlines),
                "canonical_staff_mask": _describe_file(spec.staff_mask),
                "canonical_x4_sr_image": _describe_file(x4_sr_image),
            }
        )

    return {
        "schema": "issue264.phase_c_producer_contract.v1",
        "git_head": git_head,
        "canonical_config": _describe_file(runner.CANONICAL_CONFIG),
        "mmr_model": _describe_file(runner.MODEL_PATH),
        "page_index": _describe_file(runner.LEGACY_PAGE_INDEX),
        "page_inputs": page_inputs,
    }


def _source_non_index_gate_failures(report: Mapping[str, Any]) -> list[str]:
    gates = report.get("gates")
    if not isinstance(gates, Mapping):
        raise ValueError("Phase C source report lacks gates")

    missing = sorted(REQUIRED_NON_INDEX_GATES.difference(gates))
    if missing:
        raise ValueError(f"Phase C source report lacks mandatory gates: {missing}")

    return sorted(
        str(name)
        for name, passed in gates.items()
        if name not in DIRECT_INDEX_SCORE_GATES and not bool(passed)
    )


def stamp_source_report(
    report_path: Path,
    *,
    invocation_id: str,
    producer_contract: Mapping[str, Any],
) -> None:
    """Bind a completed, augmented source report to this invocation and producer contract."""

    if not invocation_id:
        raise ValueError("Phase C invocation id must be non-empty")
    report = _load_json(report_path)
    repository = report.get("repository")
    if not isinstance(repository, Mapping):
        raise ValueError("Phase C source report lacks repository provenance")
    expected_head = str(producer_contract.get("git_head", ""))
    if repository.get("git_head") != expected_head:
        raise ValueError(
            "Phase C source report Git HEAD does not match producer contract: "
            f"report={repository.get('git_head')} contract={expected_head}"
        )

    report["acceptance_provenance"] = {
        "schema": "issue264.phase_c_acceptance_provenance.v1",
        "invocation_id": invocation_id,
        "producer_contract": dict(producer_contract),
    }
    _write_json(report_path, report)


def verify_source_report(
    report_path: Path,
    *,
    expected_invocation_id: str,
    expected_git_head: str,
) -> dict[str, Any]:
    """Verify canonical non-index source gates and current-invocation identity."""

    report = _load_json(report_path)
    provenance = report.get("acceptance_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Phase C source report lacks acceptance_provenance")
    if provenance.get("invocation_id") != expected_invocation_id:
        raise ValueError(
            "Phase C source report invocation mismatch: "
            f"report={provenance.get('invocation_id')} expected={expected_invocation_id}"
        )

    contract = provenance.get("producer_contract")
    if not isinstance(contract, Mapping):
        raise ValueError("Phase C source report lacks producer_contract")
    if contract.get("git_head") != expected_git_head:
        raise ValueError(
            "Phase C producer Git HEAD mismatch: "
            f"report={contract.get('git_head')} expected={expected_git_head}"
        )
    repository = report.get("repository")
    if not isinstance(repository, Mapping) or repository.get("git_head") != expected_git_head:
        raise ValueError("Phase C source report repository Git HEAD does not match current invocation")

    failures = _source_non_index_gate_failures(report)
    if failures:
        raise ValueError(f"Phase C non-index source gates failed: {failures}")

    gates = report["gates"]
    ignored_failures = sorted(
        name for name in DIRECT_INDEX_SCORE_GATES if name in gates and not bool(gates[name])
    )
    return {
        "status": "passed",
        "expected_invocation_id": expected_invocation_id,
        "expected_git_head": expected_git_head,
        "ignored_direct_index_gate_failures": ignored_failures,
        "verified_non_index_gates": sorted(
            name for name in gates if name not in DIRECT_INDEX_SCORE_GATES
        ),
    }


def _verify_generated_artifacts(report: Mapping[str, Any]) -> None:
    artifacts = report.get("generated_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 68:
        raise ValueError("Resume source report must contain 68 generated_artifact entries")

    required = ("numbering_base", "numbering_mmr_geometry", "overrides_mmr", "numbering_final")
    for row in artifacts:
        if not isinstance(row, Mapping):
            raise ValueError("Malformed generated_artifacts entry")
        page_id = str(row.get("page_id", ""))
        for label in required:
            detail = row.get(label)
            if not isinstance(detail, Mapping):
                raise ValueError(f"Resume artifact missing {page_id}/{label}")
            path = Path(str(detail.get("path", "")))
            if not path.is_file():
                raise FileNotFoundError(path)
            recorded_size = detail.get("size")
            recorded_hash = detail.get("sha256")
            if path.stat().st_size != recorded_size:
                raise ValueError(f"Resume artifact size changed: {page_id}/{label}")
            if _sha256_file(path) != recorded_hash:
                raise ValueError(f"Resume artifact hash changed: {page_id}/{label}")


def validate_resume_contract(
    report_path: Path,
    *,
    current_producer_contract: Mapping[str, Any],
) -> None:
    """Allow --resume only for a completed run produced by the exact current contract."""

    report = _load_json(report_path)
    provenance = report.get("acceptance_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("Cannot resume: prior report lacks acceptance_provenance")
    recorded_contract = provenance.get("producer_contract")
    if recorded_contract != current_producer_contract:
        raise ValueError("Cannot resume: producer revision/config/input contract changed")

    failures = _source_non_index_gate_failures(report)
    if failures:
        raise ValueError(f"Cannot resume: prior non-index source gates failed: {failures}")
    _verify_generated_artifacts(report)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-invocation-id", required=True)
    parser.add_argument("--expected-git-head", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = verify_source_report(
        args.report,
        expected_invocation_id=args.expected_invocation_id,
        expected_git_head=args.expected_git_head,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
