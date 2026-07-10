"""Replay Issue #244 page 001 through the current dense detector route.

Temporary investigation helper. Delete before the final PR unless promoted to
maintained diagnostic tooling. Generated artifacts stay under ignored logs/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import traceback
import zipfile
from pathlib import Path
from typing import Any

import yaml

from src.pipeline.detector_routes.dense_full_pipeline import (
    reconstruct_dense_full_pipeline_route,
)
from src.pipeline.main import run_pipeline

INVENTORY = Path("logs/issue36_prep/20260208_bench_inventory.json")
DENSE_CONFIG = Path("configs/dense_full_pipeline.yaml")
SMOKE_RUN = Path(
    "logs/issue236_pipeline_connected_review_smoke/corrected_20260709_125046"
)
WORK_ROOT = Path("logs/issue244_local_probe/dense_page001_replay")
TARGET_SCORE = "Va_Prokofiev_Symphony1"
TARGET_PAGE = "page_001"
EXPECTED_STARTS = [1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]
EXPECTED_COUNTS = [5, 5, 5, 7, 7, 8, 5, 7, 10, 8, 5, 6]
EXPECTED_MMR = [
    (7, 3, 5),
    (7, 6, 3),
    (8, 0, 2),
    (8, 2, 2),
    (8, 4, 4),
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def target_record(inventory: dict[str, Any]) -> dict[str, Any]:
    matches = [
        record
        for record in inventory.get("records", [])
        if isinstance(record, dict)
        and record.get("score") == TARGET_SCORE
        and record.get("page") == TARGET_PAGE
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one inventory record for {TARGET_SCORE}/{TARGET_PAGE}, "
            f"got {len(matches)}"
        )
    return matches[0]


def resolve_image(raw: str | Path, repo_root: Path) -> Path:
    path = Path(raw)
    for candidate in (path, repo_root / path):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(path)


def page_id_from_manifest(path: Path) -> str:
    pages = load_json(path).get("pages", [])
    if isinstance(pages, dict):
        pages = list(pages.values())
    page_ids = [
        item.get("page_id")
        for item in pages
        if isinstance(item, dict) and isinstance(item.get("page_id"), str)
    ]
    if len(page_ids) != 1:
        raise RuntimeError(f"Expected one manifest page, got {page_ids}")
    return page_ids[0]


def artifact(run_dir: Path, page_id: str, name: str) -> Path:
    for root in ("intermediate", "outputs"):
        candidate = run_dir / root / page_id / name
        if candidate.exists():
            return candidate
    matches = [path for path in run_dir.rglob(name) if page_id in path.parts]
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"{name} for {page_id}: {matches}")


def systems(path: Path) -> list[dict[str, Any]]:
    pages = load_json(path).get("pages", [])
    if not isinstance(pages, list) or not pages:
        raise ValueError(f"No pages in {path}")
    result = pages[0].get("systems", {})
    if not isinstance(result, list):
        raise ValueError(f"No systems in {path}")
    return [item for item in result if isinstance(item, dict)]


def starts(items: list[dict[str, Any]]) -> list[int | None]:
    result: list[int | None] = []
    for system in items:
        measures = system.get("measures", [])
        first = measures[0] if isinstance(measures, list) and measures else None
        result.append(first.get("number") if isinstance(first, dict) else None)
    return result


def counts(items: list[dict[str, Any]]) -> list[int]:
    return [
        len(system.get("measures", []))
        if isinstance(system.get("measures"), list)
        else 0
        for system in items
    ]


def mmr_signatures(path: Path) -> list[tuple[int, int, int]]:
    payload = load_json(path)
    overrides = (
        payload.get("measure_overrides", []) if isinstance(payload, dict) else []
    )
    result = []
    for item in overrides:
        if not isinstance(item, dict):
            continue
        try:
            result.append(
                (int(item["system"]), int(item["measure"]), int(item["skip"]))
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result)


def summarize(run_dir: Path, page_id: str) -> dict[str, Any]:
    base = artifact(run_dir, page_id, "numbering_base.json")
    final = artifact(run_dir, page_id, "numbering_final.json")
    mmr = artifact(run_dir, page_id, "overrides_mmr.json")
    return {
        "run_dir": str(run_dir),
        "page_id": page_id,
        "base_path": str(base),
        "base_sha256": sha256(base),
        "final_path": str(final),
        "final_sha256": sha256(final),
        "mmr_path": str(mmr),
        "base_counts": counts(systems(base)),
        "base_starts": starts(systems(base)),
        "final_starts": starts(systems(final)),
        "mmr_signatures": [list(item) for item in mmr_signatures(mmr)],
    }


def delta(left: list[int | None], right: list[int | None]) -> list[int | None]:
    return [
        None if a is None or b is None else a - b
        for a, b in zip(left, right, strict=False)
    ]


def barline_record(
    manifest: Path, page_id: str, repo_root: Path
) -> dict[str, Any] | None:
    pages = load_json(manifest).get("pages", [])
    if isinstance(pages, dict):
        pages = list(pages.values())
    for item in pages:
        if not isinstance(item, dict) or item.get("page_id") != page_id:
            continue
        raw = item.get("barlines_json")
        if not isinstance(raw, str):
            return None
        path = Path(raw)
        for candidate in (path, repo_root / path):
            if candidate.exists():
                resolved = candidate.resolve()
                return {
                    "path": str(resolved),
                    "sha256": sha256(resolved),
                    "size_bytes": resolved.stat().st_size,
                }
        return {"path": raw, "exists": False}
    return None


def write_zip(paths: list[Path], zip_path: Path, repo_root: Path) -> None:
    added: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            name = str(path.resolve().relative_to(repo_root))
            if name in added:
                continue
            archive.write(path, name)
            added.add(name)


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

    driver_log = work_root / "driver.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(driver_log)],
        force=True,
    )
    logger = logging.getLogger(__name__)

    try:
        inventory = load_json(repo_root / INVENTORY)
        record = target_record(inventory)
        target_inventory = work_root / "target_inventory.json"
        target_inventory.write_text(
            json.dumps({**inventory, "records": [record]}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        empty_exclude = work_root / "empty_exclude.json"
        empty_exclude.write_text('{"excluded_pages": []}\n', encoding="utf-8")

        route_root = work_root / "dense_route"
        logger.info(
            "Reconstructing dense candidates for %s/%s", TARGET_SCORE, TARGET_PAGE
        )
        route = reconstruct_dense_full_pipeline_route(
            inventory=target_inventory,
            exclude=empty_exclude,
            route_root=route_root,
            expected_pages=1,
        )
        if len(route.image_paths) != 1:
            raise RuntimeError(
                f"Expected one route image, got {len(route.image_paths)}"
            )

        source_image = resolve_image(route.image_paths[0], repo_root)
        images_dir = route_root / "images"
        images_dir.mkdir()
        replay_image = images_dir / f"{source_image.parent.name}_{source_image.name}"
        shutil.copy2(source_image, replay_image)

        config = yaml.safe_load((repo_root / DENSE_CONFIG).read_text(encoding="utf-8"))
        run_id = "dense_page001_current"
        output_root = work_root / "runs"
        config["run"] = {"run_id": run_id, "output_root": str(output_root)}
        config.setdefault("inputs", {}).pop("pdf_path", None)
        config["inputs"]["pdf_to_images"] = {
            "output_dir": str(images_dir),
            "image_glob": "*.png",
        }
        config.setdefault("steps", {})["pdf_to_images"] = False
        detection = config.setdefault("detection", {})
        detection.update(
            {
                "precomputed_probe_candidates_root": str(route.probe_rescue_root),
                "cnn_bands_from": str(route.filtered_root),
                "probe_use_original_images": True,
                "hybrid_output_root": str(route_root / "hybrid_output"),
            }
        )
        config.setdefault("outputs", {}).setdefault("review", {})[
            "manual_correction_package"
        ] = False
        config_path = work_root / "dense_page001_current.yaml"
        config_path.write_text(
            yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

        logger.info("Running current pipeline with dense-route inputs")
        run_dir = run_pipeline(
            config_path,
            run_id=run_id,
            output_root=output_root,
            debug=True,
        )
        manifest = run_dir / "manifest.json"
        page_id = page_id_from_manifest(manifest)
        replay = summarize(run_dir, page_id)
        smoke = summarize(repo_root / SMOKE_RUN, "page_001")
        observed_mmr = {tuple(item) for item in replay["mmr_signatures"]}
        expected_mmr = set(EXPECTED_MMR)

        report = {
            "schema": "issue244.dense_page001_replay.v1",
            "temporary_script": str(Path(__file__).relative_to(repo_root)),
            "route": {
                "source_image": str(source_image),
                "replay_image": str(replay_image),
                "config": str(config_path),
                "precomputed_probe_candidates_root": str(route.probe_rescue_root),
                "cnn_bands_from": str(route.filtered_root),
                "probe_use_original_images": True,
                "enable_sr": detection.get("enable_sr"),
                "execution_summary": route.execution_summary,
            },
            "expected": {
                "row_starts": EXPECTED_STARTS,
                "base_counts": EXPECTED_COUNTS,
                "mmr_signatures": [list(item) for item in EXPECTED_MMR],
            },
            "replay": replay,
            "smoke": smoke,
            "barline_artifact": barline_record(manifest, page_id, repo_root),
            "comparison": {
                "base_counts_match": replay["base_counts"] == EXPECTED_COUNTS,
                "final_starts_match": replay["final_starts"] == EXPECTED_STARTS,
                "expected_minus_replay_final": delta(
                    EXPECTED_STARTS, replay["final_starts"]
                ),
                "replay_minus_smoke_base_counts": delta(
                    replay["base_counts"], smoke["base_counts"]
                ),
                "missing_expected_mmr": [
                    list(item) for item in sorted(expected_mmr - observed_mmr)
                ],
                "unexpected_mmr": [
                    list(item) for item in sorted(observed_mmr - expected_mmr)
                ],
            },
        }

        report_path = work_root / "dense_page001_replay.json"
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        markdown_path = work_root / "dense_page001_replay.md"
        markdown_path.write_text(
            "\n".join(
                [
                    "# Issue #244 dense page-001 replay",
                    "",
                    f"- expected: `{EXPECTED_STARTS}`",
                    f"- replay final: `{replay['final_starts']}`",
                    f"- replay base counts: `{replay['base_counts']}`",
                    f"- replay MMR: `{replay['mmr_signatures']}`",
                    f"- missing expected MMR: `{report['comparison']['missing_expected_mmr']}`",
                    f"- base counts match: `{report['comparison']['base_counts_match']}`",
                    f"- final starts match: `{report['comparison']['final_starts_match']}`",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        selected = [
            report_path,
            markdown_path,
            driver_log,
            target_inventory,
            empty_exclude,
            config_path,
            manifest,
            Path(replay["base_path"]),
            Path(replay["final_path"]),
            Path(replay["mmr_path"]),
        ]
        barline = report.get("barline_artifact")
        if isinstance(barline, dict) and "sha256" in barline:
            selected.append(Path(barline["path"]))
        selected.extend(route_root.rglob("*.json"))
        zip_path = work_root.with_name(f"{work_root.name}_review.zip")
        write_zip(selected, zip_path, repo_root)

        print("Dense replay page id:", page_id)
        print("Expected:     ", EXPECTED_STARTS)
        print("Replay final: ", replay["final_starts"])
        print("Replay base counts:", replay["base_counts"])
        print("Replay MMR:", replay["mmr_signatures"])
        print("Missing expected MMR:", report["comparison"]["missing_expected_mmr"])
        print("Base counts match:", report["comparison"]["base_counts_match"])
        print("Final starts match:", report["comparison"]["final_starts_match"])
        print("Report:", report_path.relative_to(repo_root))
        print("Review zip:", zip_path.relative_to(repo_root))
        return 0
    except Exception:
        failure = work_root / "failure.txt"
        failure.write_text(traceback.format_exc(), encoding="utf-8")
        logger.exception("Dense page-001 replay failed")
        print("Failure log:", failure.relative_to(repo_root))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
