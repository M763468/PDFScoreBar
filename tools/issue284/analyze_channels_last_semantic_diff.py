"""Analyze already-materialized Issue #284 channels-last downstream artifacts.

This is a no-inference follow-up to run_channels_last_downstream_gate.py. It
separates current-HOMR JSON differences into geometry/topology fields and
summarizes whether the few changed mask pixels alter connected-component
structure. The input gate JSON must point at retained candidate/reference files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _bbox_delta(left: list[int] | tuple[int, ...], right: list[int] | tuple[int, ...]) -> list[int]:
    return [int(a) - int(b) for a, b in zip(left, right)]


def _prediction_semantics(candidate: Path, reference: Path) -> dict[str, Any]:
    cand = _load_json(candidate)
    ref = _load_json(reference)
    cp = list(cand.get("predictions", [])) if isinstance(cand, dict) else []
    rp = list(ref.get("predictions", [])) if isinstance(ref, dict) else []
    count = min(len(cp), len(rp))

    orig_deltas: list[list[int]] = []
    pred_deltas: list[list[int]] = []
    orig_diff_indices: list[int] = []
    pred_diff_indices: list[int] = []
    system_diff_indices: list[int] = []
    staff_diff_indices: list[int] = []
    for index in range(count):
        c = cp[index]
        r = rp[index]
        co = list(c.get("orig_bbox", []))
        ro = list(r.get("orig_bbox", []))
        if co != ro:
            orig_diff_indices.append(index)
            if len(co) == len(ro) == 4:
                orig_deltas.append(_bbox_delta(co, ro))
        cpb = list(c.get("pred_bbox", []))
        rpb = list(r.get("pred_bbox", []))
        if cpb != rpb:
            pred_diff_indices.append(index)
            if len(cpb) == len(rpb) == 4:
                pred_deltas.append(_bbox_delta(cpb, rpb))
        if c.get("system_index") != r.get("system_index"):
            system_diff_indices.append(index)
        if c.get("staff_index") != r.get("staff_index"):
            staff_diff_indices.append(index)

    def delta_summary(values: list[list[int]]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "max_abs_coord_delta": 0, "unique_deltas": []}
        array = np.asarray(values, dtype=np.int32)
        unique = sorted({tuple(int(v) for v in row) for row in array.tolist()})
        return {
            "count": len(values),
            "max_abs_coord_delta": int(np.abs(array).max()),
            "unique_deltas": [list(row) for row in unique[:50]],
        }

    candidate_orig = [tuple(item.get("orig_bbox", [])) for item in cp]
    reference_orig = [tuple(item.get("orig_bbox", [])) for item in rp]
    candidate_topology = [
        (tuple(item.get("orig_bbox", [])), item.get("system_index"), item.get("staff_index"))
        for item in cp
    ]
    reference_topology = [
        (tuple(item.get("orig_bbox", [])), item.get("system_index"), item.get("staff_index"))
        for item in rp
    ]
    return {
        "candidate_count": len(cp),
        "reference_count": len(rp),
        "same_count": len(cp) == len(rp),
        "orig_bbox_equal_same_order": candidate_orig == reference_orig,
        "orig_bbox_equal_as_multiset": sorted(candidate_orig) == sorted(reference_orig),
        "topology_equal_same_order": candidate_topology == reference_topology,
        "topology_equal_as_multiset": sorted(candidate_topology) == sorted(reference_topology),
        "orig_bbox_differences": delta_summary(orig_deltas),
        "pred_bbox_differences": delta_summary(pred_deltas),
        "orig_bbox_diff_indices": orig_diff_indices,
        "pred_bbox_diff_indices": pred_diff_indices,
        "system_index_diff_indices": system_diff_indices,
        "staff_index_diff_indices": staff_diff_indices,
    }


def _component_signature(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    binary = (mask > 0).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    values = []
    for index in range(1, count):
        x, y, w, h, area = stats[index].tolist()
        values.append((int(x), int(y), int(w), int(h), int(area)))
    return sorted(values)


def _mask_semantics(candidate: Path, reference: Path) -> dict[str, Any]:
    cand = cv2.imread(str(candidate), cv2.IMREAD_GRAYSCALE)
    ref = cv2.imread(str(reference), cv2.IMREAD_GRAYSCALE)
    if cand is None or ref is None:
        raise FileNotFoundError(candidate if cand is None else reference)
    if cand.shape != ref.shape:
        return {"same_shape": False, "candidate_shape": list(cand.shape), "reference_shape": list(ref.shape)}

    cb = cand > 0
    rb = ref > 0
    changed = cb != rb
    ys, xs = np.nonzero(changed)
    c_sig = _component_signature(cand)
    r_sig = _component_signature(ref)
    result: dict[str, Any] = {
        "same_shape": True,
        "changed_binary_pixels": int(changed.sum()),
        "candidate_active_pixels": int(cb.sum()),
        "reference_active_pixels": int(rb.sum()),
        "added_pixels": int(np.logical_and(cb, ~rb).sum()),
        "removed_pixels": int(np.logical_and(~cb, rb).sum()),
        "candidate_component_count": len(c_sig),
        "reference_component_count": len(r_sig),
        "component_signatures_equal": c_sig == r_sig,
    }
    if len(xs):
        result["changed_pixel_bbox_xyxy"] = [
            int(xs.min()),
            int(ys.min()),
            int(xs.max()),
            int(ys.max()),
        ]
        result["changed_pixel_coordinates_xy"] = [
            [int(x), int(y)] for x, y in zip(xs[:200].tolist(), ys[:200].tolist())
        ]
    else:
        result["changed_pixel_bbox_xyxy"] = None
        result["changed_pixel_coordinates_xy"] = []
    if c_sig != r_sig:
        c_set = set(c_sig)
        r_set = set(r_sig)
        result["candidate_only_component_signatures"] = [list(x) for x in sorted(c_set - r_set)[:50]]
        result["reference_only_component_signatures"] = [list(x) for x in sorted(r_set - c_set)[:50]]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    gate = _load_json(args.gate.resolve())
    artifacts = gate["current_homr_artifacts"]
    detection = artifacts["current_sr_detection"]
    payload: dict[str, Any] = {
        "schema_version": "issue284.channels_last_semantic_diff.v1",
        "status": "completed",
        "gate": str(args.gate.resolve()),
        "current_homr_detection_semantics": _prediction_semantics(
            Path(detection["candidate"]), Path(detection["reference"])
        ),
        "masks": {},
        "omr_predictions_equal": bool(gate.get("omr_predictions_equal")),
        "hybrid_consensus_equal": bool(gate.get("hybrid_consensus_equal")),
    }
    for field in ("staff_mask", "connector_symbols", "connector_brace_dot"):
        item = artifacts[field]
        payload["masks"][field] = _mask_semantics(Path(item["candidate"]), Path(item["reference"]))

    det = payload["current_homr_detection_semantics"]
    payload["barline_topology_equal"] = bool(det["topology_equal_same_order"])
    payload["connector_component_topology_equal"] = all(
        bool(payload["masks"][field]["component_signatures_equal"])
        for field in ("connector_symbols", "connector_brace_dot")
    )
    payload["focused_semantics_preserved"] = bool(
        payload["barline_topology_equal"]
        and payload["connector_component_topology_equal"]
        and payload["omr_predictions_equal"]
        and payload["hybrid_consensus_equal"]
    )

    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
