#!/usr/bin/env python3
"""Diagnose the Issue #372 Shostakovich page_021 post-CNN staff-band rejection.

Retained-only. Compares the exact three visible barline candidates against the
row bands that CNN scoring derives from the candidate-filter root.

The current late-raw route is compared with the retained historical D27
producer geometry. No inference or threshold tuning is performed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.barline_evaluation import is_barline_match
from src.pipeline.probe_detector.bands import build_row_stats
from tools.issue120 import eval_full68_from_intermediates as full68_eval

SCORE = "Shostakovich-Sym5-Va"
PAGE = "page_021"
TARGETS = (
    (1333, 798, 1340, 894),
    (1769, 798, 1778, 896),
    (2749, 802, 2756, 900),
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(raw: Sequence[Any]) -> tuple[int, int, int, int]:
    return tuple(int(round(float(v))) for v in raw[:4])  # type: ignore[return-value]


def _boxes(path: Path) -> list[tuple[int, int, int, int]]:
    payload = _load(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected list payload: {path}")
    out = []
    for row in payload:
        raw = row.get("bbox") if isinstance(row, Mapping) else row
        if isinstance(raw, (list, tuple)) and len(raw) >= 4:
            out.append(_norm(raw))
    return out


def _find(root: Path, filename: str) -> Path:
    record = full68_eval.PageRecord(score=SCORE, page=PAGE)
    path = full68_eval.find_page_file(root, record, filename)
    if path is None or not path.is_file():
        raise FileNotFoundError(f"{SCORE}/{PAGE}: {filename} under {root}")
    return path


def _matches(a: Sequence[int], b: Sequence[int]) -> bool:
    return is_barline_match(
        a,
        b,
        rule_name="center_anchor",
        vov_threshold=0.5,
        xdist_threshold=12.0,
    )


def _band_vov(box: Sequence[int], band: tuple[int, int]) -> float:
    y1, y2 = float(box[1]), float(box[3])
    by1, by2 = float(band[0]), float(band[1])
    height = max(1.0, y2 - y1)
    overlap = max(0.0, min(y2, by2) - max(y1, by1))
    return overlap / height


def _variant(
    *,
    name: str,
    filtered_root: Path,
    probe_root: Path,
) -> dict[str, Any]:
    filtered_path = _find(filtered_root, "pipeline2_no_peak_candidates.json")
    probe_path = _find(probe_root, "pipeline2_no_peak_candidates.json")
    filtered = _boxes(filtered_path)
    probe = _boxes(probe_path)

    stats = build_row_stats(filtered, cluster_max_dist=None, min_row_count=1)
    bands = [
        (int(row["top"]), int(row["bottom"]))
        for row in stats
        if float(row["bottom"]) >= float(row["top"])
    ]

    rows = []
    for target in TARGETS:
        matching_filtered = [box for box in filtered if _matches(box, target)]
        matching_probe = [box for box in probe if _matches(box, target)]
        best_band = None
        best_vov = 0.0
        for band in bands:
            vov = _band_vov(target, band)
            if best_band is None or vov > best_vov:
                best_band = band
                best_vov = vov

        target_cy = (target[1] + target[3]) / 2.0
        nearest_bands = sorted(
            bands,
            key=lambda band: abs(((band[0] + band[1]) / 2.0) - target_cy),
        )[:3]

        rows.append(
            {
                "target": list(target),
                "matching_filtered": [list(box) for box in matching_filtered],
                "matching_probe": [list(box) for box in matching_probe],
                "best_band": list(best_band) if best_band is not None else None,
                "best_band_vov": best_vov,
                "passes_cnn_staff_vov_0p5": best_vov >= 0.5,
                "nearest_bands": [
                    {
                        "band": list(band),
                        "vov": _band_vov(target, band),
                        "center_distance": abs(
                            ((band[0] + band[1]) / 2.0) - target_cy
                        ),
                    }
                    for band in nearest_bands
                ],
            }
        )

    return {
        "name": name,
        "filtered_path": str(filtered_path),
        "probe_path": str(probe_path),
        "filtered_count": len(filtered),
        "probe_count": len(probe),
        "median_filtered_height": (
            sorted(abs(b[3] - b[1]) for b in filtered)[len(filtered) // 2]
            if filtered
            else None
        ),
        "row_band_count": len(bands),
        "row_bands": [list(band) for band in bands],
        "targets": rows,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    late = args.late_run_root.resolve()
    d27 = args.d27_run_root.resolve()
    output = args.output.resolve()

    if output.exists():
        raise FileExistsError(output)

    late_filtered = late / "filtered"
    late_probe = (
        late
        / "late_raw_route"
        / "dense_candidate_reconstruction"
        / "probe_rescue_candidates"
    )
    d27_route = (
        d27
        / "runs"
        / SCORE
        / "intermediate"
        / "dense_full_pipeline_route"
        / "dense_candidate_reconstruction"
    )
    d27_filtered = d27_route / "probe_candidates_filtered"
    d27_probe = d27_route / "probe_rescue_candidates"

    for path in (late_filtered, late_probe, d27_filtered, d27_probe):
        if not path.is_dir():
            raise FileNotFoundError(path)

    variants = [
        _variant(
            name="late_raw_current_geometry",
            filtered_root=late_filtered,
            probe_root=late_probe,
        ),
        _variant(
            name="historical_d27_producer_geometry",
            filtered_root=d27_filtered,
            probe_root=d27_probe,
        ),
    ]

    payload = {
        "schema_version": "issue372.page021_staff_overlap_diagnostic.v1",
        "score": SCORE,
        "page": PAGE,
        "cnn_staff_filter_contract": {
            "band_source": "filtered_root row stats",
            "build_row_stats_cluster_max_dist": None,
            "build_row_stats_min_row_count": 1,
            "staff_vov_threshold": 0.5,
        },
        "targets": [list(box) for box in TARGETS],
        "variants": variants,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("=== Issue #372 page_021 staff-overlap diagnostic ===")
    for variant in variants:
        print(
            f"\n{variant['name']}: "
            f"filtered={variant['filtered_count']} "
            f"probe={variant['probe_count']} "
            f"bands={variant['row_band_count']}"
        )
        for row in variant["targets"]:
            print(
                f"  target={row['target']} "
                f"filtered_matches={len(row['matching_filtered'])} "
                f"probe_matches={len(row['matching_probe'])} "
                f"best_band={row['best_band']} "
                f"vov={row['best_band_vov']:.6f} "
                f"pass={row['passes_cnn_staff_vov_0p5']}"
            )
    print(f"\nOUTPUT={output}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--late-run-root", type=Path, required=True)
    parser.add_argument("--d27-run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
