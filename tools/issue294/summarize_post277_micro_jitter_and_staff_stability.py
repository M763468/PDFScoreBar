#!/usr/bin/env python3
"""Summarize retained Issue #294 micro-jitter selection and B/C staff geometry.

Host-only. Reads completed retained diagnostics and matrix artifacts; it does not run
HOMR, detector, CNN, OCR, or MMR inference. Selection policies are fixed and do not
use expected values except to report whether a selected result matches the fixture.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.pipeline import StaffExtractor
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue294.rescore_full68_mmr_audit import (
    _load_json,
    _load_matrix_pages,
    _resolve_project_path,
)
from tools.issue294.run_post277_mapping_guarded_mmr import DEFAULT_MANIFEST

LOG_ROOT = PROJECT_ROOT / "logs/issue294"
MICRO_SUFFIX = "_0.0025"
MICRO_NAMES = (
    "left_in" + MICRO_SUFFIX,
    "right_in" + MICRO_SUFFIX,
    "symmetric_in" + MICRO_SUFFIX,
    "symmetric_out" + MICRO_SUFFIX,
    "translate_left" + MICRO_SUFFIX,
    "translate_right" + MICRO_SUFFIX,
)
CORE_NAMES = ("native", "symmetric_in_0.0025", "translate_right_0.0025")


def _latest_completed(pattern: str) -> tuple[Path, Mapping[str, Any]]:
    candidates = sorted(LOG_ROOT.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        payload = _load_json(path)
        if isinstance(payload, Mapping) and payload.get("status") == "completed":
            return path, payload
    raise FileNotFoundError(f"No completed artifact matches {pattern}")


def _event_index(payload: Mapping[str, Any]) -> dict[tuple[str, int, int], Mapping[str, Any]]:
    result: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    pages = payload.get("pages")
    if not isinstance(pages, Mapping):
        return result
    for page_id, page in pages.items():
        if not isinstance(page, Mapping):
            continue
        events = page.get("events")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, Mapping):
                continue
            result[(str(page_id), int(event["system"]), int(event["measure"]))] = event
    return result


def _view(skip: Any, score: Any) -> dict[str, Any]:
    return {
        "skip": None if skip is None else int(skip),
        "score": float(score or 0.0),
    }


def _select_max_score(views: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    valid = [(name, value) for name, value in views.items() if value.get("skip") is not None]
    if not valid:
        return {"view": None, "skip": None, "score": 0.0}
    name, value = max(valid, key=lambda item: (float(item[1]["score"]), item[0]))
    return {"view": name, "skip": int(value["skip"]), "score": float(value["score"])}


def _select_vote_then_score(views: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    valid = [(name, value) for name, value in views.items() if value.get("skip") is not None]
    if not valid:
        return {"view": None, "skip": None, "score": 0.0, "votes": 0}
    counts = Counter(int(value["skip"]) for _name, value in valid)
    max_votes = max(counts.values())
    leaders = {skip for skip, count in counts.items() if count == max_votes}
    name, value = max(
        ((name, value) for name, value in valid if int(value["skip"]) in leaders),
        key=lambda item: (float(item[1]["score"]), item[0]),
    )
    return {
        "view": name,
        "skip": int(value["skip"]),
        "score": float(value["score"]),
        "votes": int(max_votes),
    }


def _micro_summary() -> dict[str, Any]:
    jitter_path, jitter = _latest_completed("issue294_post277_edge_jitter_*.json")
    retry_path, retry = _latest_completed("issue294_post277_mmr_retry_evolution_*.json")
    native_index = _event_index(retry)
    rows: list[dict[str, Any]] = []
    pages = jitter.get("pages")
    if not isinstance(pages, Mapping):
        raise ValueError("Jitter artifact lacks pages")
    for page_id, page in pages.items():
        if not isinstance(page, Mapping):
            continue
        for event in page.get("events", []):
            if not isinstance(event, Mapping):
                continue
            key = (str(page_id), int(event["system"]), int(event["measure"]))
            native = native_index.get(key)
            if native is None:
                raise RuntimeError(f"Native retry event missing: {key}")
            native_policy = native.get("current_policy_final")
            if not isinstance(native_policy, Mapping):
                raise ValueError(f"Native event lacks current_policy_final: {key}")
            views: dict[str, dict[str, Any]] = {
                "native": _view(native_policy.get("skip"), native_policy.get("score"))
            }
            probes = event.get("probes")
            if not isinstance(probes, Mapping):
                raise ValueError(f"Jitter event lacks probes: {key}")
            for name in MICRO_NAMES:
                probe = probes.get(name)
                if not isinstance(probe, Mapping):
                    continue
                policy = probe.get("current_policy")
                if isinstance(policy, Mapping):
                    views[name] = _view(policy.get("skip"), policy.get("score"))
            expected = event.get("expected_skip")
            all_max = _select_max_score(views)
            all_vote = _select_vote_then_score(views)
            core = {name: views[name] for name in CORE_NAMES if name in views}
            core_max = _select_max_score(core)
            rows.append(
                {
                    "key": f"{page_id} s{key[1]} m{key[2]}",
                    "expected_skip": expected,
                    "views": views,
                    "policies": {
                        "core_max_score": {
                            **core_max,
                            "expected": expected is not None and core_max["skip"] == int(expected),
                        },
                        "all_micro_max_score": {
                            **all_max,
                            "expected": expected is not None and all_max["skip"] == int(expected),
                        },
                        "all_micro_vote_then_score": {
                            **all_vote,
                            "expected": expected is not None and all_vote["skip"] == int(expected),
                        },
                    },
                }
            )
    return {"jitter_artifact": str(jitter_path), "retry_artifact": str(retry_path), "rows": rows}


def _bbox(staff: Any) -> tuple[int, int, int, int]:
    box = staff.bbox
    return int(box.x1), int(box.y1), int(box.x2), int(box.y2)


def _max_delta(left: list[tuple[int, int, int, int]], right: list[tuple[int, int, int, int]]) -> int | None:
    if len(left) != len(right):
        return None
    return max((abs(a - b) for lb, rb in zip(left, right) for a, b in zip(lb, rb)), default=0)


def _staff_summary() -> dict[str, Any]:
    manifest = _load_json(DEFAULT_MANIFEST)
    matrix_pages = _load_matrix_pages(manifest)
    page_id_by_key = {(spec.score, spec.page_name): spec.page_id for spec in build_page_specs()}
    extractor = StaffExtractor()
    details: list[dict[str, Any]] = []
    for key, page in sorted(matrix_pages.items()):
        image = cv2.imread(str(_resolve_project_path(str(page["image"]))))
        if image is None:
            raise FileNotFoundError(page["image"])
        height, width = image.shape[:2]
        native = page["modes"]["candidate_native_geometry"]["variants"]
        b_path = _resolve_project_path(str(native["B_b377"]["staff_mask"]))
        c_path = _resolve_project_path(str(native["C_latest"]["staff_mask"]))
        b = [_bbox(staff) for staff in extractor.extract(b_path, (width, height))]
        c = [_bbox(staff) for staff in extractor.extract(c_path, (width, height))]
        exact = b == c
        x1_exact = len(b) == len(c) and [item[0] for item in b] == [item[0] for item in c]
        details.append(
            {
                "page_id": str(page_id_by_key.get(key, "")),
                "score": key[0],
                "page_name": key[1],
                "B_count": len(b),
                "C_count": len(c),
                "count_equal": len(b) == len(c),
                "bbox_exact": exact,
                "x1_exact": x1_exact,
                "max_abs_bbox_delta": _max_delta(b, c),
                "B": [list(item) for item in b],
                "C": [list(item) for item in c],
            }
        )
    comparable = [item for item in details if item["max_abs_bbox_delta"] is not None]
    focus_ids = {"page_002", "page_022", "page_034", "page_042"}
    return {
        "pages": len(details),
        "staff_count_equal_pages": sum(bool(item["count_equal"]) for item in details),
        "staff_bbox_exact_pages": sum(bool(item["bbox_exact"]) for item in details),
        "staff_x1_exact_pages": sum(bool(item["x1_exact"]) for item in details),
        "max_abs_bbox_delta": max((int(item["max_abs_bbox_delta"]) for item in comparable), default=0),
        "focused": [item for item in details if item["page_id"] in focus_ids],
    }


def main() -> int:
    micro = _micro_summary()
    staff = _staff_summary()
    print(f"jitter_artifact={micro['jitter_artifact']}")
    print(f"retry_artifact={micro['retry_artifact']}")
    print("\n=== 0.25% native-B micro-jitter views and fixed policies ===")
    for row in micro["rows"]:
        print(json.dumps(row, ensure_ascii=False))
    print("\n=== B/C StaffExtractor geometry ===")
    compact_staff = {key: value for key, value in staff.items() if key != "focused"}
    print(json.dumps(compact_staff, ensure_ascii=False))
    for item in staff["focused"]:
        print(json.dumps(item, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
