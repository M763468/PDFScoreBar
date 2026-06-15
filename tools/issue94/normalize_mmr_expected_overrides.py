#!/usr/bin/env python3
"""
Normalize manual MMR ground truth annotations (rest_gt.json) into standard
expected overrides format matching numbering_base.json.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def map_global_index_to_coords(numbering_data: Dict[str, Any]) -> List[Tuple[int, int]]:
    """
    Returns a list mapping global_index -> (system_idx, measure_idx)
    """
    mapping = []
    if "pages" in numbering_data:
        page = numbering_data["pages"][0]
        for s_idx, system in enumerate(page.get("systems", [])):
            for m_idx, measure in enumerate(system.get("measures", [])):
                mapping.append((s_idx, m_idx))
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert rest_gt.json files to page-wise expected overrides json."
    )
    parser.add_argument(
        "--rest-gt-root",
        type=Path,
        default=Path("data/evaluation2/rest_gt"),
    )
    parser.add_argument(
        "--numbering-root",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/intermediate"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/stage_e_full_pipeline/manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("tests/fixtures"),
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        raise SystemExit(f"Manifest not found: {args.manifest}")

    manifest_data = load_json(args.manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    processed_count = 0

    for p in manifest_data.get("pages", []):
        page_id = p.get("page_id")
        img_path_str = p.get("image_path", "")
        if not page_id or not img_path_str:
            continue

        img_name = Path(img_path_str).name
        # Extract page token and work name
        match = re.search(r"(_page_\d+)\.png", img_name)
        if not match:
            match = re.search(r"(page_\d+)", img_name)

        if match:
            page_token = match.group(1).lstrip("_")
            work_name = (
                img_name.replace(f"_{page_token}.png", "")
                .replace(f"{page_token}.png", "")
                .rstrip("_")
            )
        else:
            page_token = page_id
            work_name = "unknown"

        # Locate manual GT
        gt_path = args.rest_gt_root / work_name / page_token / "rest_gt.json"
        if not gt_path.exists():
            # Try lowercase or other alternates if not found
            continue

        # Load GT
        try:
            gt_data = load_json(gt_path)
            overrides = gt_data.get("overrides", [])
        except Exception as e:
            print(f"Error loading GT for {page_id} ({gt_path}): {e}")
            continue

        # Skip if no MMR annotations (defaults to empty list)
        gt_mmr_list = [o for o in overrides if o.get("rest_count", 1) >= 2]
        if not gt_mmr_list:
            continue

        # Load numbering_base
        numbering_path = args.numbering_root / page_id / "numbering_base.json"
        if not numbering_path.exists():
            print(f"Skipping {page_id}: numbering_base.json not found at {numbering_path}")
            continue

        numbering_data = load_json(numbering_path)
        global_map = map_global_index_to_coords(numbering_data)

        # Load detected overrides (predictions) for best shift alignment
        pred_path = args.numbering_root / page_id / "overrides_mmr.json"
        pred_map = {}
        if pred_path.exists():
            try:
                pred_data = load_json(pred_path).get("measure_overrides", [])
                for item in pred_data:
                    key = (item["system"], item["measure"])
                    pred_map[key] = item.get("skip", 0) + 1
            except Exception:
                pass

        # 3. Robust Matching (Shift Search)
        best_shift = 0
        max_tps = 0

        # Try to find the shift that aligns the GT measure_index with the predicted (system, measure) overrides
        for s in [-2, -1, 0, 1, 2]:
            current_tps = 0
            for item in gt_mmr_list:
                g_idx = item.get("measure_index")
                if g_idx is None:
                    continue
                target_idx = g_idx + s
                if 0 <= target_idx < len(global_map):
                    key = global_map[target_idx]
                    if key in pred_map:
                        # Match if prediction count matches or at least exists
                        current_tps += 1
            if current_tps > max_tps:
                max_tps = current_tps
                best_shift = s

        if best_shift != 0:
            print(
                f"  [INFO] Detected index shift of {best_shift:+} for {page_id} ({work_name}/{page_token})"
            )

        # Map to expected overrides format
        expected_overrides = []
        page_num_idx = int(page_id.split("_")[1]) - 1
        for item in gt_mmr_list:
            g_idx = item.get("measure_index")
            rest_count = item.get("rest_count", 1)
            if g_idx is None:
                continue

            target_idx = g_idx + best_shift
            if 0 <= target_idx < len(global_map):
                s_idx, m_idx = global_map[target_idx]
                expected_overrides.append(
                    {
                        "page": page_num_idx,
                        "system": s_idx,
                        "measure": m_idx,
                        "skip": rest_count - 1,
                    }
                )
            else:
                print(
                    f"  [Warn] Out-of-bounds target index {target_idx} for GT index {g_idx} (shift {best_shift}) on {page_id}"
                )

        if expected_overrides:
            out_path = args.output_dir / f"expected_overrides_{page_id}.json"
            with open(out_path, "w", encoding="utf-8") as out_f:
                json.dump({"overrides": expected_overrides}, out_f, indent=2)
            processed_count += 1

    print(
        f"\nSuccessfully generated {processed_count} expected override JSON files under {args.output_dir}"
    )


if __name__ == "__main__":
    main()
