#!/usr/bin/env python3
"""Create fixed evaluation2 full-run configs for the v12 restore experiment."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import yaml

SCORES: dict[str, list[str]] = {
    "Shostakovich-Festival_Overture_Va": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
        "page_007",
        "page_008",
        "page_009",
    ],
    "Shostakovich-Sym5-Va": [
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
        "page_007",
        "page_008",
        "page_009",
        "page_010",
        "page_011",
        "page_012",
        "page_013",
        "page_014",
        "page_015",
        "page_016",
        "page_018",
        "page_019",
        "page_020",
        "page_021",
        "page_022",
        "page_024",
        "page_025",
    ],
    "Sibelius-Violin_Concerto-Viola": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
        "page_007",
        "page_008",
        "page_009",
        "page_010",
    ],
    "Va_Prokofiev_Symphony1": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_006",
    ],
    "Va__Prokofiev_Symphony5": [
        "page_001",
        "page_002",
        "page_003",
        "page_004",
        "page_005",
        "page_007",
        "page_008",
        "page_009",
        "page_010",
        "page_011",
        "page_013",
        "page_014",
        "page_015",
        "page_016",
        "page_017",
        "page_018",
        "page_019",
        "page_020",
        "page_021",
        "page_022",
        "page_023",
    ],
}


def page_numbers(page_ids: list[str]) -> str:
    return ",".join(str(int(page.split("_")[1])) for page in page_ids)


def build_config(base_config: dict[str, Any], score: str, pages: list[str]) -> dict[str, Any]:
    config = copy.deepcopy(base_config)
    run_id = f"eval2_full_v12_restore_h25_th08_{score}"

    config["run"]["run_id"] = run_id
    config["run"]["output_root"] = "logs/full_pipeline_runs/evaluation2_full_v12_restore"
    config["inputs"]["pdf_path"] = f"data/evaluation2/pdfs/{score}.pdf"
    config["inputs"]["pdf_to_images"]["output_dir"] = f"data/evaluation2/images/{score}"
    config["inputs"]["pdf_to_images"]["dpi"] = 360
    config["inputs"]["pdf_to_images"]["pages"] = page_numbers(pages)

    config["steps"].update(
        {
            "pdf_to_images": False,
            "detection": True,
            "filter_pages": True,
            "apply_barline_overrides": False,
            "numbering_base": False,
            "mmr_overrides": False,
            "apply_measure_overrides": False,
            "overlay": False,
        }
    )
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-config",
        type=Path,
        default=Path("configs/evaluation2_e2e_verification_full_v12_restore.yaml"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("logs/issue120_e2e_recovery/eval2_full_configs"),
    )
    args = parser.parse_args()

    base_config = yaml.safe_load(args.base_config.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for score, pages in SCORES.items():
        config = build_config(base_config, score, pages)
        config_path = args.output_dir / f"{score}.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
        manifest.append(
            {
                "score": score,
                "run_id": config["run"]["run_id"],
                "config": str(config_path),
                "pages": pages,
                "page_count": len(pages),
            }
        )

    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
