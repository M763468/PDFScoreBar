"""Temporary Issue #244 local A/B probe.

This helper is intentionally tracked only to make the local investigation reproducible.
Delete it before the final PR unless the investigation proves that it should become a
maintained diagnostic tool.

It compares the existing Issue #236 smoke run with a one-page rerun that changes only
these detector settings to the current evaluation baseline values:

- detection.enable_sr = true
- detection.sr_scale = 2
- detection.crop_recenter_on_bbox_ink = true

Generated artifacts remain under ignored ``logs/`` paths.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

DEFAULT_SOURCE_CONFIG = Path(
    "logs/issue236_pipeline_connected_review_smoke/"
    "corrected_20260709_125046/corrected_pipeline_config.json"
)
DEFAULT_BASELINE_RUN = Path(
    "logs/issue236_pipeline_connected_review_smoke/corrected_20260709_125046"
)
DEFAULT_WORK_ROOT = Path("logs/issue244_local_probe/current_canonical_ab")
DEFAULT_RUN_ID = "current_canonical_page001"
DEFAULT_PAGE_ID = "page_001"
DEFAULT_EXPECTED_ROW_STARTS = [1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_expected(value: str) -> list[int]:
    try:
        result = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--expected-row-starts must be a comma-separated integer list"
        ) from exc
    if not result:
        raise argparse.ArgumentTypeError("--expected-row-starts must not be empty")
    return result


def _systems_from_numbering(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
        raise ValueError(f"No usable pages[0] in {path}")
    systems = pages[0].get("systems")
    if not isinstance(systems, list):
        raise ValueError(f"No usable pages[0].systems in {path}")
    return [item for item in systems if isinstance(item, dict)]


def _row_starts(systems: list[dict[str, Any]]) -> list[int | None]:
    result: list[int | None] = []
    for system in systems:
        measures = system.get("measures")
        if not isinstance(measures, list) or not measures:
            result.append(None)
            continue
        first = measures[0]
        result.append(first.get("number") if isinstance(first, dict) else None)
    return result


def _measure_counts(systems: list[dict[str, Any]]) -> list[int]:
    counts = []
    for system in systems:
        measures = system.get("measures")
        counts.append(len(measures) if isinstance(measures, list) else 0)
    return counts


def _numbering_summary(run_dir: Path, page_id: str) -> dict[str, Any]:
    base_path = run_dir / "intermediate" / page_id / "numbering_base.json"
    final_path = run_dir / "outputs" / page_id / "numbering_final.json"
    mmr_path = run_dir / "intermediate" / page_id / "overrides_mmr.json"

    missing = [path for path in (base_path, final_path) if not path.exists()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing numbering artifact(s): {joined}")

    base_systems = _systems_from_numbering(base_path)
    final_systems = _systems_from_numbering(final_path)
    mmr_payload = _load_json(mmr_path) if mmr_path.exists() else {}

    return {
        "run_dir": str(run_dir),
        "base_numbering_path": str(base_path),
        "final_numbering_path": str(final_path),
        "mmr_path": str(mmr_path) if mmr_path.exists() else None,
        "base_measure_counts": _measure_counts(base_systems),
        "base_row_starts": _row_starts(base_systems),
        "final_row_starts": _row_starts(final_systems),
        "mmr_overrides": mmr_payload.get("measure_overrides", []),
    }


def _subtract_lists(
    right: list[int | None], left: list[int | None]
) -> list[int | None]:
    result: list[int | None] = []
    for left_value, right_value in zip(left, right, strict=False):
        if left_value is None or right_value is None:
            result.append(None)
        else:
            result.append(right_value - left_value)
    return result


def _tail(path: Path, line_count: int = 120) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])


def _add_to_zip(
    archive: zipfile.ZipFile,
    path: Path,
    *,
    root: Path,
) -> None:
    if path.exists() and path.is_file():
        archive.write(path, path.relative_to(root))


def _build_review_zip(
    *,
    repo_root: Path,
    work_root: Path,
    run_dir: Path,
    page_id: str,
    config_path: Path,
    driver_log: Path,
    comparison_path: Path,
) -> Path:
    archive_path = work_root.with_name(f"{work_root.name}_review.zip")
    if archive_path.exists():
        archive_path.unlink()

    candidate_files = [
        config_path,
        driver_log,
        comparison_path,
        run_dir / "manifest.json",
        run_dir / "pipeline.log",
        run_dir / "intermediate" / page_id / "numbering_base.json",
        run_dir / "intermediate" / page_id / "overrides_mmr.json",
        run_dir / "outputs" / page_id / "numbering_final.json",
    ]

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidate_files:
            _add_to_zip(archive, path, root=repo_root)

    return archive_path


def _prepare_config(
    *,
    source_config: Path,
    destination: Path,
    work_root: Path,
) -> dict[str, Any]:
    config = _load_json(source_config)
    if not isinstance(config, dict):
        raise TypeError(f"Expected object config: {source_config}")

    inputs = config.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        raise TypeError("config.inputs must be an object")
    pdf_options = inputs.setdefault("pdf_to_images", {})
    if not isinstance(pdf_options, dict):
        raise TypeError("config.inputs.pdf_to_images must be an object")

    # normalise_pages() expects a comma-separated string, not a JSON array.
    pdf_options["pages"] = "1"

    detection = config.setdefault("detection", {})
    if not isinstance(detection, dict):
        raise TypeError("config.detection must be an object")
    detection["enable_sr"] = True
    detection["sr_scale"] = 2
    detection["crop_recenter_on_bbox_ink"] = True
    detection["hybrid_output_root"] = str(work_root / "hybrid")

    mmr = config.setdefault("mmr", {})
    if not isinstance(mmr, dict):
        raise TypeError("config.mmr must be an object")
    mmr["debug_root"] = str(work_root / "mmr_debug")

    outputs = config.setdefault("outputs", {})
    if not isinstance(outputs, dict):
        raise TypeError("config.outputs must be an object")
    review = outputs.setdefault("review", {})
    if not isinstance(review, dict):
        raise TypeError("config.outputs.review must be an object")
    review["manual_correction_package"] = False

    _write_json(destination, config)
    return config


def _run_pipeline(
    *,
    repo_root: Path,
    config_path: Path,
    output_root: Path,
    run_id: str,
    driver_log: Path,
) -> int:
    command = [
        sys.executable,
        "-m",
        "src.pipeline.main",
        "--config",
        str(config_path),
        "--run-id",
        run_id,
        "--output-root",
        str(output_root),
        "--page-limit",
        "1",
        "--debug",
    ]

    driver_log.parent.mkdir(parents=True, exist_ok=True)
    with driver_log.open("w", encoding="utf-8") as stream:
        stream.write("command: " + " ".join(command) + "\n\n")
        stream.flush()
        completed = subprocess.run(
            command,
            cwd=repo_root,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
        stream.write(f"\nexit_status={completed.returncode}\n")
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--baseline-run", type=Path, default=DEFAULT_BASELINE_RUN)
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--page-id", default=DEFAULT_PAGE_ID)
    parser.add_argument(
        "--expected-row-starts",
        type=_parse_expected,
        default=DEFAULT_EXPECTED_ROW_STARTS,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove a prior candidate run before executing.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write the candidate config without running the pipeline.",
    )
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    source_config = (repo_root / args.source_config).resolve()
    baseline_run = (repo_root / args.baseline_run).resolve()
    work_root = (repo_root / args.work_root).resolve()
    output_root = work_root / "runs"
    run_dir = output_root / args.run_id
    config_path = work_root / "current_canonical_page001.json"
    driver_log = work_root / "driver_stdout_stderr.log"
    comparison_path = work_root / "ab_comparison.json"

    if not source_config.exists():
        raise FileNotFoundError(source_config)
    if not baseline_run.exists():
        raise FileNotFoundError(baseline_run)

    work_root.mkdir(parents=True, exist_ok=True)
    if run_dir.exists():
        if not args.force:
            raise FileExistsError(
                f"Candidate run already exists: {run_dir}. Re-run with --force."
            )
        shutil.rmtree(run_dir)

    for path in (work_root / "hybrid", work_root / "mmr_debug"):
        if path.exists() and args.force:
            shutil.rmtree(path)

    config = _prepare_config(
        source_config=source_config,
        destination=config_path,
        work_root=work_root.relative_to(repo_root),
    )

    detection = config["detection"]
    print("Prepared candidate config:")
    print(f"  source: {source_config.relative_to(repo_root)}")
    print(f"  output: {config_path.relative_to(repo_root)}")
    print(f"  pages: {config['inputs']['pdf_to_images']['pages']!r}")
    print(f"  enable_sr: {detection['enable_sr']}")
    print(f"  sr_scale: {detection['sr_scale']}")
    print(
        "  crop_recenter_on_bbox_ink: "
        f"{detection['crop_recenter_on_bbox_ink']}"
    )

    if args.prepare_only:
        return 0

    status = _run_pipeline(
        repo_root=repo_root,
        config_path=config_path.relative_to(repo_root),
        output_root=output_root.relative_to(repo_root),
        run_id=args.run_id,
        driver_log=driver_log,
    )
    if status != 0:
        print(f"Pipeline failed with exit status {status}.", file=sys.stderr)
        print(f"Log: {driver_log.relative_to(repo_root)}", file=sys.stderr)
        tail = _tail(driver_log)
        if tail:
            print("\n--- log tail ---", file=sys.stderr)
            print(tail, file=sys.stderr)
        return status

    baseline = _numbering_summary(baseline_run, args.page_id)
    candidate = _numbering_summary(run_dir, args.page_id)
    expected = args.expected_row_starts

    report = {
        "schema": "issue244.current_canonical_ab.v1",
        "temporary_script": str(Path(__file__).relative_to(repo_root)),
        "changed_detection_settings": {
            "enable_sr": True,
            "sr_scale": 2,
            "crop_recenter_on_bbox_ink": True,
        },
        "expected_row_starts": expected,
        "baseline": baseline,
        "candidate": candidate,
        "comparison": {
            "base_measure_count_delta_candidate_minus_baseline": _subtract_lists(
                candidate["base_measure_counts"], baseline["base_measure_counts"]
            ),
            "final_row_start_delta_candidate_minus_baseline": _subtract_lists(
                candidate["final_row_starts"], baseline["final_row_starts"]
            ),
            "expected_minus_baseline_final": _subtract_lists(
                baseline["final_row_starts"], expected
            ),
            "expected_minus_candidate_final": _subtract_lists(
                candidate["final_row_starts"], expected
            ),
            "candidate_matches_expected": candidate["final_row_starts"] == expected,
        },
    }
    _write_json(comparison_path, report)

    archive_path = _build_review_zip(
        repo_root=repo_root,
        work_root=work_root,
        run_dir=run_dir,
        page_id=args.page_id,
        config_path=config_path,
        driver_log=driver_log,
        comparison_path=comparison_path,
    )

    print("\nA/B summary:")
    print(f"  expected:  {expected}")
    print(f"  baseline:  {baseline['final_row_starts']}")
    print(f"  candidate: {candidate['final_row_starts']}")
    print(
        "  base measure-count delta: "
        f"{report['comparison']['base_measure_count_delta_candidate_minus_baseline']}"
    )
    print(
        "  candidate matches expected: "
        f"{report['comparison']['candidate_matches_expected']}"
    )
    print(f"  comparison: {comparison_path.relative_to(repo_root)}")
    print(f"  review zip: {archive_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
