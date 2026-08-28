"""Run eager/compiled Issue #284 variants through a 3-page dense production slice.

The gate executes the real dense pipeline twice on Shostakovich-Sym5-Va pages
012-014.  It separates raw coordinate identity from the semantic contracts used
by Issue #284/#286: hybrid barline identity, numbering topology/numbers, MMR
override semantics, and current-support connector completeness.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.issue284.compare_full68_variants import (
    bbox_differences,
    boxes_from_payload,
    load_json,
    normalize_overrides,
    numbering_view,
    support_semantics,
)

PIPELINE_PYTHON = Path("/opt/venv_pipeline/bin/python")
SCORE = "Shostakovich-Sym5-Va"
PAGES = ("page_012", "page_013", "page_014")
CANONICAL_CONFIG = ROOT / "configs/dense_full_pipeline.yaml"


def _require_runtime() -> None:
    if not Path("/.dockerenv").exists() or ROOT.resolve() != Path("/workspace").resolve():
        raise RuntimeError("Issue #284 integrated slice gate requires canonical /workspace Docker")
    if not PIPELINE_PYTHON.is_file():
        raise FileNotFoundError(PIPELINE_PYTHON)


def _stage_inputs(root: Path) -> Path:
    staged = root / "input_staging" / SCORE
    staged.mkdir(parents=True, exist_ok=False)
    for page in PAGES:
        source = ROOT / "data/evaluation2/images" / SCORE / f"{page}.png"
        if not source.is_file():
            raise FileNotFoundError(source)
        (staged / source.name).symlink_to(source)
    return staged


def _derived_config(root: Path, staged: Path, compile_mode: str | None) -> Path:
    config = yaml.safe_load(CANONICAL_CONFIG.read_text(encoding="utf-8"))
    detection = config.get("detection")
    if not isinstance(detection, dict):
        raise ValueError("Canonical config lacks detection mapping")
    if detection.get("detector_route") != "dense_full_pipeline":
        raise ValueError("Canonical config is not dense_full_pipeline")
    if detection.get("homr_profile") != "stage_e_verified":
        raise ValueError("Canonical config is not stage_e_verified")
    if int(detection.get("sr_scale", 0)) != 4:
        raise ValueError("Canonical config is not x4 SR")

    config["inputs"]["pdf_to_images"]["output_dir"] = str(staged)
    detection["hybrid_output_root"] = str(root / "hybrid_output")
    detection["sr_compile_mode"] = compile_mode
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _page_artifacts(*, variant_root: Path, run_id: str, page: str) -> dict[str, str]:
    pipeline_run = variant_root / "pipeline_output" / run_id
    hybrid_run = variant_root / "hybrid_output" / run_id
    paths = {
        "hybrid": hybrid_run / "hybrid_results" / f"{page}_hybrid.json",
        "numbering_base": pipeline_run / "intermediate" / page / "numbering_base.json",
        "overrides_mmr": pipeline_run / "intermediate" / page / "overrides_mmr.json",
        "numbering_final": pipeline_run / "outputs" / page / "numbering_final.json",
        "current_support": hybrid_run / "current_support" / SCORE / page / "result.json",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("Integrated slice artifacts missing: " + ", ".join(missing))
    return {key: str(value) for key, value in paths.items()}


def _run_variant(output: Path, *, label: str, compile_mode: str | None) -> dict[str, Any]:
    root = output / label
    root.mkdir(parents=True, exist_ok=False)
    staged = _stage_inputs(root)
    config = _derived_config(root, staged, compile_mode)
    run_id = f"issue284_compile_slice_{label}"
    log = root / "pipeline.log"
    command = [
        str(PIPELINE_PYTHON),
        "-m",
        "src.pipeline.main",
        "--config",
        str(config),
        "--run-id",
        run_id,
        "--output-root",
        str(root / "pipeline_output"),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env.pop("PDFSCORE_PERF_TRACE_DIR", None)

    started = time.perf_counter()
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
    wall = time.perf_counter() - started
    if process.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-100:]
        raise RuntimeError(
            f"{label} integrated slice failed ({process.returncode})\n" + "\n".join(tail)
        )

    hybrid_run = root / "hybrid_output" / run_id
    sr_batch_path = hybrid_run / "current_support" / "_sr_batch" / "result.json"
    if not sr_batch_path.is_file():
        raise FileNotFoundError(sr_batch_path)
    sr_batch = load_json(sr_batch_path)
    return {
        "label": label,
        "compile_mode": compile_mode,
        "e2e_wall_sec": wall,
        "config": str(config),
        "log": str(log),
        "run_id": run_id,
        "sr_batch": {
            key: sr_batch.get(key)
            for key in (
                "page_count",
                "batch_wall_sec",
                "peak_cuda_allocated_bytes",
                "peak_cuda_reserved_bytes",
                "runtime",
            )
        },
        "pages": {
            page: _page_artifacts(variant_root=root, run_id=run_id, page=page) for page in PAGES
        },
    }


def _compare_page(eager: dict[str, str], compiled: dict[str, str], page: str) -> dict[str, Any]:
    eager_boxes = boxes_from_payload(load_json(Path(eager["hybrid"])))
    compiled_boxes = boxes_from_payload(load_json(Path(compiled["hybrid"])))
    eager_base = numbering_view(Path(eager["numbering_base"]))
    compiled_base = numbering_view(Path(compiled["numbering_base"]))
    eager_final = numbering_view(Path(eager["numbering_final"]))
    compiled_final = numbering_view(Path(compiled["numbering_final"]))
    eager_mmr = normalize_overrides(Path(eager["overrides_mmr"]))
    compiled_mmr = normalize_overrides(Path(compiled["overrides_mmr"]))
    eager_support = support_semantics(Path(eager["current_support"]))
    compiled_support = support_semantics(Path(compiled["current_support"]))

    base_bbox_diff = bbox_differences(eager_base, compiled_base)
    final_bbox_diff = bbox_differences(eager_final, compiled_final)
    coordinate_review_required = any(
        item.get("classification") == "coordinate_review_required"
        for item in [*base_bbox_diff, *final_bbox_diff]
    )
    semantic_pass = bool(
        sorted(eager_boxes) == sorted(compiled_boxes)
        and eager_base["topology"] == compiled_base["topology"]
        and eager_base["numbers"] == compiled_base["numbers"]
        and eager_final["topology"] == compiled_final["topology"]
        and eager_final["numbers"] == compiled_final["numbers"]
        and eager_mmr == compiled_mmr
        and eager_support["connector_complete"] is True
        and compiled_support["connector_complete"] is True
        and eager_support["historical_detector_artifact_runtime_input"] is False
        and compiled_support["historical_detector_artifact_runtime_input"] is False
        and not coordinate_review_required
    )
    return {
        "page": page,
        "semantic_pass": semantic_pass,
        "hybrid": {
            "eager_count": len(eager_boxes),
            "compiled_count": len(compiled_boxes),
            "multiset_exact": sorted(eager_boxes) == sorted(compiled_boxes),
        },
        "numbering_base": {
            "topology_equal": eager_base["topology"] == compiled_base["topology"],
            "numbers_equal": eager_base["numbers"] == compiled_base["numbers"],
            "raw_equal": eager_base["payload"] == compiled_base["payload"],
            "bbox_differences": base_bbox_diff,
        },
        "numbering_final": {
            "topology_equal": eager_final["topology"] == compiled_final["topology"],
            "numbers_equal": eager_final["numbers"] == compiled_final["numbers"],
            "raw_equal": eager_final["payload"] == compiled_final["payload"],
            "bbox_differences": final_bbox_diff,
        },
        "mmr": {
            "semantic_equal": eager_mmr == compiled_mmr,
            "eager": eager_mmr,
            "compiled": compiled_mmr,
        },
        "support": {
            "eager": eager_support,
            "compiled": compiled_support,
            "sr_byte_identical": eager_support["sr_sha256"] == compiled_support["sr_sha256"],
            "connector_symbols_byte_identical": (
                eager_support["connector_symbols_sha256"]
                == compiled_support["connector_symbols_sha256"]
            ),
            "connector_brace_dot_byte_identical": (
                eager_support["connector_brace_dot_sha256"]
                == compiled_support["connector_brace_dot_sha256"]
            ),
        },
        "coordinate_review_required": coordinate_review_required,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _require_runtime()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result_path = output / "integrated_slice_result.json"
    payload: dict[str, Any] = {
        "schema_version": "issue284.compile_integrated_slice.v1",
        "status": "started",
        "score": SCORE,
        "pages": list(PAGES),
    }
    try:
        eager = _run_variant(output, label="eager", compile_mode=None)
        compiled = _run_variant(output, label="compiled", compile_mode="reduce-overhead")
        comparisons = [
            _compare_page(eager["pages"][page], compiled["pages"][page], page) for page in PAGES
        ]
        gate_passed = all(item["semantic_pass"] for item in comparisons)
        payload.update(
            {
                "status": "completed",
                "eager": eager,
                "compiled": compiled,
                "comparisons": comparisons,
                "semantic_pass_pages": sum(item["semantic_pass"] for item in comparisons),
                "integrated_dense_semantics_preserved": gate_passed,
            }
        )
    except Exception as error:  # noqa: BLE001
        payload.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            }
        )
        result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 1

    result_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["integrated_dense_semantics_preserved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
