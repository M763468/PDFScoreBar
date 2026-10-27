"""Replay the real Phase C with retained MMR, an explicit boundary and manual correction.

This is CPU-only semantic validation, not another model/E2E performance measurement.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.pipeline.core import load_yaml
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.steps.numbering import load_movement_boundary_payload
from src.pipeline.utils.images import clear_image_cache
from tools.issue447.analyze import local_path


def replay(root: Path, label: str, output: Path):
    source = root / "logs/issue447/runs" / label
    pipeline = source / "pipeline"
    config = load_yaml(source / "config.yaml")
    manifest = json.loads((pipeline / "manifest.json").read_text())
    boundaries = load_movement_boundary_payload(
        {
            "boundaries": [
                {
                    "page": 1,
                    "system": 0,
                    "reset_number": 1,
                    "source": "issue447-fixed-validation-replay",
                    "provenance": {
                        "contract": "deepening/contract-v3.json",
                        "purpose": "explicit movement/index guard",
                    },
                }
            ]
        }
    )
    manual = {
        "measure_overrides": [
            {
                "page": 0,
                "system": 0,
                "measure": 0,
                "set_number": 0,
                "comment": "fixed replay anacrusis",
            }
        ]
    }
    output.mkdir(parents=True, exist_ok=False)
    clear_image_cache()
    orchestrator = PipelineOrchestrator(config, label + "-replay", output)
    context = {}
    for index, page in enumerate(manifest["pages"], 1):
        page_id = page["page_id"]
        intermediate = output / "intermediate" / page_id
        outputs = output / "outputs" / page_id
        intermediate.mkdir(parents=True)
        outputs.mkdir(parents=True)
        shutil.copy2(
            pipeline / "intermediate" / page_id / "overrides_mmr.json",
            intermediate / "overrides_mmr.json",
        )
        resolved = dict(page)
        resolved["barlines_json"] = str(local_path(root, page["barlines_json"]))
        resolved["staff_mask"] = str(local_path(root, page["staff_mask"]))
        context[page_id] = {
            "index": index,
            "image_path": local_path(root, page["image_path"]),
            "intermediate_dir": intermediate,
            "outputs_dir": outputs,
            "resolved": resolved,
            "barlines_path": Path(resolved["barlines_json"]),
        }
    page_ids = [p["page_id"] for p in manifest["pages"]]
    paths = orchestrator.run_final_numbering_and_overlays(
        page_ids, set(), context, manual, boundaries
    )
    payloads = [json.loads(path.read_text()) for path in paths]
    first = payloads[0]["pages"][0]["systems"][0]["measures"][0]["number"]
    reset = payloads[1]["pages"][0]["systems"][0]["measures"][0]["number"]
    continuity = (
        payloads[2]["numbering_metadata"]["start_number"]
        == payloads[1]["numbering_metadata"]["next_number"]
    )
    checks = {
        "manual_anacrusis_zero": first == 0,
        "second_page_movement_reset_one": reset == 1,
        "third_page_continuity": continuity,
        "page_order": page_ids == ["page_012", "page_013", "page_014"],
    }
    result = {
        "source_run": label,
        "movement_boundaries": boundaries,
        "manual_correction": manual,
        "pages": payloads,
        "checks": checks,
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    args.output.mkdir(parents=True, exist_ok=False)
    a = replay(root, "deep-e2e-w1", args.output / "serial")
    b = replay(root, "deep-e2e-w2", args.output / "parallel")
    result = {
        "kind": "real Phase C semantic replay; no detector/MMR inference",
        "serial_checks": a["checks"],
        "parallel_checks": b["checks"],
        "replayed_pages_and_metadata_equal": a["pages"] == b["pages"],
    }
    (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if (
        not all(a["checks"].values())
        or not all(b["checks"].values())
        or not result["replayed_pages_and_metadata_equal"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
