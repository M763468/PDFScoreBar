#!/usr/bin/env python3
"""Validate and normalize an Issue #255 batch failed only by allowed untracked files."""

from __future__ import annotations

import argparse
import copy
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

EXPECTED_FRESH = {
    "mode": "fresh_upstream",
    "fresh_upstream_authoritative": True,
    "override_keys": [],
}
DIRTY_ERROR = "repository was dirty during run"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _untracked_paths(status: str) -> list[str]:
    lines = [line for line in status.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Repository status is empty; no untracked-only waiver is needed")
    paths = []
    for line in lines:
        if not line.startswith("?? "):
            raise ValueError(f"Repository status contains a tracked change: {line}")
        path = line[3:].strip()
        if not path:
            raise ValueError(f"Invalid untracked status line: {line!r}")
        paths.append(path)
    return paths


def _is_allowed(path: str, prefixes: Sequence[str]) -> bool:
    normalized = path.lstrip("./")
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def normalize_batch(
    *,
    payload: Mapping[str, Any],
    allowed_untracked_prefixes: Sequence[str],
) -> dict[str, Any]:
    if payload.get("schema_version") != "issue255.focused_fresh_batch.v1":
        raise ValueError("Unsupported focused batch schema")
    if payload.get("status") != "failed":
        raise ValueError("Input batch must have status='failed'")
    if not allowed_untracked_prefixes:
        raise ValueError("At least one allowed untracked prefix is required")

    expected_commit = payload.get("expected_commit")
    expected_branch = payload.get("expected_branch")
    if not isinstance(expected_commit, str) or not expected_commit:
        raise ValueError("Batch expected_commit is missing")
    if not isinstance(expected_branch, str) or not expected_branch:
        raise ValueError("Batch expected_branch is missing")

    top_errors = payload.get("errors")
    if not isinstance(top_errors, list) or not top_errors:
        raise ValueError("Failed batch lacks errors")
    if any(not isinstance(error, str) or not error.endswith(DIRTY_ERROR) for error in top_errors):
        raise ValueError(f"Batch contains a non-waivable error: {top_errors}")

    runs = payload.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("Focused batch must contain exactly two runs")

    normalized = copy.deepcopy(dict(payload))
    all_untracked: list[str] = []
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            raise ValueError(f"Run {index} is invalid")
        if run.get("runner_exit_code") != 0:
            raise ValueError(f"Run {index} did not exit successfully")
        if run.get("errors") != [DIRTY_ERROR]:
            raise ValueError(f"Run {index} contains non-waivable errors: {run.get('errors')}")

        contract = run.get("contract")
        if not isinstance(contract, Mapping) or contract.get("status") != "completed":
            raise ValueError(f"Run {index} contract is not completed")
        fresh = contract.get("detector_input_contract")
        if not isinstance(fresh, Mapping) or any(
            fresh.get(key) != value for key, value in EXPECTED_FRESH.items()
        ):
            raise ValueError(f"Run {index} fresh detector contract is invalid")
        if contract.get("detection_config_changed") is not False:
            raise ValueError(f"Run {index} changed detection configuration")
        if contract.get("pipeline_steps_changed") is not False:
            raise ValueError(f"Run {index} changed pipeline steps")

        repository = contract.get("repository")
        if not isinstance(repository, Mapping):
            raise ValueError(f"Run {index} repository provenance is missing")
        if repository.get("commit") != expected_commit:
            raise ValueError(f"Run {index} repository commit mismatch")
        if repository.get("branch") != expected_branch:
            raise ValueError(f"Run {index} repository branch mismatch")
        status = repository.get("status")
        if not isinstance(status, str):
            raise ValueError(f"Run {index} repository status is missing")
        paths = _untracked_paths(status)
        disallowed = [path for path in paths if not _is_allowed(path, allowed_untracked_prefixes)]
        if disallowed:
            raise ValueError(f"Run {index} contains disallowed untracked paths: {disallowed}")
        all_untracked.extend(paths)

        artifacts = contract.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"Run {index} artifact inventory is missing")
        missing = [
            name
            for name, record in artifacts.items()
            if name != "clef_mask"
            and (not isinstance(record, Mapping) or record.get("exists") is not True)
        ]
        if missing:
            raise ValueError(f"Run {index} is missing artifacts: {sorted(missing)}")

        normalized_run = normalized["runs"][index]
        normalized_run["original_errors"] = list(normalized_run.get("errors", []))
        normalized_run["errors"] = []

    normalized["original_status"] = payload.get("status")
    normalized["original_errors"] = list(top_errors)
    normalized["status"] = "completed"
    normalized["errors"] = []
    normalized["provenance_adjustment"] = {
        "schema_version": "issue255.untracked_only_batch_adjustment.v1",
        "reason": "batch failed only because explicitly allowed untracked paths were recorded",
        "allowed_untracked_prefixes": list(allowed_untracked_prefixes),
        "observed_untracked_paths": sorted(set(all_untracked)),
        "tracked_repository_state_accepted": True,
        "runtime_artifacts_reused": True,
    }
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-untracked-prefix",
        action="append",
        default=[],
        help="Allowed untracked path prefix. Repeat for multiple prefixes.",
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError(args.output)
        payload = _load_json(args.input.resolve())
        if not isinstance(payload, Mapping):
            raise ValueError("Input batch must be a JSON object")
        normalized = normalize_batch(
            payload=payload,
            allowed_untracked_prefixes=args.allow_untracked_prefix,
        )
        _write_json(args.output.resolve(), normalized)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "completed",
                "output": str(args.output.resolve()),
                "observed_untracked_paths": normalized["provenance_adjustment"][
                    "observed_untracked_paths"
                ],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
