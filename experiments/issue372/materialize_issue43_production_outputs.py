#!/usr/bin/env python3
"""Materialize Issue #43 saved production detector JSONs into a writable tree.

The Issue #43 full68 run may be owned by root because it was created through
Docker.  This helper reads the retained production run locations from the
Issue #43 report and copies only the detector JSON artifacts needed by Issue
#372 into a caller-selected writable directory.  It never reruns inference and
never writes into the Issue #43 run tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

FILENAMES = (
    "pipeline2_no_peak_candidates.json",
    "pipeline2_no_peak_scored.json",
    "pipeline2_no_peak_filtered_cnn.json",
)
EXPECTED_PAGES = 68


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _host_path(value: str | Path, *, source_repo_root: Path) -> Path:
    path = Path(value)
    try:
        return source_repo_root / path.relative_to("/workspace")
    except ValueError:
        return path


def run(*, report_path: Path, source_repo_root: Path, destination: Path) -> dict[str, Any]:
    report = _load_json(report_path)
    if not isinstance(report, Mapping):
        raise ValueError("Issue #43 report must be a JSON object")

    production_runs = report.get("provenance", {}).get("production_runs", [])
    if not isinstance(production_runs, list) or not production_runs:
        raise ValueError(
            "Issue #43 report has no provenance.production_runs; "
            "the original fresh-upstream run is required"
        )

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=False)

    copied_pages: list[dict[str, Any]] = []
    seen_page_dirs: set[str] = set()

    for run in production_runs:
        if not isinstance(run, Mapping):
            raise ValueError(f"Invalid production run record: {run!r}")
        raw_probe_root = run.get("probe_output_dir")
        if not raw_probe_root:
            raise ValueError(f"Production run lacks probe_output_dir: {run!r}")
        probe_root = _host_path(raw_probe_root, source_repo_root=source_repo_root)
        if not probe_root.is_dir():
            raise FileNotFoundError(
                f"Saved production probe output is missing: {probe_root} "
                f"(reported as {raw_probe_root})"
            )

        for filtered in sorted(probe_root.rglob("pipeline2_no_peak_filtered_cnn.json")):
            page_dir = filtered.parent
            page_name = page_dir.name
            if page_name in seen_page_dirs:
                raise RuntimeError(f"Duplicate production page directory: {page_name}")
            seen_page_dirs.add(page_name)

            target = destination / page_name
            target.mkdir(parents=True, exist_ok=False)
            copied_files: list[str] = []
            for filename in FILENAMES:
                source = page_dir / filename
                if source.is_file():
                    shutil.copyfile(source, target / filename)
                    copied_files.append(filename)

            missing = [
                filename
                for filename in (
                    "pipeline2_no_peak_candidates.json",
                    "pipeline2_no_peak_filtered_cnn.json",
                )
                if filename not in copied_files
            ]
            if missing:
                raise FileNotFoundError(
                    f"{page_name}: missing required detector artifacts: {missing}"
                )
            copied_pages.append(
                {
                    "page_dir": page_name,
                    "source": str(page_dir),
                    "destination": str(target),
                    "files": copied_files,
                }
            )

    if len(copied_pages) != EXPECTED_PAGES:
        raise RuntimeError(
            f"Expected {EXPECTED_PAGES} saved production pages, copied {len(copied_pages)}"
        )

    result = {
        "schema_version": "issue372.materialized_current_production.v1",
        "source_report": str(report_path),
        "source_repo_root": str(source_repo_root),
        "destination": str(destination),
        "page_count": len(copied_pages),
        "pages": copied_pages,
    }
    manifest = destination / "materialization_manifest.json"
    manifest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"materialized_pages={len(copied_pages)}")
    print(f"destination={destination}")
    print(f"manifest={manifest}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-repo-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    run(
        report_path=args.report.resolve(),
        source_repo_root=args.source_repo_root.resolve(),
        destination=args.destination.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
