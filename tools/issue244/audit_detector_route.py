"""Audit Issue #244 detector route and local artifact provenance.

Temporary investigation helper. Delete before the final PR unless promoted to
maintained diagnostic tooling. Generated reports stay under ignored logs/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import yaml

SMOKE_RUN = Path("logs/issue236_pipeline_connected_review_smoke/corrected_20260709_125046")
STAGE_E_ROOT = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline")
WORK_ROOT = Path("logs/issue244_local_probe/detector_route_audit")
CONFIGS = {
    "smoke": SMOKE_RUN / "corrected_pipeline_config.json",
    "dense": Path("configs/dense_full_pipeline.yaml"),
    "evaluation2": Path("configs/evaluation2_e2e_verification_full.yaml"),
    "stage_e_generated": STAGE_E_ROOT / "stage_e_config.yaml",
}
MANIFESTS = {
    "smoke": SMOKE_RUN / "manifest.json",
    "stage_e": STAGE_E_ROOT / "manifest.json",
}
ROUTE_KEYS = [
    "precomputed_probe_candidates_root",
    "cnn_bands_from",
    "probe_use_original_images",
    "band_source",
    "band_cluster_max_dist",
    "ink_threshold",
    "min_ratio",
    "min_height_ratio",
    "min_width_ratio",
    "probe_width",
    "max_per_band",
    "enable_heuristic_filters",
    "candidate_filter_kwargs",
    "cnn_model_path",
    "cnn_threshold",
    "cnn_apply_nms",
    "divisi_rescue",
    "scan_gap_rescue",
    "scan_gap_threshold_ratio",
    "scan_gap_rescue_min_ratio",
    "scan_x_peak_rescue",
    "scan_rightmost_rescue",
    "scan_center_on_peak",
    "enable_sr",
    "sr_scale",
    "crop_recenter_on_bbox_ink",
]
IMPLEMENTATION_FILES = [
    "src/pipeline/detection/orchestrator.py",
    "src/pipeline/detection/config.py",
    "src/pipeline/detector_routes/dense_full_pipeline.py",
    "src/pipeline/steps/probe_scan.py",
    "src/pipeline/steps/candidate_filters.py",
    "src/pipeline/steps/cnn_scoring.py",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_data(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)


def route_signature(payload: Any) -> dict[str, Any]:
    detection = payload.get("detection", {}) if isinstance(payload, dict) else {}
    if not isinstance(detection, dict):
        detection = {}
    return {key: detection.get(key) for key in ROUTE_KEYS}


def config_summary(repo: Path, relative: Path) -> dict[str, Any]:
    path = repo / relative
    if not path.exists():
        return {"path": str(relative), "exists": False}
    payload = load_data(path)
    return {
        "path": str(relative),
        "exists": True,
        "sha256": sha256_file(path),
        "route_signature": route_signature(payload),
    }


def manifest_summary(repo: Path, relative: Path) -> dict[str, Any]:
    path = repo / relative
    if not path.exists():
        return {"path": str(relative), "exists": False}
    payload = load_data(path)
    pages = payload.get("pages", []) if isinstance(payload, dict) else []
    config = payload.get("config", {}) if isinstance(payload, dict) else {}
    return {
        "path": str(relative),
        "exists": True,
        "sha256": sha256_file(path),
        "route_signature": route_signature(config),
        "commands": payload.get("commands") if isinstance(payload, dict) else None,
        "pages": [
            {
                "page_id": item.get("page_id"),
                "image": item.get("image"),
                "barlines_json": item.get("barlines_json"),
            }
            for item in pages
            if isinstance(item, dict)
        ],
    }


def git_metadata(repo: Path) -> dict[str, Any]:
    git = shutil.which("git")
    if git is None:
        return {
            "available": False,
            "reason": "git executable is not installed in this runtime",
            "branch": None,
            "head": None,
            "status_short": None,
        }

    def run(*args: str) -> dict[str, Any]:
        result = subprocess.run(
            [git, *args],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }

    branch = run("branch", "--show-current")
    head = run("rev-parse", "HEAD")
    status = run("status", "--short")
    return {
        "available": True,
        "branch": branch["stdout"] or None,
        "head": head["stdout"] or None,
        "status_short": status["stdout"],
        "diagnostics": {"branch": branch, "head": head, "status": status},
    }


def implementation_summary(repo: Path) -> dict[str, Any]:
    current = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        current[relative] = {
            "exists": path.exists(),
            "sha256": sha256_file(path) if path.exists() else None,
        }
    return {
        "current": current,
        "historical_commit_comparison": {
            "status": (
                "not_run_git_unavailable"
                if shutil.which("git") is None
                else "deferred_to_github_audit"
            ),
            "note": (
                "Current hashes are recorded here. Historical commit comparison "
                "is performed separately against GitHub checkpoints."
            ),
        },
    }


def find_artifacts(repo: Path, relative_root: Path) -> list[dict[str, Any]]:
    root = repo / relative_root
    if not root.exists():
        return []
    records = []
    for path in sorted(root.rglob("*.json")):
        name = path.name.lower()
        lower = str(path).lower()
        relevant = "barline" in name or name in {
            "pipeline2_no_peak_candidates.json",
            "pipeline2_no_peak_filtered.json",
            "pipeline2_no_peak_filtered_cnn.json",
            "pipeline2_no_peak_scored.json",
        }
        if relevant and ("page_001" in lower or "symphony1" in lower or relative_root == SMOKE_RUN):
            records.append(
                {
                    "path": str(path.relative_to(repo)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return records


def signature_diff(left: dict[str, Any], right: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: {"smoke": left.get(key), "reference": right.get(key)}
        for key in ROUTE_KEYS
        if left.get(key) != right.get(key)
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    diff = report["comparisons"]["smoke_vs_dense"]
    lines = [
        "# Issue #244 detector route audit",
        "",
        f"- git available in runtime: `{report['git']['available']}`",
        f"- branch: `{report['git'].get('branch')}`",
        f"- head: `{report['git'].get('head')}`",
        f"- same route signature as dense config: `{not bool(diff)}`",
        f"- differing route fields: `{len(diff)}`",
        "",
        "## Differing route fields",
        "",
    ]
    for key, values in diff.items():
        lines.append(f"- `{key}`: smoke=`{values['smoke']}` / dense=`{values['reference']}`")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The high-accuracy wrapper injects precomputed dense candidates, "
            "dense CNN bands, and original-image probe mode.",
            "- When those keys are absent, DetectorOrchestrator regenerates "
            "ordinary hybrid/probe candidates instead.",
            "- Current implementation hashes are recorded even when git is "
            "unavailable inside the container.",
            "",
            "See `detector_route_audit.json` for config hashes, manifest commands, "
            "artifact hashes, and implementation hashes.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo = Path.cwd().resolve()
    work = repo / WORK_ROOT
    if work.exists() and args.force:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

    configs = {name: config_summary(repo, path) for name, path in CONFIGS.items()}
    manifests = {name: manifest_summary(repo, path) for name, path in MANIFESTS.items()}
    smoke_signature = configs["smoke"].get("route_signature", {})
    dense_signature = configs["dense"].get("route_signature", {})
    stage_signature = configs["stage_e_generated"].get("route_signature", {})

    report = {
        "schema": "issue244.detector_route_audit.v2",
        "git": git_metadata(repo),
        "configs": configs,
        "manifests": manifests,
        "comparisons": {
            "smoke_vs_dense": signature_diff(smoke_signature, dense_signature),
            "smoke_vs_generated_stage_e": (
                signature_diff(smoke_signature, stage_signature) if stage_signature else None
            ),
        },
        "artifacts": {
            "smoke": find_artifacts(repo, SMOKE_RUN),
            "stage_e": find_artifacts(repo, STAGE_E_ROOT),
            "golden": find_artifacts(repo, Path("data/evaluation2/golden_baseline_eval2_bc23deb")),
        },
        "implementation": implementation_summary(repo),
        "interpretation": {
            "same_route_as_dense_config": not bool(
                signature_diff(smoke_signature, dense_signature)
            ),
            "stage_e_injected_keys": (
                {
                    key: stage_signature.get(key)
                    for key in (
                        "precomputed_probe_candidates_root",
                        "cnn_bands_from",
                        "probe_use_original_images",
                    )
                }
                if stage_signature
                else None
            ),
        },
    }

    json_path = work / "detector_route_audit.json"
    markdown_path = work / "detector_route_audit.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, markdown_path)

    zip_path = work.with_name(f"{work.name}_review.zip")
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(json_path, json_path.relative_to(repo))
        archive.write(markdown_path, markdown_path.relative_to(repo))
        for relative in (*CONFIGS.values(), *MANIFESTS.values()):
            path = repo / relative
            if path.exists():
                archive.write(path, path.relative_to(repo))

    print(f"Route audit: {markdown_path.relative_to(repo)}")
    print(f"JSON report: {json_path.relative_to(repo)}")
    print(f"Review zip: {zip_path.relative_to(repo)}")
    print("Git available in runtime:", report["git"]["available"])
    print(
        "Same route signature as dense config:",
        report["interpretation"]["same_route_as_dense_config"],
    )
    print(
        "Differing route fields:",
        len(report["comparisons"]["smoke_vs_dense"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
