#!/usr/bin/env python3
"""Finalize an Issue #294 host gate whose container work already completed."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_ROOT))

from tools.issue294.run_same_original_ab_host import (  # noqa: E402
    BASE_COMMIT,
    BRANCH,
    CONTAINER,
    CONTAINER_ROOT,
    EXPECTED_IMAGE_ID,
    PIPELINE_PYTHON,
    PROJECT_ROOT,
    _restore_host_ownership,
    _run_comparator,
    _run_pinned_runtime_probe,
    checked,
    container_path,
    require_container,
    require_host_checkout,
)

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def _load_mapping(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON mapping: {path}")
    return payload


def _require_experiment_commit_ancestor(experiment_commit: str, current_head: str) -> None:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", experiment_commit, current_head],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Existing run source {experiment_commit} is not an ancestor of current HEAD {current_head}"
        )


def _resolve_experiment_commit(
    summary_payload: dict[str, object],
    explicit_source_commit: str | None,
    finalizer_commit: str,
) -> tuple[str, dict[str, object] | None]:
    raw = summary_payload.get("source_commit")
    summary_commit = raw if isinstance(raw, str) and raw else None
    override = explicit_source_commit.strip() if explicit_source_commit else None

    if summary_commit is not None:
        if not _COMMIT_RE.fullmatch(summary_commit):
            raise ValueError(f"Invalid source_commit in existing summary: {summary_commit!r}")
        if override is not None and override != summary_commit:
            raise ValueError(
                f"Explicit --source-commit {override} disagrees with summary source_commit {summary_commit}"
            )
        experiment_commit = summary_commit
        recovery = None
    else:
        if override is None:
            raise ValueError(
                "Existing A/B summary lacks source_commit; rerun finalizer with the known "
                "experiment HEAD via --source-commit"
            )
        if not _COMMIT_RE.fullmatch(override):
            raise ValueError(f"Invalid --source-commit: {override!r}")
        experiment_commit = override
        recovery = {
            "required": True,
            "reason": "inner_runner_git_probe_returned_null",
            "summary_source_commit": raw,
            "method": "explicit_known_experiment_head",
            "recovered_source_commit": override,
            "summary_mutated": False,
        }

    _require_experiment_commit_ancestor(experiment_commit, finalizer_commit)
    return experiment_commit, recovery


def _run_musicxml_comparison(summary: Path, output: Path) -> None:
    checked(
        [
            "docker",
            "exec",
            "-w",
            str(CONTAINER_ROOT),
            "-e",
            "PYTHONPATH=/workspace",
            CONTAINER,
            PIPELINE_PYTHON,
            "tools/issue294/compare_musicxml_ab.py",
            "--summary",
            str(container_path(summary)),
            "--output",
            str(container_path(output)),
        ],
        cwd=PROJECT_ROOT,
    )


def run(run_tag: str, source_commit: str | None = None) -> dict[str, str]:
    finalizer_commit = require_host_checkout()
    require_container()

    output_root = (PROJECT_ROOT / "logs/issue294" / run_tag).resolve()
    if not output_root.is_dir():
        raise FileNotFoundError(output_root)

    # A failed prior host-side write commonly leaves this directory root-owned.
    _restore_host_ownership(output_root)

    summary = output_root / "summary.json"
    if not summary.is_file():
        raise FileNotFoundError(summary)
    summary_payload = _load_mapping(summary)
    if summary_payload.get("status") != "completed":
        raise ValueError(f"Existing A/B summary is incomplete: {summary}")
    experiment_commit, source_commit_recovery = _resolve_experiment_commit(
        summary_payload,
        source_commit,
        finalizer_commit,
    )

    comparison = output_root / "comparison.json"
    if not comparison.exists():
        _run_comparator(summary, comparison)
    comparison_payload = _load_mapping(comparison)
    if comparison_payload.get("status") != "completed":
        raise ValueError(f"Existing comparison is incomplete: {comparison}")

    pinned_probe_path = output_root / "A_pinned_runtime_probe.json"
    if pinned_probe_path.exists():
        pinned_probe = _load_mapping(pinned_probe_path)
    else:
        pinned_probe = _run_pinned_runtime_probe(pinned_probe_path)
    if pinned_probe.get("status") != "completed" or pinned_probe.get("hard_contract_pass") is not True:
        raise RuntimeError(f"Pinned Stage-E runtime provenance gate failed: {pinned_probe_path}")

    # Container tools above may have created new root-owned files.
    _restore_host_ownership(output_root)

    provenance_path = output_root / "host_provenance.json"
    if provenance_path.exists():
        raise FileExistsError(provenance_path)
    pages_payload = summary_payload.get("pages")
    page_ids: list[str] = []
    if isinstance(pages_payload, list):
        for page in pages_payload:
            if not isinstance(page, dict):
                continue
            image = page.get("image")
            if isinstance(image, str):
                page_ids.append(Path(image).stem.removeprefix("page_"))
    provenance = {
        "schema_version": "issue294.same_original_host_provenance.v1",
        "source_commit": experiment_commit,
        "source_commit_recovery": source_commit_recovery,
        "finalized_by_commit": finalizer_commit,
        "branch": BRANCH,
        "develop": BASE_COMMIT,
        "container": CONTAINER,
        "image_id": EXPECTED_IMAGE_ID,
        "pages": page_ids,
        "summary": str(summary.relative_to(PROJECT_ROOT)),
        "comparison": str(comparison.relative_to(PROJECT_ROOT)),
        "pinned_runtime_probe": str(pinned_probe_path.relative_to(PROJECT_ROOT)),
        "pinned_runtime_hard_contract": True,
        "fixed_support_root": None,
        "fixed_support_replay": None,
        "recovered_existing_run": True,
    }
    provenance_path.write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    musicxml = output_root / "musicxml_comparison.json"
    if not musicxml.exists():
        _run_musicxml_comparison(summary, musicxml)
    musicxml_payload = _load_mapping(musicxml)
    if musicxml_payload.get("status") != "completed":
        raise ValueError(f"MusicXML comparison is incomplete: {musicxml}")

    _restore_host_ownership(output_root)
    return {
        "summary": str(summary),
        "comparison": str(comparison),
        "pinned_runtime_probe": str(pinned_probe_path),
        "provenance": str(provenance_path),
        "musicxml_comparison": str(musicxml),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument(
        "--source-commit",
        help=(
            "Known experiment HEAD used only to recover legacy runs whose summary source_commit "
            "is null. It must be an ancestor of the current branch HEAD."
        ),
    )
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.source_commit)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
