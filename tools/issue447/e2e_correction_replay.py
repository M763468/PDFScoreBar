"""Supplemental actual Phase A/C replay with a fixed source-coordinate edit."""

import argparse
import json
import shutil
from pathlib import Path

from src.pipeline.core import load_yaml
from src.pipeline.orchestrator import PipelineOrchestrator
from src.pipeline.steps.barlines import normalize_barlines
from src.pipeline.steps.numbering import load_movement_boundary_payload
from src.pipeline.utils.images import clear_image_cache
from tools.issue447.analyze import local_path


def run(label, output, overrides, *, source_runs=None):
    root = Path.cwd()
    source = (source_runs or root / "logs/issue447/runs") / label
    pipeline = source / "pipeline"
    config = load_yaml(source / "config.yaml")
    config["steps"]["apply_barline_overrides"] = True
    clear_image_cache()
    output.mkdir(parents=True, exist_ok=False)
    orchestrator = PipelineOrchestrator(config, label + "-correction-replay", output)
    orchestrator._barline_override_payload = overrides
    manifest = json.loads((pipeline / "manifest.json").read_text())
    resolved = []
    for page in manifest["pages"]:
        item = dict(page)
        for key in ("barlines_json", "staff_mask", "image_path"):
            item[key] = str(local_path(root, page[key]))
        resolved.append(item)
    ids = [r["page_id"] for r in resolved]
    phase = orchestrator.run_base_numbering_and_barline_correction(
        ids, [Path(r["image_path"]) for r in resolved], resolved, set()
    )
    ctx = phase["page_ctx"]
    for page in ids:
        shutil.copyfile(
            pipeline / "intermediate" / page / "overrides_mmr.json",
            ctx[page]["intermediate_dir"] / "overrides_mmr.json",
        )
    manual = {
        "measure_overrides": [
            {
                "page": 0,
                "system": 0,
                "measure": 0,
                "set_number": 0,
                "comment": "fixed correction replay",
            }
        ]
    }
    boundaries = load_movement_boundary_payload(
        {
            "boundaries": [
                {
                    "page": 1,
                    "system": 0,
                    "reset_number": 1,
                    "source": "issue447-correction-replay",
                    "provenance": {"purpose": "fixed manual/barline/movement validation"},
                }
            ]
        }
    )
    paths = orchestrator.run_final_numbering_and_overlays(ids, set(), ctx, manual, boundaries)
    pages = [json.loads(p.read_text()) for p in paths]
    boxes = {p: ctx[p]["corrected_barlines"] for p in ids}
    original = normalize_barlines(json.loads(Path(resolved[0]["barlines_json"]).read_text()))
    stats = phase["barline_override_stats"]
    checks = {
        "remove_matched": stats[ids[0]]["removed"] >= 1 and stats[ids[0]]["unmatched_remove"] == 0,
        "one_add": stats[ids[0]]["added"] == 1,
        "geometry_changed": boxes[ids[0]] != original,
        "manual_zero": pages[0]["pages"][0]["systems"][0]["measures"][0]["number"] == 0,
        "movement_one": pages[1]["pages"][0]["systems"][0]["measures"][0]["number"] == 1,
        "continuity": pages[2]["numbering_metadata"]["start_number"]
        == pages[1]["numbering_metadata"]["next_number"],
        "order": ids == ["page_012", "page_013", "page_014"],
    }
    result = {
        "label": label,
        "checks": checks,
        "corrected_boxes": boxes,
        "stats": stats,
        "final_pages": pages,
        "base_pages": [json.loads(p.read_text()) for p in phase["numbering_base_paths"]],
    }
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(Path("logs/issue447/e2e-candidates/results.json").read_text())
    labels = [r["label"] for r in rows]
    first = Path("logs/issue447/runs") / labels[0] / "pipeline"
    manifest = json.loads((first / "manifest.json").read_text())
    box = normalize_barlines(
        json.loads(local_path(Path.cwd(), manifest["pages"][0]["barlines_json"]).read_text())
    )[0]
    shifted = [box[0] + 2, box[1], box[2] + 2, box[3]]
    overrides = {
        "barline_overrides": [
            {"page": 0, "op": "remove", "bbox": box},
            {"page": 0, "op": "add", "bbox": shifted},
        ]
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "fixed-overrides.json").write_text(json.dumps(overrides, indent=2) + "\n")
    baseline = None
    summary = []
    for label in labels:
        result = run(label, args.output / label, overrides)
        compared = {k: result[k] for k in ("corrected_boxes", "stats", "final_pages", "base_pages")}
        if baseline is None:
            baseline = compared
        checks = {
            **result["checks"],
            "all_corrected_pages_stats_and_metadata_equal": compared == baseline,
        }
        summary.append({"label": label, "checks": checks})
    (args.output / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    assert all(all(r["checks"].values()) for r in summary)


if __name__ == "__main__":
    main()
