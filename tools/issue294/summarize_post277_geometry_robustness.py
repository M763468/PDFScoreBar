#!/usr/bin/env python3
"""Print compact decision-relevant summaries for the latest Issue #294 geometry probes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_ROOT = PROJECT_ROOT / "logs/issue294"


def _latest(pattern: str) -> Path:
    matches = sorted(LOG_ROOT.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(pattern)
    return matches[-1]


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("status") != "completed":
        raise ValueError(f"Not a completed report: {path}")
    return value


def main() -> int:
    stability_path = _latest("issue294_maintained_family_detector_stability_*.json")
    jitter_path = _latest("issue294_post277_edge_jitter_*.json")
    stability = _load(stability_path)
    jitter = _load(jitter_path)

    print(f"stability_artifact={stability_path}")
    print(f"jitter_artifact={jitter_path}")
    print("\n=== Maintained-family B/C stability ===")
    print(json.dumps({"pages": stability["pages"], "counts": stability["counts"], "differences": stability["differences"]}, ensure_ascii=False))

    print("\n=== B native edge-jitter expected hits ===")
    for page_id, page in jitter["pages"].items():
        for event in page["events"]:
            once_hits = []
            policy_hits = []
            for name, probe in event["probes"].items():
                if probe["once_expected"]:
                    once_hits.append(name)
                if probe["policy_expected"]:
                    policy_hits.append(name)
            out = {
                "key": f"{page_id} s{event['system']} m{event['measure']}",
                "expected_skip": event["expected_skip"],
                "native_bbox": event["native_bbox"],
                "once_expected_hits": once_hits,
                "policy_expected_hits": policy_hits,
            }
            print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
