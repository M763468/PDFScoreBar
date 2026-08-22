"""Validate Issue #283 thin-barline vectorization on retained Phase-1 x4 inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
PAGES = ("page_012.png", "page_013.png", "page_014.png")
ARTIFACT_FIELDS = (
    "current_sr_detection",
    "staff_mask",
    "connector_symbols",
    "connector_brace_dot",
)


def _require_canonical_container() -> None:
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Issue #283 validation must run inside pdfscore_pipeline_gpu")
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


def _discover_baselines(phase1_run: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in phase1_run.rglob("current_homr_result.json"):
        payload = _load_json(path)
        page = Path(str(payload.get("image", ""))).name
        if page not in PAGES:
            continue
        if page in found:
            raise RuntimeError(f"Multiple baseline current-HOMR results for {page}")
        found[page] = (path, payload)
    missing = [page for page in PAGES if page not in found]
    if missing:
        raise FileNotFoundError(
            "Missing retained Phase-1 current-HOMR baseline(s): " + ", ".join(missing)
        )
    return found


def _artifact_hashes(payload: dict[str, Any]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for field in ARTIFACT_FIELDS:
        raw = payload.get(field)
        if not raw:
            raise ValueError(f"Result lacks artifact field {field}")
        path = Path(str(raw))
        if not path.is_file():
            raise FileNotFoundError(path)
        hashes[field] = _sha256(path)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase1-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    _require_canonical_container()
    phase1_run = args.phase1_run.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baselines = _discover_baselines(phase1_run)

    page_results: dict[str, Any] = {}
    all_equal = True
    for page in PAGES:
        baseline_path, baseline = baselines[page]
        image = Path(str(baseline["image"]))
        sr_image = Path(str(baseline["sr_image"]))
        if not image.is_file():
            raise FileNotFoundError(image)
        if not sr_image.is_file():
            raise FileNotFoundError(sr_image)

        page_output = output / Path(page).stem
        command = [
            str(PIPELINE_PYTHON),
            "tools/issue283/run_current_homr_replay.py",
            "--image",
            str(image),
            "--sr-image",
            str(sr_image),
            "--output",
            str(page_output),
            "--run-id",
            f"issue283_vectorized_{Path(page).stem}",
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        (page_output / "runner.stdout.log").write_text(
            completed.stdout[-200_000:], encoding="utf-8"
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Current-HOMR replay failed for {page} ({completed.returncode})\n"
                + "\n".join(completed.stdout.splitlines()[-80:])
            )

        current = _load_json(page_output / "result.json")
        baseline_hashes = _artifact_hashes(baseline)
        current_hashes = _artifact_hashes(current)
        comparison = {
            field: {
                "baseline_sha256": baseline_hashes[field],
                "current_sha256": current_hashes[field],
                "equal": baseline_hashes[field] == current_hashes[field],
            }
            for field in ARTIFACT_FIELDS
        }
        page_equal = all(item["equal"] for item in comparison.values())
        all_equal = all_equal and page_equal
        compact = _load_json(page_output / "compact_summary.json")
        stages = compact.get("stage_summary", {})
        page_results[page] = {
            "baseline_result": str(baseline_path),
            "baseline_sr_image": str(sr_image),
            "worker_wall_sec": compact.get("worker_wall_sec"),
            "synchronized_prediction_sec": stages.get(
                "current_homr_worker.synchronized_prediction", {}
            ).get("total_duration_sec"),
            "thin_barline_detection_sec": stages.get(
                "current_homr.post.thin_barline_detection", {}
            ).get("total_duration_sec"),
            "artifact_comparison": comparison,
            "all_artifacts_equal": page_equal,
        }

    summary = {
        "schema_version": "issue283.thin_barline_vectorization_validation.v1",
        "phase1_run": str(phase1_run),
        "pages": page_results,
        "all_artifacts_equal": all_equal,
    }
    summary_path = output / "validation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if all_equal else 2


if __name__ == "__main__":
    raise SystemExit(main())
