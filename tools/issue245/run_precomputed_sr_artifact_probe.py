#!/usr/bin/env python3
"""Isolate retained historical SR pixels from HOMR runtime/source drift for Issue #245.

The probe reuses two saved SR working images per target page:

* the regenerated current-source x4 image from the preceding focused scale probe;
* the retained historical x4 image next to the accepted historical SR detection.

Both images are fed to the same current evaluator source and fixed HOMR runtime via
``--pre-computed-sr``. No Real-ESRGAN, dense reconstruction, CNN, MMR, or numbering
stage is run by this probe.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image

from src.pipeline.probe_detector.bands import build_row_stats
from src.pipeline.steps.hybrid_consensus import (
    apply_hybrid_consensus_filter,
    load_json_boxes,
)
from tools.issue245.run_pdfscore_evaluator_ref_probe import (
    IMAGE_TAG,
    compare_records,
    ensure_image,
    load_records,
    sha256_file,
)

Box = tuple[int, int, int, int]
DEFAULT_MAIN_REPO = Path("/home/masaki_muramatsu/ws_PDFScoreBar")
DEFAULT_SCALE_REPORT = Path(
    "logs/issue245_accuracy_first_stage_e/"
    "focused_sr_scale_revision_probe_sr_weights_userenv/"
    "focused_sr_scale_revision_probe_report.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "logs/issue245_accuracy_first_stage_e/precomputed_sr_artifact_probe"
)
PROVENANCE_NAMES = (
    "run_config.json",
    "run.sh",
    "config.json",
    "metadata.json",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in value).strip("_")


def _normalise_box(value: Sequence[Any]) -> Box:
    if len(value) != 4:
        raise ValueError(f"Invalid bbox: {value!r}")
    return tuple(int(round(float(item))) for item in value)  # type: ignore[return-value]


def _image_summary(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
        mode = image.mode
        image_format = image.format
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "width": int(width),
        "height": int(height),
        "mode": mode,
        "format": image_format,
    }


def _find_working_image(detection_path: Path, page: str, original: dict[str, Any]) -> Path:
    directory = detection_path.parent
    ordered = [directory / f"{page}.png", directory / f"{page}_sr.png"]
    ordered.extend(sorted(directory.glob("*.png")))

    candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in ordered:
        resolved = candidate.resolve()
        if candidate.is_file() and resolved not in seen:
            seen.add(resolved)
            candidates.append(candidate)

    if not candidates:
        raise FileNotFoundError(f"No PNG working image next to detection: {detection_path}")

    summaries = [(candidate, _image_summary(candidate)) for candidate in candidates]
    upscaled = [
        (candidate, summary)
        for candidate, summary in summaries
        if summary["width"] > original["width"] and summary["height"] > original["height"]
    ]
    named = [candidate for candidate, _ in upscaled if candidate.name == f"{page}.png"]
    if len(named) == 1:
        return named[0]
    if len(upscaled) == 1:
        return upscaled[0][0]
    raise RuntimeError(
        "Could not select exactly one upscaled working image next to "
        f"{detection_path}: {[summary for _, summary in summaries]}"
    )


def _nearest_provenance_files(detection_path: Path, max_levels: int = 5) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    directory = detection_path.parent
    for _ in range(max_levels + 1):
        for name in PROVENANCE_NAMES:
            candidate = directory / name
            if candidate.is_file():
                records.append(
                    {
                        "path": str(candidate),
                        "sha256": sha256_file(candidate),
                        "size_bytes": candidate.stat().st_size,
                    }
                )
        directory = directory.parent
    unique: dict[str, dict[str, Any]] = {record["path"]: record for record in records}
    return [unique[path] for path in sorted(unique)]


def _path_to_container(path: Path, *, worktree: Path, main_repo: Path) -> str:
    resolved = path.resolve()
    roots = (
        (worktree.resolve(), Path("/workspace")),
        ((main_repo / "logs").resolve(), Path("/main_logs")),
        ((main_repo / "data").resolve(), Path("/main_data")),
    )
    for host_root, container_root in roots:
        try:
            relative = resolved.relative_to(host_root)
        except ValueError:
            continue
        return str(container_root / relative)
    raise ValueError(f"Path is outside supported mounts: {path}")


def _run_logged(command: list[str], log_path: Path, *, cwd: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("+", " ".join(command), flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            log.write(line)
        returncode = process.wait()
    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, command)


def _run_precomputed(
    *,
    name: str,
    worktree: Path,
    main_repo: Path,
    output_root: Path,
    original_image: Path,
    sr_image: Path,
    page: str,
) -> dict[str, Any]:
    output_host = output_root / name / "evaluator"
    output_host.mkdir(parents=True, exist_ok=True)
    run_id = f"issue245_{name}"
    output_container = _path_to_container(output_host, worktree=worktree, main_repo=main_repo)
    original_container = _path_to_container(original_image, worktree=worktree, main_repo=main_repo)
    sr_container = _path_to_container(sr_image, worktree=worktree, main_repo=main_repo)

    uid = str(os.getuid())
    gid = str(os.getgid())
    command = [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--user",
        f"{uid}:{gid}",
        "-v",
        f"{worktree}:/workspace",
        "-v",
        f"{main_repo / 'logs'}:/main_logs:ro",
        "-v",
        f"{main_repo / 'data'}:/main_data:ro",
        "-w",
        "/workspace",
        "-e",
        "PYTHONPATH=/workspace",
        "-e",
        "HOME=/tmp/issue245_home",
        "-e",
        "XDG_CACHE_HOME=/tmp/issue245_cache",
        "-e",
        "TORCH_HOME=/tmp/issue245_torch",
        IMAGE_TAG,
        "/opt/venv_pipeline/bin/python",
        "tools/issue245/run_homr_evaluator_compat.py",
        "--images",
        original_container,
        "--output-root",
        output_container,
        "--force-run-id",
        run_id,
        "--pre-computed-sr",
        sr_container,
        "--enable-segnet-cache",
    ]
    log_path = output_root / name / "evaluator.log"
    _run_logged(command, log_path, cwd=worktree)

    detection_path = output_host / run_id / page / f"{page}_detections.json"
    if not detection_path.is_file():
        raise FileNotFoundError(f"Detection was not created: {detection_path}")
    return {
        "name": name,
        "run_id": run_id,
        "log": str(log_path),
        "sr_image": _image_summary(sr_image),
        "detection": {
            "path": str(detection_path),
            "sha256": sha256_file(detection_path),
            "count": len(load_records(detection_path)),
        },
    }


def _row_bands(
    *, baseline_path: Path, sr_path: Path, omr_path: Path
) -> tuple[list[dict[str, Any]], int]:
    hybrid = apply_hybrid_consensus_filter(
        baseline_boxes=load_json_boxes(baseline_path),
        sr_boxes=load_json_boxes(sr_path),
        omr_boxes=load_json_boxes(omr_path),
    )
    rows = build_row_stats(hybrid, cluster_max_dist=25.0, min_row_count=1)
    normalised = [
        {
            "center": float(row["center"]),
            "top": int(row["top"]),
            "bottom": int(row["bottom"]),
            "count": int(row["count"]),
        }
        for row in rows
    ]
    return normalised, len(hybrid)


def _has_reference_band(rows: Iterable[dict[str, Any]], reference: Box) -> bool:
    expected = (min(reference[1], reference[3]), max(reference[1], reference[3]))
    return any((int(row["top"]), int(row["bottom"])) == expected for row in rows)


def _classify_target(*, control_present: bool, historical_pixels_present: bool) -> str:
    if not control_present and historical_pixels_present:
        return "historical_sr_pixels_restore"
    if control_present and historical_pixels_present:
        return "precomputed_route_restores_both"
    if control_present and not historical_pixels_present:
        return "unexpected_control_only_restore"
    return "homr_runtime_or_retained_artifact_postprocess_dependency"


def _resolve_input(path: Path, *, worktree: Path, main_repo: Path) -> Path:
    if path.is_absolute():
        return path
    worktree_candidate = worktree / path
    if worktree_candidate.exists():
        return worktree_candidate
    return main_repo / path


def build_report(
    *,
    worktree: Path,
    main_repo: Path,
    scale_report_path: Path,
    output_root: Path,
    force: bool,
    base_image: str,
    rebuild: bool,
) -> dict[str, Any]:
    scale_report = _load_json(scale_report_path)
    if scale_report.get("status") != "completed":
        raise ValueError(f"Scale report is not completed: {scale_report_path}")

    if output_root.exists():
        if not force:
            raise FileExistsError(f"Output exists; rerun with --force: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    ensure_image(
        worktree,
        output_root,
        base_image=base_image,
        rebuild=rebuild,
    )

    report: dict[str, Any] = {
        "schema_version": "issue245.precomputed_sr_artifact_probe.v1",
        "status": "running",
        "production_default_changed": False,
        "realesrgan_run": False,
        "dense_or_cnn_run": False,
        "isolation": {
            "homr_commit": scale_report.get("isolation", {}).get("homr_commit"),
            "image_tag": IMAGE_TAG,
            "variable": "precomputed retained historical SR pixels vs regenerated x4 pixels",
            "evaluator_source": "current worktree source only",
        },
        "scale_report": str(scale_report_path),
        "pages": [],
        "targets": [],
    }
    report_path = output_root / "precomputed_sr_artifact_probe_report.json"
    _write_json(report_path, report)

    try:
        for page_item in scale_report.get("pages", []):
            score = str(page_item["score"])
            page = str(page_item["page"])
            key = f"{score}/{page}"
            original_image = Path(str(page_item["image"]))
            original_summary = _image_summary(original_image)

            historical_detection = Path(str(page_item["paths"]["historical_sr"]))
            generated_x4_detection = Path(
                str(scale_report["variants"]["current_source_x4"]["detections"][key]["path"])
            )
            historical_sr_image = _find_working_image(
                historical_detection, page, original_summary
            )
            generated_x4_image = _find_working_image(
                generated_x4_detection, page, original_summary
            )

            page_slug = f"{_slug(score)}_{_slug(page)}"
            control = _run_precomputed(
                name=f"control_x4_pixels_{page_slug}",
                worktree=worktree,
                main_repo=main_repo,
                output_root=output_root,
                original_image=original_image,
                sr_image=generated_x4_image,
                page=page,
            )
            historical_pixels = _run_precomputed(
                name=f"historical_sr_pixels_{page_slug}",
                worktree=worktree,
                main_repo=main_repo,
                output_root=output_root,
                original_image=original_image,
                sr_image=historical_sr_image,
                page=page,
            )

            baseline_path = Path(str(page_item["paths"]["fresh_baseline"]))
            omr_path = Path(str(page_item["paths"]["current_omr"]))
            control_detection = Path(str(control["detection"]["path"]))
            historical_pixels_detection = Path(
                str(historical_pixels["detection"]["path"])
            )
            control_rows, control_hybrid_count = _row_bands(
                baseline_path=baseline_path,
                sr_path=control_detection,
                omr_path=omr_path,
            )
            historical_rows, historical_hybrid_count = _row_bands(
                baseline_path=baseline_path,
                sr_path=historical_pixels_detection,
                omr_path=omr_path,
            )

            saved_historical_records = load_records(historical_detection)
            generated_x4_records = load_records(generated_x4_detection)
            control_records = load_records(control_detection)
            historical_pixel_records = load_records(historical_pixels_detection)

            page_result = {
                "score": score,
                "page": page,
                "original_image": original_summary,
                "historical_sr_image": _image_summary(historical_sr_image),
                "regenerated_x4_image": _image_summary(generated_x4_image),
                "historical_vs_regenerated_x4_same_bytes": (
                    sha256_file(historical_sr_image) == sha256_file(generated_x4_image)
                ),
                "historical_detection_provenance": _nearest_provenance_files(
                    historical_detection
                ),
                "generated_x4_detection_provenance": _nearest_provenance_files(
                    generated_x4_detection
                ),
                "variants": {
                    "control_x4_pixels": {
                        **control,
                        "comparison_to_original_generated_x4_detection": compare_records(
                            generated_x4_records, control_records
                        ),
                        "comparison_to_saved_historical_sr": compare_records(
                            saved_historical_records, control_records
                        ),
                        "hybrid_candidate_count": control_hybrid_count,
                        "rows": control_rows,
                    },
                    "historical_sr_pixels": {
                        **historical_pixels,
                        "comparison_to_saved_historical_sr": compare_records(
                            saved_historical_records, historical_pixel_records
                        ),
                        "comparison_to_original_generated_x4_detection": compare_records(
                            generated_x4_records, historical_pixel_records
                        ),
                        "hybrid_candidate_count": historical_hybrid_count,
                        "rows": historical_rows,
                    },
                },
            }
            report["pages"].append(page_result)

            for raw_reference in page_item.get("references", []):
                reference = _normalise_box(raw_reference)
                control_present = _has_reference_band(control_rows, reference)
                historical_present = _has_reference_band(historical_rows, reference)
                report["targets"].append(
                    {
                        "score": score,
                        "page": page,
                        "reference": list(reference),
                        "control_x4_pixels_present": control_present,
                        "historical_sr_pixels_present": historical_present,
                        "classification": _classify_target(
                            control_present=control_present,
                            historical_pixels_present=historical_present,
                        ),
                    }
                )
            _write_json(report_path, report)

        report["status"] = "completed"
    except Exception as error:
        report.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
    finally:
        _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--main-repo-root",
        type=Path,
        default=Path(os.environ.get("ISSUE245_MAIN_REPO_ROOT", DEFAULT_MAIN_REPO)),
    )
    parser.add_argument("--scale-report", type=Path, default=DEFAULT_SCALE_REPORT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--base-image",
        default=os.environ.get("ISSUE245_REVISION_BASE_IMAGE", "pdfscore_pipeline_gpu"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    worktree = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    main_repo = args.main_repo_root.expanduser().resolve()
    scale_report = _resolve_input(
        args.scale_report.expanduser(), worktree=worktree, main_repo=main_repo
    ).resolve()
    output_root = args.output_root.expanduser()
    if not output_root.is_absolute():
        output_root = (worktree / output_root).resolve()

    report = build_report(
        worktree=worktree,
        main_repo=main_repo,
        scale_report_path=scale_report,
        output_root=output_root,
        force=args.force,
        base_image=args.base_image,
        rebuild=args.rebuild,
    )
    print(f"Report: {output_root / 'precomputed_sr_artifact_probe_report.json'}")
    for target in report.get("targets", []):
        print(
            f"{target['score']}/{target['page']} reference={target['reference']} "
            f"classification={target['classification']}"
        )
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
