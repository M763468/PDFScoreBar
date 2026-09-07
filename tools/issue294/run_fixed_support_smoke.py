#!/usr/bin/env python3
"""Run a cheap Issue #294 fixed-support smoke without shell fail-fast semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2

from tools.issue294.run_downstream_candidate_matrix import _generate_fixed_support


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run(image: Path, output_root: Path) -> dict[str, Any]:
    report_path = output_root / "smoke_report.json"
    if report_path.is_file():
        payload = _load_json(report_path)
        if isinstance(payload, dict) and payload.get("status") == "completed":
            return payload
    if output_root.exists():
        raise RuntimeError(
            f"Smoke output exists without a completed report: {output_root}. "
            "Use a new output root; retained artifacts are not overwritten."
        )
    if not image.is_file():
        raise FileNotFoundError(image)

    result = _generate_fixed_support(image, output_root)
    sr_image = Path(str(result["sr_image"]))
    source_data = cv2.imread(str(image))
    sr_data = cv2.imread(str(sr_image))
    if source_data is None:
        raise FileNotFoundError(image)
    if sr_data is None:
        raise FileNotFoundError(sr_image)

    source_height, source_width = source_data.shape[:2]
    sr_height, sr_width = sr_data.shape[:2]
    required_outputs = {
        key: Path(str(result.get(key, ""))).is_file()
        for key in (
            "current_sr_detection",
            "current_omr",
            "current_homr_staff_mask",
            "connector_symbols",
            "connector_brace_dot",
        )
    }
    checks = {
        "source_wh": [source_width, source_height],
        "sr_wh": [sr_width, sr_height],
        "true_x4": (sr_width, sr_height) == (source_width * 4, source_height * 4),
        "sr_scale": int(result.get("sr_scale", 0)),
        "sr_sha_differs_from_source": _sha256(sr_image) != _sha256(image),
        "connector_complete": result.get("connector_complete") is True,
        "required_outputs": required_outputs,
    }
    passed = (
        checks["true_x4"]
        and checks["sr_scale"] == 4
        and checks["sr_sha_differs_from_source"]
        and checks["connector_complete"]
        and all(required_outputs.values())
    )
    payload = {
        "schema_version": "issue294.fixed_support_smoke.v1",
        "status": "completed" if passed else "failed",
        "image": str(image),
        "output_root": str(output_root),
        "support_result": result,
        "checks": checks,
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not passed:
        raise RuntimeError(f"Fixed-support smoke failed checks: {checks}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = run(args.image, args.output_root)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
