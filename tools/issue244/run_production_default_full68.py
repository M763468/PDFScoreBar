#!/usr/bin/env python3
"""Run the current production-default detector/numbering route on all 68 pages.

Temporary Issue #244 acceptance helper. Delete before the final PR after the
full-regression evidence has been recorded.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.detector_routes.dense_full_pipeline import load_route_image_paths
from src.pipeline.main import run_pipeline

INVENTORY = Path("logs/issue36_prep/20260208_bench_inventory.json")
EXCLUDE = Path("logs/issue36_prep/excluded_pages_for_gt_prep.json")
SOURCE_CONFIG = Path("configs/dense_full_pipeline.yaml")
WORK_ROOT = Path("logs/issue244_full_regression")
RUN_ID = "production_default_full68"
EXPECTED_PAGES = 68


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def one_page_id(item: dict[str, Any]) -> str:
    page_id = item.get("page_id")
    if not isinstance(page_id, str):
        raise ValueError(f"Manifest page has no page_id: {item}")
    return page_id


def build_mmr_page_inputs(run_dir: Path, output_path: Path) -> None:
    manifest = load_json(run_dir / "manifest.json")
    pages = manifest.get("pages", [])
    if not isinstance(pages, list) or len(pages) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} manifest pages, got {len(pages)}")

    records = []
    for item in pages:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid manifest page: {item}")
        page_id = one_page_id(item)
        image_path = item.get("image_path")
        if not isinstance(image_path, str):
            raise ValueError(f"Manifest page has no image_path: {item}")
        numbering_base = run_dir / "intermediate" / page_id / "numbering_base.json"
        if not numbering_base.exists():
            raise FileNotFoundError(numbering_base)
        records.append(
            {
                "page_id": page_id,
                "image": image_path,
                "numbering_base": str(numbering_base),
            }
        )

    output_path.write_text(
        json.dumps({"pages": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


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

    inventory = repo_root / INVENTORY
    exclude = repo_root / EXCLUDE
    if not inventory.exists():
        raise FileNotFoundError(inventory)
    if not exclude.exists():
        raise FileNotFoundError(exclude)

    image_paths = load_route_image_paths(
        inventory=inventory,
        exclude=exclude,
        expected_pages=EXPECTED_PAGES,
    )
    images_dir = work_root / "input_images"
    images_dir.mkdir()
    for image_path in image_paths:
        source = Path(image_path)
        destination = images_dir / f"{source.parent.name}_{source.name}"
        shutil.copy2(source, destination)

    config = yaml.safe_load((repo_root / SOURCE_CONFIG).read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Invalid config root: {SOURCE_CONFIG}")

    runs_root = work_root / "runs"
    config["run"] = {"run_id": RUN_ID, "output_root": str(runs_root)}
    inputs = config.setdefault("inputs", {})
    inputs.pop("pdf_path", None)
    inputs["pdf_to_images"] = {
        "output_dir": str(images_dir),
        "image_glob": "*.png",
    }
    config.setdefault("steps", {})["pdf_to_images"] = False

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
    config.setdefault("outputs", {}).setdefault("review", {})["manual_correction_package"] = False

    config_path = work_root / "production_default_full68.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    run_dir = run_pipeline(
        config_path,
        run_id=RUN_ID,
        output_root=runs_root,
    )
    manifest = load_json(run_dir / "manifest.json")
    resolved_route = manifest.get("config", {}).get("detection", {}).get("resolved_route")
    if not isinstance(resolved_route, dict):
        raise RuntimeError("Manifest does not contain resolved detector route metadata")
    if resolved_route.get("profile") != "production_dense_v1":
        raise RuntimeError(f"Unexpected detector profile: {resolved_route}")
    if resolved_route.get("selection") != "default":
        raise RuntimeError(f"Detector route was not selected by default: {resolved_route}")

    page_inputs = work_root / "mmr_page_inputs.json"
    build_mmr_page_inputs(run_dir, page_inputs)

    summary = {
        "schema": "issue244.production_default_full68_run.v1",
        "config": str(config_path),
        "run_dir": str(run_dir),
        "page_count": len(image_paths),
        "mmr_page_inputs": str(page_inputs),
        "resolved_route": resolved_route,
    }
    summary_path = work_root / "run_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Run directory: {run_dir.relative_to(repo_root)}")
    print(f"Page count: {len(image_paths)}")
    print(f"Route profile: {resolved_route.get('profile')}")
    print(f"Route selection: {resolved_route.get('selection')}")
    print(f"MMR page inputs: {page_inputs.relative_to(repo_root)}")
    print(f"Summary: {summary_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
