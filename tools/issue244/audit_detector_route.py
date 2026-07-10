"""Audit Issue #244 detector route, artifacts, and implementation provenance.

Temporary investigation helper. Delete before the final PR unless promoted to
maintained diagnostic tooling. Generated reports stay under ignored logs/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

import yaml

SMOKE_RUN = Path(
    "logs/issue236_pipeline_connected_review_smoke/corrected_20260709_125046"
)
DENSE_CONFIG = Path("configs/dense_full_pipeline.yaml")
EVAL_CONFIG = Path("configs/evaluation2_e2e_verification_full.yaml")
STAGE_E_ROOT = Path("logs/issue120_e2e_recovery/stage_e_full_pipeline")
WORK_ROOT = Path("logs/issue244_local_probe/detector_route_audit")
CHECKPOINTS = {
    "dense_runtime_equivalence_pr178": "0d38f70b818722160d6c785f12e2d577622ef9d6",
    "issue206_baseline_audit": "fbd521af433b3e8b081761f84104e4d7e9d5a1d2",
}
IMPLEMENTATION_FILES = [
    "src/pipeline/detection/orchestrator.py",
    "src/pipeline/detection/config.py",
    "src/pipeline/detector_routes/dense_full_pipeline.py",
    "src/pipeline/steps/probe_scan.py",
    "src/pipeline/steps/candidate_filters.py",
    "src/pipeline/steps/cnn_scoring.py",
]
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


def run_git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_structured(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def detection_from(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    detection = payload.get("detection")
    return detection if isinstance(detection, dict) else {}


def route_signature(detection: dict[str, Any]) -> dict[str, Any]:
    return {key: detection.get(key) for key in ROUTE_KEYS}


def config_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    payload = load_structured(path)
    return {
        "path": str(path),
        "exists": True,
        "sha256": sha256_file(path),
        "route_signature": route_signature(detection_from(payload)),
    }


def manifest_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    payload = load_structured(path)
    config = payload.get("config") if isinstance(payload, dict) else None
    pages = payload.get("pages") if isinstance(payload, dict) else None
    page_records = pages if isinstance(pages, list) else []
    return {
        "path": str(path),
        "exists": True,
        "sha256": sha256_file(path),
        "route_signature": route_signature(detection_from(config)),
        "commands": payload.get("commands") if isinstance(payload, dict) else None,
        "page_count": len(page_records),
        "pages": [
            {
                "page_id": item.get("page_id"),
                "image": item.get("image"),
                "barlines_json": item.get("barlines_json"),
            }
            for item in page_records
            if isinstance(item, dict)
        ],
    }


def find_target_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    names = {
        "pipeline2_no_peak_candidates.json",
        "pipeline2_no_peak_filtered.json",
        "pipeline2_no_peak_filtered_cnn.json",
        "pipeline2_no_peak_scored.json",
        "barlines_review.json",
        "barlines_corrected.json",
    }
    result: list[Path] = []
    for path in root.rglob("*.json"):
        lower = str(path).lower()
        if path.name in names or "barline" in path.name.lower():
            if "page_001" in lower or "symphony1" in lower or root == SMOKE_RUN:
                result.append(path)
    return sorted(set(result))


def bbox_from_item(item: Any) -> list[float] | None:
    if isinstance(item, dict):
        value = item.get("bbox") or item.get("box") or item.get("pred_bbox")
    elif isinstance(item, list) and len(item) == 4:
        value = item
    else:
        value = None
    if isinstance(value, list) and len(value) == 4:
        try:
            return [float(v) for v in value]
        except (TypeError, ValueError):
            return None
    return None


def records_from_payload(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in (
            "predictions",
            "boxes",
            "barlines",
            "candidates",
            "results",
            "items",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def artifact_summary(path: Path) -> dict[str, Any]:
    try:
        payload = load_structured(path)
        records = records_from_payload(payload)
        boxes = [bbox for item in records if (bbox := bbox_from_item(item)) is not None]
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "record_count": len(records),
            "bbox_count": len(boxes),
            "x_centers": [round((b[0] + b[2]) / 2.0, 2) for b in boxes],
        }
    except Exception as exc:
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "error": f"{type(exc).__name__}: {exc}",
        }


def implementation_summary(repo_root: Path) -> dict[str, Any]:
    current: dict[str, Any] = {}
    checkpoints: dict[str, Any] = {}

    for rel in IMPLEMENTATION_FILES:
        path = repo_root / rel
        current[rel] = {
            "exists": path.exists(),
            "sha256": sha256_file(path) if path.exists() else None,
        }

    for label, commit in CHECKPOINTS.items():
        files: dict[str, Any] = {}
        for rel in IMPLEMENTATION_FILES:
            spec = f"{commit}:{rel}"
            exists = (
                subprocess.run(
                    ["git", "cat-file", "-e", spec],
                    capture_output=True,
                    check=False,
                ).returncode
                == 0
            )
            record: dict[str, Any] = {"exists": exists}
            if exists:
                data = subprocess.run(
                    ["git", "show", spec],
                    capture_output=True,
                    check=True,
                ).stdout
                record["sha256"] = sha256_bytes(data)
                record["same_as_current"] = (
                    current.get(rel, {}).get("sha256") == record["sha256"]
                )
                record["numstat_to_head"] = run_git(
                    "diff", "--numstat", commit, "HEAD", "--", rel, check=False
                )
            files[rel] = record
        checkpoints[label] = {"commit": commit, "files": files}

    return {"current": current, "checkpoints": checkpoints}


def diff_signatures(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        key: {"left": left.get(key), "right": right.get(key)}
        for key in ROUTE_KEYS
        if left.get(key) != right.get(key)
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    smoke = report["configs"]["smoke"]
    dense = report["configs"]["dense"]
    diff = report["comparisons"]["smoke_vs_dense_route_signature"]
    lines = [
        "# Issue #244 detector route audit",
        "",
        f"- branch: `{report['git']['branch']}`",
        f"- head: `{report['git']['head']}`",
        f"- smoke config: `{smoke['path']}`",
        f"- dense config: `{dense['path']}`",
        "",
        "## Route verdict",
        "",
        f"- same route signature: `{not bool(diff)}`",
        f"- differing route fields: `{len(diff)}`",
        "- high-accuracy Stage E wrapper injects dense candidate roots and original-image probe mode; "
        "absence of those keys means the ordinary hybrid/probe route is used.",
        "",
        "## Differing route fields",
        "",
    ]
    for key, values in diff.items():
        lines.append(
            f"- `{key}`: smoke=`{values['left']}` / dense=`{values['right']}`"
        )
    lines.extend(
        [
            "",
            "## Local historical artifacts",
            "",
            f"- Stage E root exists: `{report['local_artifacts']['stage_e_root_exists']}`",
            f"- discovered smoke artifacts: `{len(report['artifacts']['smoke'])}`",
            f"- discovered Stage E artifacts: `{len(report['artifacts']['stage_e'])}`",
            f"- discovered tracked golden artifacts: `{len(report['artifacts']['golden'])}`",
            "",
            "See `detector_route_audit.json` for hashes, commands, artifact counts, and implementation diffs.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    work_root = repo_root / WORK_ROOT
    if work_root.exists() and args.force:
        for child in work_root.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()
    work_root.mkdir(parents=True, exist_ok=True)

    smoke_config = repo_root / SMOKE_RUN / "corrected_pipeline_config.json"
    smoke_manifest = repo_root / SMOKE_RUN / "manifest.json"
    stage_e_config = repo_root / STAGE_E_ROOT / "stage_e_config.yaml"
    stage_e_manifest = repo_root / STAGE_E_ROOT / "manifest.json"

    configs = {
        "smoke": config_summary(smoke_config),
        "dense": config_summary(repo_root / DENSE_CONFIG),
        "evaluation2": config_summary(repo_root / EVAL_CONFIG),
        "stage_e_generated": config_summary(stage_e_config),
    }
    manifests = {
        "smoke": manifest_summary(smoke_manifest),
        "stage_e": manifest_summary(stage_e_manifest),
    }

    smoke_signature = configs["smoke"].get("route_signature", {})
    dense_signature = configs["dense"].get("route_signature", {})
    stage_e_signature = configs["stage_e_generated"].get("route_signature", {})

    golden_root = repo_root / "data/evaluation2/golden_baseline_eval2_bc23deb"
    artifacts = {
        "smoke": [
            artifact_summary(path)
            for path in find_target_files(repo_root / SMOKE_RUN)
        ],
        "stage_e": [
            artifact_summary(path)
            for path in find_target_files(repo_root / STAGE_E_ROOT)
        ],
        "golden": [
            artifact_summary(path)
            for path in find_target_files(golden_root)
        ],
    }

    report = {
        "schema": "issue244.detector_route_audit.v1",
        "temporary_script": str(Path(__file__).relative_to(repo_root)),
        "git": {
            "branch": run_git("branch", "--show-current"),
            "head": run_git("rev-parse", "HEAD"),
            "status_short": run_git("status", "--short", check=False),
        },
        "configs": configs,
        "manifests": manifests,
        "comparisons": {
            "smoke_vs_dense_route_signature": diff_signatures(
                smoke_signature, dense_signature
            ),
            "smoke_vs_generated_stage_e_route_signature": diff_signatures(
                smoke_signature, stage_e_signature
            )
            if stage_e_signature
            else None,
        },
        "local_artifacts": {
            "stage_e_root_exists": (repo_root / STAGE_E_ROOT).exists(),
            "golden_root_exists": golden_root.exists(),
        },
        "artifacts": artifacts,
        "implementation": implementation_summary(repo_root),
        "interpretation": {
            "same_route_as_dense_config": not bool(
                diff_signatures(smoke_signature, dense_signature)
            ),
            "required_stage_e_injected_keys": {
                "precomputed_probe_candidates_root": stage_e_signature.get(
                    "precomputed_probe_candidates_root"
                ),
                "cnn_bands_from": stage_e_signature.get("cnn_bands_from"),
                "probe_use_original_images": stage_e_signature.get(
                    "probe_use_original_images"
                ),
            }
            if stage_e_signature
            else None,
        },
    }

    json_path = work_root / "detector_route_audit.json"
    md_path = work_root / "detector_route_audit.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_markdown(report, md_path)

    zip_path = work_root.with_name(f"{work_root.name}_review.zip")
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(json_path, json_path.relative_to(repo_root))
        archive.write(md_path, md_path.relative_to(repo_root))
        for optional in (smoke_config, smoke_manifest, stage_e_config, stage_e_manifest):
            if optional.exists():
                archive.write(optional, optional.relative_to(repo_root))

    print(f"Route audit: {md_path.relative_to(repo_root)}")
    print(f"JSON report: {json_path.relative_to(repo_root)}")
    print(f"Review zip: {zip_path.relative_to(repo_root)}")
    print(
        "Same route signature as dense config:",
        report["interpretation"]["same_route_as_dense_config"],
    )
    print(
        "Differing route fields:",
        len(report["comparisons"]["smoke_vs_dense_route_signature"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
