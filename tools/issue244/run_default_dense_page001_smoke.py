"""Validate that the production default route fixes Issue #244 page 001.

Temporary investigation/acceptance helper. Delete before the final PR unless it
is promoted to maintained diagnostic tooling. Generated artifacts stay in logs/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from src.pipeline.main import run_pipeline

SOURCE_CONFIG = Path(
    "logs/issue236_pipeline_connected_review_smoke/"
    "corrected_20260709_125046/corrected_pipeline_config.json"
)
WORK_ROOT = Path("logs/issue244_local_probe/default_dense_page001_smoke")
EXPECTED_STARTS = [1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]
EXPECTED_COUNTS = [5, 5, 5, 7, 7, 8, 5, 7, 10, 8, 5, 6]
EXPECTED_MMR = [
    [7, 3, 5],
    [7, 6, 3],
    [8, 0, 2],
    [8, 2, 2],
    [8, 4, 4],
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def systems(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    pages = payload.get("pages", [])
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"No pages in {path}")
    result = pages[0].get("systems", [])
    if not isinstance(result, list):
        raise ValueError(f"No systems in {path}")
    return [item for item in result if isinstance(item, dict)]


def row_starts(items: list[dict[str, Any]]) -> list[int | None]:
    result: list[int | None] = []
    for system in items:
        measures = system.get("measures", [])
        first = measures[0] if isinstance(measures, list) and measures else None
        result.append(first.get("number") if isinstance(first, dict) else None)
    return result


def measure_counts(items: list[dict[str, Any]]) -> list[int]:
    return [
        len(system.get("measures", [])) if isinstance(system.get("measures"), list) else 0
        for system in items
    ]


def mmr_signatures(path: Path) -> list[list[int]]:
    payload = load_json(path)
    overrides = payload.get("measure_overrides", [])
    signatures = []
    for item in overrides:
        if not isinstance(item, dict):
            continue
        signatures.append([int(item["system"]), int(item["measure"]), int(item["skip"])])
    return sorted(signatures)


def one_manifest_page_id(manifest_path: Path) -> str:
    pages = load_json(manifest_path).get("pages", [])
    page_ids = [
        item.get("page_id")
        for item in pages
        if isinstance(item, dict) and isinstance(item.get("page_id"), str)
    ]
    if len(page_ids) != 1:
        raise RuntimeError(f"Expected one manifest page, got {page_ids}")
    return page_ids[0]


def write_review_zip(work_root: Path, run_dir: Path, report: Path) -> Path:
    zip_path = work_root.with_name(f"{work_root.name}_review.zip")
    zip_path.unlink(missing_ok=True)
    include = [
        report,
        work_root / "default_dense_page001.json",
        run_dir / "manifest.json",
        run_dir / "pipeline.log",
    ]
    include.extend(run_dir.rglob("numbering_base.json"))
    include.extend(run_dir.rglob("numbering_final.json"))
    include.extend(run_dir.rglob("overrides_mmr.json"))
    include.extend(run_dir.rglob("dense_route_execution_summary.json"))
    include.extend(run_dir.rglob("pipeline2_no_peak_filtered_cnn.json"))

    repo_root = Path.cwd().resolve()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        added: set[str] = set()
        for path in include:
            if not path.exists() or not path.is_file():
                continue
            name = str(path.resolve().relative_to(repo_root))
            if name in added:
                continue
            archive.write(path, name)
            added.add(name)
    return zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    work_root = repo_root / WORK_ROOT
    if work_root.exists():
        if not args.force:
            raise FileExistsError(f"{work_root} exists; use --force")
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    source = repo_root / SOURCE_CONFIG
    if not source.exists():
        raise FileNotFoundError(source)
    config = load_json(source)

    # Exercise the actual default. Do not set route, precomputed candidates,
    # bands, or original-image mode in this acceptance config.
    detection = config.setdefault("detection", {})
    for key in (
        "route",
        "precomputed_probe_candidates_root",
        "cnn_bands_from",
        "probe_use_original_images",
        "resolved_route",
    ):
        detection.pop(key, None)
    detection["hybrid_output_root"] = str(work_root / "hybrid")

    pdf_options = config.setdefault("inputs", {}).setdefault("pdf_to_images", {})
    pdf_options["pages"] = "1"
    config.setdefault("outputs", {}).setdefault("review", {})["manual_correction_package"] = False

    run_id = "default_dense_page001"
    output_root = work_root / "runs"
    config["run"] = {"run_id": run_id, "output_root": str(output_root)}
    config_path = work_root / "default_dense_page001.json"
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    run_dir = run_pipeline(
        config_path,
        run_id=run_id,
        output_root=output_root,
        debug=True,
    )
    page_id = one_manifest_page_id(run_dir / "manifest.json")
    base_path = run_dir / "intermediate" / page_id / "numbering_base.json"
    final_path = run_dir / "outputs" / page_id / "numbering_final.json"
    mmr_path = run_dir / "intermediate" / page_id / "overrides_mmr.json"

    observed_counts = measure_counts(systems(base_path))
    observed_starts = row_starts(systems(final_path))
    observed_mmr = mmr_signatures(mmr_path)
    manifest = load_json(run_dir / "manifest.json")
    resolved_route = manifest.get("config", {}).get("detection", {}).get("resolved_route")

    report_payload = {
        "schema": "issue244.default_dense_page001_smoke.v1",
        "source_config": str(source),
        "acceptance_config": str(config_path),
        "run_dir": str(run_dir),
        "page_id": page_id,
        "expected": {
            "row_starts": EXPECTED_STARTS,
            "base_counts": EXPECTED_COUNTS,
            "mmr": EXPECTED_MMR,
        },
        "observed": {
            "row_starts": observed_starts,
            "base_counts": observed_counts,
            "mmr": observed_mmr,
            "resolved_route": resolved_route,
        },
        "checks": {
            "route_defaulted_to_dense": (
                isinstance(resolved_route, dict)
                and resolved_route.get("profile") == "production_dense_v1"
                and resolved_route.get("selection") == "default"
            ),
            "base_counts_match": observed_counts == EXPECTED_COUNTS,
            "mmr_match": observed_mmr == EXPECTED_MMR,
            "final_starts_match": observed_starts == EXPECTED_STARTS,
        },
    }
    report = work_root / "default_dense_page001_smoke.json"
    report.write_text(
        json.dumps(report_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review_zip = write_review_zip(work_root, run_dir, report)

    print("Resolved route:", resolved_route)
    print("Expected:     ", EXPECTED_STARTS)
    print("Observed:     ", observed_starts)
    print("Base counts:  ", observed_counts)
    print("MMR:          ", observed_mmr)
    print("Checks:       ", report_payload["checks"])
    print("Report:       ", report.relative_to(repo_root))
    print("Review zip:   ", review_zip.relative_to(repo_root))

    if not all(report_payload["checks"].values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
