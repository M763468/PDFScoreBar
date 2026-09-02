#!/usr/bin/env python3
"""Run the complete Issue #294 representative same-original host gate."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from tools.issue294.run_same_original_ab_host import (
    CONTAINER,
    CONTAINER_ROOT,
    PIPELINE_PYTHON,
    PROJECT_ROOT,
    run as run_ab_host,
)


def _container_path(host_path: Path) -> Path:
    relative = host_path.resolve().relative_to(PROJECT_ROOT.resolve())
    return CONTAINER_ROOT / relative


def run(run_tag: str, pages: list[str], support_root: Path | None = None) -> dict[str, str]:
    result = run_ab_host(run_tag, pages, support_root)
    summary = Path(result["summary"]).resolve()
    musicxml = summary.parent / "musicxml_comparison.json"
    if musicxml.exists():
        raise FileExistsError(musicxml)

    subprocess.run(
        [
            "docker",
            "exec",
            "-w",
            str(CONTAINER_ROOT),
            "-e",
            "PYTHONPATH=/workspace",
            CONTAINER,
            PIPELINE_PYTHON,
            "tools/issue294/compare_musicxml_ab.py",
            "--summary",
            str(_container_path(summary)),
            "--output",
            str(_container_path(musicxml)),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    if not musicxml.is_file():
        raise FileNotFoundError(musicxml)

    payload = json.loads(musicxml.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete MusicXML comparison: {musicxml}")

    result["musicxml_comparison"] = str(musicxml)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", required=True)
    parser.add_argument(
        "--page",
        action="append",
        choices=["012", "013", "014"],
        dest="pages",
        help="Representative page number. Repeat for multiple pages. Defaults to page 013.",
    )
    parser.add_argument("--support-root", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.run_tag, args.pages or ["013"], args.support_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"status": "completed", **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
