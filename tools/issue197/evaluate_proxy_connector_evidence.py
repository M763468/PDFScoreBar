from __future__ import annotations

import json
import lzma
from pathlib import Path
from typing import Any

import cv2
import numpy as np

TRACE = Path("logs/issue197_system_grouping/system_grouping_decision_trace.json")
OUT = Path("logs/issue197_system_grouping/proxy_connector_pair_evidence.json")

BASE_STAGE_E = Path(
    "logs/issue120_e2e_recovery/stage_e_hybrid_output/stage_e_full_pipeline/baseline/batch"
)
BASE_DEBUG = Path(
    "logs/full_pipeline_runs/dense_full_pipeline/hybrid_output/dense_full_pipeline/baseline/batch"
)

TARGET_PAIRS = {
    "page_021": {
        (2, 3): "known_false_split_divisi_candidate",
        (4, 5): "additional_trace_similar_false_split_candidate",
    },
    "page_022": {
        (0, 1): "known_false_split_divisi_candidate",
    },
    "page_045": {
        (10, 11): "known_false_merge_candidate",
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_proxy_npy(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    try:
        with lzma.open(path, "rb") as f:
            return np.load(f, allow_pickle=False)
    except Exception:
        try:
            return np.load(path, allow_pickle=False)
        except Exception:
            return None


def load_binary_image(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    arr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if arr is None:
        return None
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr


def to_binary(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == bool:
        return arr.astype(np.uint8)
    if arr.max(initial=0) <= 1:
        return (arr > 0).astype(np.uint8)
    return (arr > 0).astype(np.uint8)


def clip(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def map_roi_to_artifact(
    pair: dict[str, Any], original_shape_hw: tuple[int, int], artifact_shape_hw: tuple[int, int]
) -> tuple[int, int, int, int]:
    orig_h, orig_w = original_shape_hw
    art_h, art_w = artifact_shape_hw
    scale_x = art_w / orig_w
    scale_y = art_h / orig_h

    s1 = pair["s1_bbox"]
    s2 = pair["s2_bbox"]
    left = min(s1[0], s2[0])
    x1 = int(round((left - 100) * scale_x))
    x2 = int(round((left + 120) * scale_x))
    y1 = int(round(s1[3] * scale_y))
    y2 = int(round(s2[1] * scale_y))

    x1 = clip(x1, 0, art_w)
    x2 = clip(x2, 0, art_w)
    y1 = clip(y1, 0, art_h)
    y2 = clip(y2, 0, art_h)
    if x2 <= x1:
        x2 = min(art_w, x1 + 1)
    if y2 <= y1:
        y2 = min(art_h, y1 + 1)
    return x1, y1, x2, y2


def roi_stats(arr: np.ndarray | None, pair: dict[str, Any], original_shape_hw: tuple[int, int]) -> dict[str, Any]:
    if arr is None:
        return {"exists": False}

    binary = to_binary(arr)
    h, w = binary.shape[:2]
    x1, y1, x2, y2 = map_roi_to_artifact(pair, original_shape_hw, (h, w))
    roi = binary[y1:y2, x1:x2]
    nonzero = int(np.count_nonzero(roi))
    density = float(nonzero / max(1, roi.size))

    vertical_open = 0
    vertical_density = 0.0
    if roi.size:
        kernel_h = max(3, int(roi.shape[0] * 0.65))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, kernel_h))
        opened = cv2.morphologyEx((roi * 255).astype(np.uint8), cv2.MORPH_OPEN, kernel)
        vertical_open = int(cv2.countNonZero(opened))
        vertical_density = float(vertical_open / max(1, opened.size))

    return {
        "exists": True,
        "artifact_shape_hw": [int(h), int(w)],
        "roi_xyxy": [int(x1), int(y1), int(x2), int(y2)],
        "roi_shape_hw": [int(roi.shape[0]), int(roi.shape[1])],
        "nonzero": nonzero,
        "density": density,
        "vertical_open_pixels": vertical_open,
        "vertical_open_density": vertical_density,
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    trace = load_json(TRACE)

    report: dict[str, Any] = {"pages": {}}

    for page_id, page in trace["pages"].items():
        source = page["source"]
        original_shape_hw = tuple(page["image_shape"] if "image_shape" in page else page["image_shape_hw"])
        stage_dir = BASE_STAGE_E / source
        debug_dir = BASE_DEBUG / source

        artifacts = {
            "stage_proxy_npy": load_proxy_npy(stage_dir / f"{source}_proxy.npy"),
            "debug_symbols_png": load_binary_image(debug_dir / f"{source}_proxy_debug_4_symbols.png"),
            "debug_brace_dot_png": load_binary_image(debug_dir / f"{source}_proxy_debug_16_brace_dot.png"),
            "debug_bar_line_img_png": load_binary_image(debug_dir / f"{source}_proxy_debug_8_bar_line_img.png"),
        }

        pair_rows = []
        for pair in page["adjacent_staff_pairs"]:
            pair_tuple = tuple(pair["staff_pair"])
            evidence = {
                name: roi_stats(arr, pair, original_shape_hw) for name, arr in artifacts.items()
            }
            pair_rows.append(
                {
                    "staff_pair": list(pair_tuple),
                    "label": TARGET_PAIRS.get(page_id, {}).get(pair_tuple),
                    "current_same_system": pair["same_system"],
                    "passes_distance_gate": pair["passes_distance_gate"],
                    "aligned_connection": pair["aligned_connection"],
                    "aligned_barline_count": pair["aligned_barline_count_tol10"],
                    "trace_left_connector_open_pixels": pair["left_connector_ink"].get(
                        "gap_vertical_open_pixels"
                    ),
                    "evidence": evidence,
                }
            )

        report["pages"][page_id] = {
            "source": source,
            "original_shape_hw": list(original_shape_hw),
            "target_pairs": [r for r in pair_rows if r["label"]],
            "all_pairs": pair_rows,
        }

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
