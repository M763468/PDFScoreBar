#!/usr/bin/env python3
"""Compact stdout summary for the retained Issue #294 boundary-source diagnostic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.issue294.diagnose_post277_measure_boundary_sources import run


def main() -> int:
    payload = run()
    print(f"status={payload['status']}")
    for page_id, page in payload["pages"].items():
        a_events = page["variants"]["A_production"]["events"]
        b_events = page["variants"]["B_b377_mapping_guarded"]["events"]
        for comp, a, b in zip(page["comparisons"], a_events, b_events):
            out = {
                "key": f"{page_id} s{comp['system']} m{comp['measure']}",
                "bbox_delta_B_minus_A": comp["measure_bbox_delta_B_minus_A"],
                "system_x1_delta_B_minus_A": comp["system_x1_delta_B_minus_A"],
                "left_source_A": comp["left_source_A"],
                "left_source_B": comp["left_source_B"],
                "left_bar_center_delta_B_minus_A": comp["left_bar_center_delta_B_minus_A"],
                "left_bar_width_delta_B_minus_A": comp["left_bar_width_delta_B_minus_A"],
                "right_source_A": comp["right_source_A"],
                "right_source_B": comp["right_source_B"],
                "right_bar_center_delta_B_minus_A": comp["right_bar_center_delta_B_minus_A"],
                "right_bar_width_delta_B_minus_A": comp["right_bar_width_delta_B_minus_A"],
                "A_left_exact": a["left"]["exact_membership"],
                "B_left_exact": b["left"]["exact_membership"],
                "A_right_exact": a["right"]["exact_membership"],
                "B_right_exact": b["right"]["exact_membership"],
                "A_staff_x1": a["system_staff_x1"],
                "B_staff_x1": b["system_staff_x1"],
            }
            print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
