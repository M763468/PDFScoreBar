"""Validate Issue #283 current-HOMR output across the canonical retained full-68 set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from tools.issue120.eval_full68_from_intermediates import SCORES

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
ARTIFACT_FIELDS = (
    "current_sr_detection",
    "staff_mask",
    "connector_symbols",
    "connector_brace_dot",
)


def _require_canonical_container() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Issue #283 full-68 validation must run inside pdfscore_pipeline_gpu")
    if ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError(f"Expected repository mount at /workspace, got {ROOT}")
    if not PIPELINE_PYTHON.is_file():
        raise RuntimeError(f"Missing canonical interpreter: {PIPELINE_PYTHON}")
    if not Path(sys.executable).as_posix().startswith("/opt/venv_pipeline/"):
        raise RuntimeError(f"Runner must use /opt/venv_pipeline/bin/python, got {sys.executable}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _expected_keys() -> list[tuple[str, str]]:
    return [(score, page) for score, pages in SCORES.items() for page in pages]


def _visible_path(raw: Any) -> Path:
    path = Path(str(raw))
    candidates = [path if path.is_absolute() else ROOT / path]
    if path.is_absolute():
        parts = path.parts
        for marker in ("logs", "data", "configs", "tools"):
            if marker in parts:
                index = parts.index(marker)
                candidates.append(ROOT / Path(*parts[index:]))
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def _canonical_key(payload: dict[str, Any]) -> tuple[str, str] | None:
    raw = payload.get("image")
    if not raw:
        return None
    image = _visible_path(raw)
    key = (image.parent.name, image.stem)
    return key if key in set(_expected_keys()) else None


def _candidate_payload(path: Path) -> tuple[tuple[str, str], dict[str, Any]] | None:
    try:
        payload = _load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    key = _canonical_key(payload)
    if key is None:
        return None
    return key, payload


def _scan_root(root: Path) -> list[tuple[Path, tuple[str, str], dict[str, Any]]]:
    rows: list[tuple[Path, tuple[str, str], dict[str, Any]]] = []
    for path in root.rglob("current_homr_result.json"):
        parsed = _candidate_payload(path)
        if parsed is None:
            continue
        key, payload = parsed
        rows.append((path.resolve(), key, payload))
    return rows


def _discover_baseline_root(
    search_root: Path,
) -> tuple[Path, dict[tuple[str, str], tuple[Path, dict[str, Any]]], dict[str, Any]]:
    search_root = search_root.resolve()
    expected = set(_expected_keys())
    rows = _scan_root(search_root)
    grouped: dict[Path, dict[tuple[str, str], list[tuple[Path, dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for result_path, key, payload in rows:
        ancestor = result_path.parent
        while True:
            try:
                ancestor.relative_to(search_root)
            except ValueError:
                break
            grouped[ancestor][key].append((result_path, payload))
            if ancestor == search_root:
                break
            ancestor = ancestor.parent

    complete: list[tuple[Path, dict[tuple[str, str], tuple[Path, dict[str, Any]]]]] = []
    for root, by_key in grouped.items():
        if set(by_key) != expected:
            continue
        if any(len(items) != 1 for items in by_key.values()):
            continue
        complete.append((root, {key: items[0] for key, items in by_key.items()}))

    leaf_complete = []
    for root, items in complete:
        has_complete_descendant = any(
            other != root and root in other.parents for other, _ in complete
        )
        if not has_complete_descendant:
            leaf_complete.append((root, items))

    discovery = {
        "schema_version": "issue283.full68_current_homr.discovery.v1",
        "search_root": str(search_root),
        "candidate_result_files": len(rows),
        "complete_roots": [str(root) for root, _ in complete],
        "leaf_complete_roots": [str(root) for root, _ in leaf_complete],
        "expected_pages": len(expected),
    }
    if len(leaf_complete) != 1:
        roots = [str(root) for root, _ in leaf_complete]
        raise RuntimeError(
            "Expected exactly one independent complete 68-page current-HOMR baseline root; "
            f"found {len(leaf_complete)} from {len(rows)} candidate result files: {roots}"
        )
    return leaf_complete[0][0], leaf_complete[0][1], discovery


def _load_explicit_baseline(
    baseline_root: Path,
) -> tuple[dict[tuple[str, str], tuple[Path, dict[str, Any]]], dict[str, Any]]:
    baseline_root = baseline_root.resolve()
    expected = set(_expected_keys())
    grouped: dict[tuple[str, str], list[tuple[Path, dict[str, Any]]]] = defaultdict(list)
    rows = _scan_root(baseline_root)
    for result_path, key, payload in rows:
        grouped[key].append((result_path, payload))

    missing = sorted(expected - set(grouped))
    duplicates = {
        f"{score}/{page}": [str(path) for path, _ in items]
        for (score, page), items in grouped.items()
        if len(items) != 1
    }
    if missing or duplicates:
        raise RuntimeError(
            "Explicit baseline root is not a unique canonical full-68 set: "
            f"missing={len(missing)} duplicates={len(duplicates)}"
        )
    selected = {key: grouped[key][0] for key in expected}
    discovery = {
        "schema_version": "issue283.full68_current_homr.discovery.v1",
        "explicit_baseline_root": str(baseline_root),
        "candidate_result_files": len(rows),
        "expected_pages": len(expected),
        "missing": [f"{score}/{page}" for score, page in missing],
        "duplicates": duplicates,
    }
    return selected, discovery


def _artifact_hashes(payload: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for field in ARTIFACT_FIELDS:
        raw = payload.get(field)
        if not raw:
            raise ValueError(f"Result lacks artifact field {field}")
        path = _visible_path(raw)
        if not path.is_file():
            raise FileNotFoundError(path)
        hashes[field] = _sha256(path)
    return hashes


def _preflight_entry(
    key: tuple[str, str],
    result_path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    score, page = key
    image = _visible_path(payload.get("image"))
    sr_image = _visible_path(payload.get("sr_image"))
    expected_image = (ROOT / "data/evaluation2/images" / score / f"{page}.png").resolve()
    if image != expected_image:
        raise RuntimeError(f"{score}/{page}: baseline image mismatch: {image} != {expected_image}")
    if not image.is_file():
        raise FileNotFoundError(image)
    if not sr_image.is_file():
        raise FileNotFoundError(sr_image)
    if payload.get("connector_complete") is not True:
        raise RuntimeError(f"{score}/{page}: connector_complete is not true")
    hashes = _artifact_hashes(payload)
    return {
        "score": score,
        "page": page,
        "baseline_result": str(result_path),
        "image": str(image),
        "sr_image": str(sr_image),
        "sr_sha256": _sha256(sr_image),
        "baseline_artifact_hashes": hashes,
    }


def _stage_duration(compact: dict[str, Any], name: str) -> float | None:
    stages = compact.get("stage_summary")
    if not isinstance(stages, dict):
        return None
    stage = stages.get(name)
    if not isinstance(stage, dict):
        return None
    value = stage.get("total_duration_sec")
    return float(value) if value is not None else None


def _current_commit() -> str | None:
    configured = os.environ.get("PDFSCORE_ISSUE283_GIT_COMMIT")
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _resume_result(
    path: Path,
    *,
    baseline_result: Path,
    commit: str | None,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = _load_json(path)
    if payload.get("baseline_result") != str(baseline_result):
        return None
    if payload.get("commit") != commit:
        return None
    if payload.get("all_artifacts_equal") is not True:
        return None
    return payload


def _run_page(
    *,
    entry: dict[str, Any],
    output: Path,
    commit: str | None,
    resume: bool,
) -> dict[str, Any]:
    score = str(entry["score"])
    page = str(entry["page"])
    baseline_result = Path(str(entry["baseline_result"]))
    page_output = output / "pages" / score / page
    page_output.mkdir(parents=True, exist_ok=True)
    page_result_path = page_output / "page_result.json"
    if resume:
        cached = _resume_result(
            page_result_path,
            baseline_result=baseline_result,
            commit=commit,
        )
        if cached is not None:
            print(f"RESUME {score}/{page}: exact", flush=True)
            return cached

    replay_output = page_output / "replay"
    command = [
        str(PIPELINE_PYTHON),
        "tools/issue283/run_current_homr_replay.py",
        "--image",
        str(entry["image"]),
        "--sr-image",
        str(entry["sr_image"]),
        "--output",
        str(replay_output),
        "--run-id",
        f"issue283_full68_{score}_{page}",
    ]
    print(f"RUN {score}/{page}", flush=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (page_output / "runner.stdout.log").write_text(
        completed.stdout[-200_000:],
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Current-HOMR replay failed for {score}/{page} ({completed.returncode})\n"
            + "\n".join(completed.stdout.splitlines()[-80:])
        )

    current = _load_json(replay_output / "result.json")
    compact = _load_json(replay_output / "compact_summary.json")
    current_hashes = _artifact_hashes(current)
    comparison = {
        field: {
            "baseline_sha256": entry["baseline_artifact_hashes"][field],
            "current_sha256": current_hashes[field],
            "equal": entry["baseline_artifact_hashes"][field] == current_hashes[field],
        }
        for field in ARTIFACT_FIELDS
    }
    exact = all(item["equal"] for item in comparison.values())
    result = {
        "score": score,
        "page": page,
        "baseline_result": str(baseline_result),
        "commit": commit,
        "worker_wall_sec": compact.get("worker_wall_sec"),
        "synchronized_prediction_sec": _stage_duration(
            compact,
            "current_homr_worker.synchronized_prediction",
        ),
        "thin_barline_detection_sec": _stage_duration(
            compact,
            "current_homr.post.thin_barline_detection",
        ),
        "resource_summary": compact.get("resource_summary"),
        "artifact_comparison": comparison,
        "all_artifacts_equal": exact,
    }
    page_result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if exact:
        shutil.rmtree(replay_output / "current_homr_output", ignore_errors=True)
        shutil.rmtree(replay_output / "traces", ignore_errors=True)
        for transient in ("resource_samples.jsonl", "stage_timings.json"):
            (replay_output / transient).unlink(missing_ok=True)
    print(f"DONE {score}/{page}: exact={exact}", flush=True)
    return result


def _mean_present(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return mean(values) if values else None


def _write_summary(
    *,
    output: Path,
    baseline_root: Path,
    discovery: dict[str, Any],
    preflight: list[dict[str, Any]],
    page_results: list[dict[str, Any]],
    commit: str | None,
) -> dict[str, Any]:
    changed = [
        f"{row['score']}/{row['page']}" for row in page_results if not row["all_artifacts_equal"]
    ]
    summary = {
        "schema_version": "issue283.full68_current_homr_validation.v1",
        "commit": commit,
        "dirty": os.environ.get("PDFSCORE_ISSUE283_GIT_DIRTY"),
        "docker_image": os.environ.get(
            "PDFSCORE_ISSUE281_DOCKER_IMAGE",
            "pdfscore_pipeline_gpu",
        ),
        "docker_image_identity": os.environ.get("PDFSCORE_ISSUE281_DOCKER_IMAGE_IDENTITY"),
        "baseline_root": str(baseline_root),
        "expected_pages": len(_expected_keys()),
        "preflight_pages": len(preflight),
        "evaluated_pages": len(page_results),
        "all_artifacts_equal": len(page_results) == len(_expected_keys()) and not changed,
        "changed_pages": changed,
        "timing": {
            "mean_worker_wall_sec": _mean_present(page_results, "worker_wall_sec"),
            "mean_synchronized_prediction_sec": _mean_present(
                page_results,
                "synchronized_prediction_sec",
            ),
            "mean_thin_barline_detection_sec": _mean_present(
                page_results,
                "thin_barline_detection_sec",
            ),
        },
        "discovery": discovery,
    }
    (output / "page_results.json").write_text(
        json.dumps(page_results, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "validation_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", type=Path, default=ROOT / "logs")
    parser.add_argument("--baseline-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    _require_canonical_container()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    discovery_path = output / "discovery.json"

    try:
        if args.baseline_root is not None:
            selected, discovery = _load_explicit_baseline(args.baseline_root)
            baseline_root = args.baseline_root.resolve()
        else:
            baseline_root, selected, discovery = _discover_baseline_root(args.search_root)
        discovery_path.write_text(json.dumps(discovery, indent=2) + "\n", encoding="utf-8")
    except Exception as error:
        if not discovery_path.exists():
            discovery_path.write_text(
                json.dumps(
                    {
                        "schema_version": "issue283.full68_current_homr.discovery_failure.v1",
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        raise

    preflight = [_preflight_entry(key, *selected[key]) for key in _expected_keys()]
    (output / "preflight.json").write_text(
        json.dumps(preflight, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"PREFLIGHT OK: {len(preflight)} pages from {baseline_root}", flush=True)
    if args.preflight_only:
        return 0

    commit = _current_commit()
    page_results: list[dict[str, Any]] = []
    for entry in preflight:
        result = _run_page(
            entry=entry,
            output=output,
            commit=commit,
            resume=args.resume,
        )
        page_results.append(result)
        _write_summary(
            output=output,
            baseline_root=baseline_root,
            discovery=discovery,
            preflight=preflight,
            page_results=page_results,
            commit=commit,
        )

    summary = _write_summary(
        output=output,
        baseline_root=baseline_root,
        discovery=discovery,
        preflight=preflight,
        page_results=page_results,
        commit=commit,
    )
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if summary["all_artifacts_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
