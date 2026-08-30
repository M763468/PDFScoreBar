"""Evaluate the final Issue #284 eager-vs-compile canonical full-68 A/B.

The semantic comparison is delegated to ``compare_full68_variants.py`` so this
final gate keeps the Issue #286 coordinate policy already established there. In
addition, this wrapper verifies the A/B provenance, compile modes, shared cache,
and whether the compiled variant improves both total SR-batch and total score E2E
wall time.

A corrected compile-only rerun may legitimately be one harness-only commit ahead
of the retained eager control. Such a pair is accepted only when the control is an
ancestor of the candidate and every changed path is in the explicit harness-only
allowlist below; production/config changes are never accepted through this path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
COMPARATOR = ROOT / "tools/issue284/compare_full68_variants.py"
ALLOWED_HARNESS_ONLY_PATHS = frozenset({"tools/issue284/run_compile_full68_variant.py"})


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _variant(root: Path) -> dict[str, Any]:
    path = root / "variant_summary.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = _load_json(path)
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise RuntimeError(f"Incomplete full68 variant: {path}")
    if payload.get("canonical_page_count") != 68:
        raise RuntimeError(f"Variant is not canonical 68 pages: {path}")
    return payload


def _score_view(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("scores", []):
        if not isinstance(item, dict):
            continue
        sr_batch = item.get("sr_batch") or {}
        outputs = sr_batch.get("outputs") or []
        page_times = [
            float(page["page_wall_sec"])
            for page in outputs
            if isinstance(page, dict) and page.get("page_wall_sec") is not None
        ]
        rows.append(
            {
                "score": item.get("score"),
                "page_count": item.get("page_count"),
                "e2e_wall_sec": item.get("e2e_wall_sec"),
                "sr_batch_wall_sec": sr_batch.get("batch_wall_sec"),
                "first_sr_page_wall_sec": page_times[0] if page_times else None,
                "effective_sr_compile_mode": item.get("effective_sr_compile_mode"),
                "compile_cache_before": item.get("compile_cache_before"),
                "compile_cache_after": item.get("compile_cache_after"),
            }
        )
    return rows


def _git_changed_paths(base: str, head: str) -> list[str]:
    process = subprocess.run(
        ["git", "diff", "--name-only", base, head],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        return []
    return sorted(line.strip() for line in process.stdout.splitlines() if line.strip())


def _git_is_ancestor(base: str, head: str) -> bool:
    process = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return process.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    control_root = args.control.resolve()
    candidate_root = args.candidate.resolve()
    control = _variant(control_root)
    candidate = _variant(candidate_root)

    control_ab = control.get("compile_ab") or {}
    candidate_ab = candidate.get("compile_ab") or {}
    control_commit = str(control.get("git_commit") or "")
    candidate_commit = str(candidate.get("git_commit") or "")
    same_git_commit = bool(control_commit) and control_commit == candidate_commit
    source_delta_paths = (
        [] if same_git_commit else _git_changed_paths(control_commit, candidate_commit)
    )
    candidate_descends_from_control = (
        False
        if same_git_commit or not control_commit or not candidate_commit
        else _git_is_ancestor(control_commit, candidate_commit)
    )
    harness_only_source_delta = (
        not same_git_commit
        and candidate_descends_from_control
        and bool(source_delta_paths)
        and set(source_delta_paths).issubset(ALLOWED_HARNESS_ONLY_PATHS)
    )
    source_compatible = same_git_commit or harness_only_source_delta

    provenance = {
        "source_compatible": source_compatible,
        "same_git_commit": same_git_commit,
        "candidate_descends_from_control": candidate_descends_from_control,
        "harness_only_source_delta": harness_only_source_delta,
        "source_delta_paths": source_delta_paths,
        "allowed_harness_only_paths": sorted(ALLOWED_HARNESS_ONLY_PATHS),
        "same_canonical_config_sha256": (
            control.get("config_sha256") == candidate.get("config_sha256")
        ),
        "control_mode_off": control_ab.get("compile_mode_override") == "off",
        "control_effective_mode_none": control_ab.get("effective_sr_compile_mode") is None,
        "candidate_mode_reduce_overhead": (
            candidate_ab.get("compile_mode_override") == "reduce-overhead"
        ),
        "candidate_effective_mode_reduce_overhead": (
            candidate_ab.get("effective_sr_compile_mode") == "reduce-overhead"
        ),
        "candidate_shared_compile_cache": candidate_ab.get("shared_compile_cache") is True,
        "candidate_compile_cache_nonempty": int(
            (candidate_ab.get("compile_cache_final") or {}).get("file_count") or 0
        )
        > 0,
        "candidate_home_xdg_preserved": candidate_ab.get("home_xdg_preserved") is True,
    }
    provenance_valid = all(
        (
            provenance["source_compatible"],
            provenance["same_canonical_config_sha256"],
            provenance["control_mode_off"],
            provenance["control_effective_mode_none"],
            provenance["candidate_mode_reduce_overhead"],
            provenance["candidate_effective_mode_reduce_overhead"],
            provenance["candidate_shared_compile_cache"],
            provenance["candidate_compile_cache_nonempty"],
            provenance["candidate_home_xdg_preserved"],
        )
    )

    comparison_path = args.output.resolve().with_name(
        args.output.resolve().stem + ".semantic_comparison.json"
    )
    command = [
        sys.executable,
        str(COMPARATOR),
        "--control",
        str(control_root),
        "--candidate",
        str(candidate_root),
        "--output",
        str(comparison_path),
    ]
    process = subprocess.run(command, cwd=ROOT, check=False)
    if process.returncode != 0:
        raise RuntimeError(f"Full68 semantic comparator failed: rc={process.returncode}")
    comparison = _load_json(comparison_path)

    control_e2e = float(control.get("total_score_e2e_wall_sec") or 0.0)
    candidate_e2e = float(candidate.get("total_score_e2e_wall_sec") or 0.0)
    control_sr = float(control.get("total_sr_batch_wall_sec") or 0.0)
    candidate_sr = float(candidate.get("total_sr_batch_wall_sec") or 0.0)
    performance = {
        "control_total_score_e2e_wall_sec": control_e2e,
        "candidate_total_score_e2e_wall_sec": candidate_e2e,
        "e2e_saved_sec": control_e2e - candidate_e2e,
        "e2e_reduction_pct": (
            100.0 * (control_e2e - candidate_e2e) / control_e2e if control_e2e else None
        ),
        "e2e_throughput_x": control_e2e / candidate_e2e if candidate_e2e else None,
        "control_total_sr_batch_wall_sec": control_sr,
        "candidate_total_sr_batch_wall_sec": candidate_sr,
        "sr_saved_sec": control_sr - candidate_sr,
        "sr_reduction_pct": (
            100.0 * (control_sr - candidate_sr) / control_sr if control_sr else None
        ),
        "sr_throughput_x": control_sr / candidate_sr if candidate_sr else None,
        "e2e_improved": candidate_e2e < control_e2e,
        "sr_improved": candidate_sr < control_sr,
    }

    semantic_gate = comparison.get("semantic_gate") or {}
    correctness = {
        "semantic_gate_passed": semantic_gate.get("passed") is True,
        "coordinate_review_page_count": int(comparison.get("coordinate_review_page_count") or 0),
        "coordinate_review_clear": int(comparison.get("coordinate_review_page_count") or 0) == 0,
        "hybrid_multiset_exact_pages": comparison.get("hybrid_multiset_exact_pages"),
        "hybrid_metric_exact_pages": comparison.get("hybrid_metric_exact_pages"),
        "base_topology_equal_pages": comparison.get("base_topology_equal_pages"),
        "base_numbers_equal_pages": comparison.get("base_numbers_equal_pages"),
        "final_topology_equal_pages": comparison.get("final_topology_equal_pages"),
        "final_numbers_equal_pages": comparison.get("final_numbers_equal_pages"),
        "mmr_semantic_equal_pages": comparison.get("mmr_semantic_equal_pages"),
        "sr_byte_identical_pages": comparison.get("sr_byte_identical_pages"),
        "connector_symbols_byte_identical_pages": comparison.get(
            "connector_symbols_byte_identical_pages"
        ),
        "connector_brace_dot_byte_identical_pages": comparison.get(
            "connector_brace_dot_byte_identical_pages"
        ),
    }

    final_gate = {
        "provenance_valid": provenance_valid,
        "correctness_preserved": (
            correctness["semantic_gate_passed"] and correctness["coordinate_review_clear"]
        ),
        "performance_improved": performance["e2e_improved"] and performance["sr_improved"],
    }
    final_gate["passed"] = all(final_gate.values())

    payload = {
        "schema_version": "issue284.compile_full68_final_gate.v3",
        "status": "completed",
        "control": str(control_root),
        "candidate": str(candidate_root),
        "semantic_comparison": str(comparison_path),
        "provenance": provenance,
        "performance": performance,
        "correctness": correctness,
        "control_scores": _score_view(control),
        "candidate_scores": _score_view(candidate),
        "final_gate": final_gate,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if final_gate["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
