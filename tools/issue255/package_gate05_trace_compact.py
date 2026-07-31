#!/usr/bin/env python3
"""Package only the machine-readable Issue #255 gate05 trace reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRACE_ROOT = ROOT / "logs/issue255_first_loss/issue255_gate_05_trace"
DEFAULT_OUTPUT = ROOT / "logs/issue255_first_loss/issue255_gate_05_trace_compact.tar.gz"
INCLUDED_NAMES = {
    "issue255_gate05_first_loss_summary.json",
    "focused_detector_inventory.json",
    "focused_detector_inventory.csv",
    "probe_boundary_report.json",
    "variant_report.json",
    "probe_debug.json",
    "target_metadata.json",
    "trace.stdout.txt",
    "trace.stderr.txt",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_report_files(trace_root: Path) -> list[Path]:
    trace_root = trace_root.resolve()
    if not trace_root.is_dir():
        raise FileNotFoundError(trace_root)
    files = sorted(
        path
        for path in trace_root.rglob("*")
        if path.is_file() and path.name in INCLUDED_NAMES
    )
    summary = trace_root / "issue255_gate05_first_loss_summary.json"
    if summary not in files:
        raise FileNotFoundError(summary)
    if not any(path.name == "focused_detector_inventory.json" for path in files):
        raise RuntimeError("No focused detector inventory found")
    if not any(path.name == "probe_boundary_report.json" for path in files):
        raise RuntimeError("No probe boundary reports found")
    return files


def build_compact_archive(*, trace_root: Path, output: Path) -> dict[str, Any]:
    trace_root = trace_root.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(output)
    files = collect_report_files(trace_root)
    records = [
        {
            "path": str(path.relative_to(trace_root)),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]
    manifest = {
        "schema_version": "issue255.gate05_trace_compact.v1",
        "status": "completed",
        "trace_root": str(trace_root),
        "file_count": len(records),
        "uncompressed_size_bytes": sum(record["size_bytes"] for record in records),
        "excluded": ["*.png", "*_candidates.json"],
        "files": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="issue255_trace_compact_") as temp_dir:
        manifest_path = Path(temp_dir) / "compact_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        with tarfile.open(output, "w:gz") as archive:
            root_name = trace_root.name
            archive.add(
                manifest_path,
                arcname=f"{root_name}/compact_manifest.json",
            )
            for path in files:
                archive.add(
                    path,
                    arcname=f"{root_name}/{path.relative_to(trace_root)}",
                )
    return {
        **manifest,
        "output": str(output),
        "archive_size_bytes": output.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-root", type=Path, default=DEFAULT_TRACE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        report = build_compact_archive(trace_root=args.trace_root, output=args.output)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
