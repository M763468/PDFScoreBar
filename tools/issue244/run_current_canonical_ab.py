"""Temporary Issue #244 one-page canonical-config A/B probe.

Tracked only so the local investigation is reproducible. Delete this helper before
opening the final PR unless it is deliberately promoted to maintained tooling.
Generated artifacts stay under ignored ``logs/`` paths.
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

SOURCE_CONFIG = Path(
    "logs/issue236_pipeline_connected_review_smoke/"
    "corrected_20260709_125046/corrected_pipeline_config.json"
)
BASELINE_RUN = Path(
    "logs/issue236_pipeline_connected_review_smoke/corrected_20260709_125046"
)
WORK_ROOT = Path("logs/issue244_local_probe/current_canonical_ab")
RUN_ID = "current_canonical_page001"
PAGE_ID = "page_001"
EXPECTED = [1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_expected(value: str) -> list[int]:
    try:
        result = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected row starts must be comma-separated integers"
        ) from exc
    if not result:
        raise argparse.ArgumentTypeError("expected row starts must not be empty")
    return result


def systems(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages or not isinstance(pages[0], dict):
        raise ValueError(f"No usable pages[0] in {path}")
    value = pages[0].get("systems")
    if not isinstance(value, list):
        raise ValueError(f"No usable pages[0].systems in {path}")
    return [item for item in value if isinstance(item, dict)]


def row_starts(items: list[dict[str, Any]]) -> list[int | None]:
    result: list[int | None] = []
    for system in items:
        measures = system.get("measures")
        if not isinstance(measures, list) or not measures:
            result.append(None)
            continue
        measure = measures[0]
        result.append(measure.get("number") if isinstance(measure, dict) else None)
    return result


def measure_counts(items: list[dict[str, Any]]) -> list[int]:
    return [
        len(value) if isinstance(value := system.get("measures"), list) else 0
        for system in items
    ]


def summarize(run_dir: Path, page_id: str) -> dict[str, Any]:
    base_path = run_dir / "intermediate" / page_id / "numbering_base.json"
    final_path = run_dir / "outputs" / page_id / "numbering_final.json"
    mmr_path = run_dir / "intermediate" / page_id / "overrides_mmr.json"
    missing = [path for path in (base_path, final_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing numbering artifact(s): " + ", ".join(map(str, missing))
        )
    base_systems = systems(base_path)
    final_systems = systems(final_path)
    mmr = load_json(mmr_path) if mmr_path.exists() else {}
    return {
        "run_dir": str(run_dir),
        "base_measure_counts": measure_counts(base_systems),
        "base_row_starts": row_starts(base_systems),
        "final_row_starts": row_starts(final_systems),
        "mmr_overrides": mmr.get("measure_overrides", []),
    }


def delta(
    minuend: list[int | None], subtrahend: list[int | None]
) -> list[int | None]:
    result: list[int | None] = []
    for left, right in zip(minuend, subtrahend, strict=False):
        result.append(None if left is None or right is None else left - right)
    return result


def prepare_config(source: Path, destination: Path, work_root: Path) -> None:
    config = load_json(source)
    if not isinstance(config, dict):
        raise TypeError(f"Expected object config: {source}")

    inputs = config.setdefault("inputs", {})
    if not isinstance(inputs, dict):
        raise TypeError("config.inputs must be an object")
    pdf_options = inputs.setdefault("pdf_to_images", {})
    if not isinstance(pdf_options, dict):
        raise TypeError("config.inputs.pdf_to_images must be an object")
    # src.pdf_to_images.normalise_pages expects a comma-separated string.
    pdf_options["pages"] = "1"

    detection = config.setdefault("detection", {})
    if not isinstance(detection, dict):
        raise TypeError("config.detection must be an object")
    detection.update(
        {
            "enable_sr": True,
            "sr_scale": 2,
            "crop_recenter_on_bbox_ink": True,
            "hybrid_output_root": str(work_root / "hybrid"),
        }
    )

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
    write_json(destination, config)


def run_pipeline(
    repo_root: Path,
    config_path: Path,
    output_root: Path,
    run_id: str,
    log_path: Path,
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
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as stream:
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


def create_review_zip(
    repo_root: Path,
    work_root: Path,
    run_dir: Path,
    config_path: Path,
    log_path: Path,
    comparison_path: Path,
    page_id: str,
) -> Path:
    archive_path = work_root.with_name(f"{work_root.name}_review.zip")
    archive_path.unlink(missing_ok=True)
    paths = [
        config_path,
        log_path,
        comparison_path,
        run_dir / "manifest.json",
        run_dir / "pipeline.log",
        run_dir / "intermediate" / page_id / "numbering_base.json",
        run_dir / "intermediate" / page_id / "overrides_mmr.json",
        run_dir / "outputs" / page_id / "numbering_final.json",
    ]
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, path.relative_to(repo_root))
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", type=Path, default=SOURCE_CONFIG)
    parser.add_argument("--baseline-run", type=Path, default=BASELINE_RUN)
    parser.add_argument("--work-root", type=Path, default=WORK_ROOT)
    parser.add_argument("--run-id", default=RUN_ID)
    parser.add_argument("--page-id", default=PAGE_ID)
    parser.add_argument(
        "--expected-row-starts",
        type=parse_expected,
        default=EXPECTED,
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    source_config = (repo_root / args.source_config).resolve()
    baseline_run = (repo_root / args.baseline_run).resolve()
    work_root = (repo_root / args.work_root).resolve()
    output_root = work_root / "runs"
    run_dir = output_root / args.run_id
    config_path = work_root / "current_canonical_page001.json"
    log_path = work_root / "driver_stdout_stderr.log"
    comparison_path = work_root / "ab_comparison.json"

    for path in (source_config, baseline_run):
        if not path.exists():
            raise FileNotFoundError(path)
    try:
        relative_work_root = work_root.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("--work-root must be inside the repository") from exc

    if run_dir.exists():
        if not args.force:
            raise FileExistsError(f"Run exists; use --force: {run_dir}")
        shutil.rmtree(run_dir)
    if args.force:
        for path in (work_root / "hybrid", work_root / "mmr_debug"):
            if path.exists():
                shutil.rmtree(path)

    work_root.mkdir(parents=True, exist_ok=True)
    prepare_config(source_config, config_path, relative_work_root)
    print(f"Prepared: {config_path.relative_to(repo_root)}")
    print("Changed only: enable_sr=true, sr_scale=2, crop_recenter=true")
    print("PDF page selector: '1' (string)")
    if args.prepare_only:
        return 0

    status = run_pipeline(
        repo_root,
        config_path.relative_to(repo_root),
        output_root.relative_to(repo_root),
        args.run_id,
        log_path,
    )
    if status != 0:
        print(f"Pipeline failed: status={status}", file=sys.stderr)
        print(f"Log: {log_path.relative_to(repo_root)}", file=sys.stderr)
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        print("\n".join(lines[-120:]), file=sys.stderr)
        return status

    baseline = summarize(baseline_run, args.page_id)
    candidate = summarize(run_dir, args.page_id)
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
            "base_measure_count_delta_candidate_minus_baseline": delta(
                candidate["base_measure_counts"], baseline["base_measure_counts"]
            ),
            "final_row_start_delta_candidate_minus_baseline": delta(
                candidate["final_row_starts"], baseline["final_row_starts"]
            ),
            "expected_minus_baseline_final": delta(
                expected, baseline["final_row_starts"]
            ),
            "expected_minus_candidate_final": delta(
                expected, candidate["final_row_starts"]
            ),
            "candidate_matches_expected": candidate["final_row_starts"] == expected,
        },
    }
    write_json(comparison_path, report)
    archive_path = create_review_zip(
        repo_root,
        work_root,
        run_dir,
        config_path,
        log_path,
        comparison_path,
        args.page_id,
    )

    print("A/B summary")
    print(f"  expected:  {expected}")
    print(f"  baseline:  {baseline['final_row_starts']}")
    print(f"  candidate: {candidate['final_row_starts']}")
    print(
        "  base count delta: "
        f"{report['comparison']['base_measure_count_delta_candidate_minus_baseline']}"
    )
    print(f"  comparison: {comparison_path.relative_to(repo_root)}")
    print(f"  review zip: {archive_path.relative_to(repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
