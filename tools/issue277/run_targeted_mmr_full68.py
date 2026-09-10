#!/usr/bin/env python3
"""Run the Issue #277 targeted MMR retry across the retained full-68 corpus.

This is experiment-only validation tooling. It reuses the accepted Phase-A
numbering artifacts and the retained #274 MMR support sidecars, then executes
only the MMR CNN/RapidOCR path with ``TargetedRetryProcessor``. Detector, HOMR,
SR, OMR-DLN, grouping, and numbering are not rerun.

The run intentionally writes fresh per-page override artifacts so the final
accepted-geometry scorer can account for all positives, historical FNs, and
zero-fixture pages rather than extrapolating from the retained-positive slice.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from tools.issue264.run_phase_c_mmr_regression import build_page_specs
from tools.issue277.run_composed_mmr_positive_risk_slice import CountingOCR
from tools.issue277.run_targeted_mmr_positive_risk_slice import TargetedRetryProcessor

DEFAULT_REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
DEFAULT_NUMBERING_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "logs/issue277/issue277_targeted_full68_01/targeted_mmr_full68_01.json"
)
EXPECTED_PAGES = 68


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


class CountingClassifier:
    """Count real MMR classifier calls without changing classifier behavior."""

    def __init__(self, wrapped: Any):
        self.wrapped = wrapped
        self.calls = 0

    def predict(self, image: Any) -> float:
        self.calls += 1
        return float(self.wrapped.predict(image))


def _preflight(reuse_root: Path, numbering_root: Path, model_path: Path) -> tuple[list[Any], dict[str, Any]]:
    specs = build_page_specs()
    if len(specs) != EXPECTED_PAGES:
        raise RuntimeError(f"Expected {EXPECTED_PAGES} page specs, got {len(specs)}")

    missing: list[str] = []
    for spec in specs:
        required = (
            spec.image,
            numbering_root / "intermediate" / spec.page_id / "numbering_base.json",
            reuse_root / "intermediate" / spec.page_id / "mmr_support.json",
        )
        for path in required:
            if not path.is_file():
                missing.append(str(path))
    if not model_path.is_file():
        missing.append(str(model_path))
    if missing:
        raise FileNotFoundError("Missing targeted full68 inputs:\n" + "\n".join(missing))

    return specs, {
        "pages": len(specs),
        "reuse_root": str(reuse_root),
        "numbering_root": str(numbering_root),
        "model": str(model_path),
    }


def run(
    *,
    reuse_root: Path,
    numbering_root: Path,
    model_path: Path,
    output_path: Path,
    provider_mode: str,
    preflight_only: bool = False,
) -> dict[str, Any]:
    specs, preflight = _preflight(reuse_root, numbering_root, model_path)
    if preflight_only:
        payload = {
            "schema_version": "issue277.targeted_mmr_full68.preflight.v1",
            "status": "preflight_passed",
            "git_head": _git_head(),
            "preflight": preflight,
        }
        _write_json(output_path, payload)
        return payload

    import cv2
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the canonical targeted full68 MMR run")
    device = torch.device("cuda")

    provider = create_mmr_rapidocr(provider_mode)
    providers = collect_rapidocr_providers(provider)
    if provider_mode == "cuda" and not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDA requested but not confirmed: {providers}")

    ocr_counter = CountingOCR(provider)
    classifier = CountingClassifier(MMRClassifier(model_path, device))
    processor = TargetedRetryProcessor(
        ocr_engine=MMROCREngine(ocr_engine=ocr_counter),
        classifier=classifier,
    )

    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    started_all = time.perf_counter()

    page_rows: list[dict[str, Any]] = []
    all_overrides: list[dict[str, Any]] = []
    total_stage_counts: Counter[str] = Counter()
    total_support_stats: Counter[str] = Counter()

    for index, spec in enumerate(specs, start=1):
        image = cv2.imread(str(spec.image))
        if image is None:
            raise FileNotFoundError(spec.image)
        page_data = _load_json(
            numbering_root / "intermediate" / spec.page_id / "numbering_base.json"
        )
        support = _load_json(
            reuse_root / "intermediate" / spec.page_id / "mmr_support.json"
        )

        processor.support_stats = {
            "phase_a_ocr_fallback": 0,
            "alternate_veto_suppression": 0,
        }
        processor.reset_decision_trace()
        before_ocr = ocr_counter.calls
        before_classifier = classifier.calls
        height, width = image.shape[:2]

        torch.cuda.synchronize()
        started_page = time.perf_counter()
        overrides = processor._process_page_with_support(
            page_data=page_data,
            support=support,
            image=image,
            page_num=spec.global_index + 1,
            image_width=width,
            image_height=height,
            debug_img=None,
        )
        torch.cuda.synchronize()
        elapsed_page = time.perf_counter() - started_page

        stage_counts = Counter(
            str(item.get("stage"))
            for item in processor.decision_trace
            if item.get("stage") is not None
        )
        total_stage_counts.update(stage_counts)
        total_support_stats.update(processor.support_stats)

        page_output = output_path.parent / "pages" / spec.page_id / "overrides_mmr.json"
        _write_json(page_output, {"measure_overrides": overrides})
        all_overrides.extend(overrides)
        page_rows.append(
            {
                "page_id": spec.page_id,
                "global_index": spec.global_index,
                "score": spec.score,
                "score_page": spec.page_name,
                "overrides": overrides,
                "override_count": len(overrides),
                "rapidocr_calls": ocr_counter.calls - before_ocr,
                "classifier_calls": classifier.calls - before_classifier,
                "elapsed_sec": elapsed_page,
                "support_stats": dict(processor.support_stats),
                "stage_counts": dict(sorted(stage_counts.items())),
                "output": str(page_output),
            }
        )
        print(
            f"targeted full68: {index}/{len(specs)} {spec.page_id} "
            f"overrides={len(overrides)} ocr_calls={ocr_counter.calls - before_ocr} "
            f"elapsed={elapsed_page:.3f}s",
            flush=True,
        )

    torch.cuda.synchronize()
    elapsed_all = time.perf_counter() - started_all
    payload = {
        "schema_version": "issue277.targeted_mmr_full68.v1",
        "status": "completed",
        "git_head": _git_head(),
        "execution_contract": {
            "production_code_modified": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "grouping_reexecuted": False,
            "numbering_reexecuted": False,
            "mmr_cnn_reexecuted": True,
            "rapidocr_reexecuted": True,
            "frozen_A_geometry_used": False,
            "candidate": (
                "production one-shot high-score passthrough; candidate-native full-span "
                "unmasked heavy_dilate then +1% x1 masked no_dilate only for low-score/None; "
                "positive retry spatial score required; merged-J2 fallback for unresolved "
                "low-score, low-CNN, and one-bar-sensitive cases"
            ),
        },
        "inputs": preflight,
        "runtime": {
            "provider_mode": provider_mode,
            "rapidocr_providers": providers,
            "rapidocr_cuda_confirmed": providers_include_cuda(providers),
            "device": str(device),
            "elapsed_sec": elapsed_all,
            "rapidocr_calls": ocr_counter.calls,
            "classifier_calls": classifier.calls,
            "torch_peak_memory_allocated_mb": torch.cuda.max_memory_allocated() / (1024 * 1024),
            "torch_peak_memory_reserved_mb": torch.cuda.max_memory_reserved() / (1024 * 1024),
            "note": "Torch peak memory does not include all ONNX Runtime allocations.",
        },
        "summary": {
            "pages": len(page_rows),
            "detected_overrides": len(all_overrides),
            "stage_counts": dict(sorted(total_stage_counts.items())),
            "support_stats": dict(sorted(total_support_stats.items())),
        },
        "pages": page_rows,
        "all_overrides": all_overrides,
    }
    _write_json(output_path, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-root", type=Path, default=DEFAULT_REUSE_ROOT)
    parser.add_argument("--numbering-root", type=Path, default=DEFAULT_NUMBERING_ROOT)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--provider", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    payload = run(
        reuse_root=args.reuse_root,
        numbering_root=args.numbering_root,
        model_path=args.model,
        output_path=args.output,
        provider_mode=args.provider,
        preflight_only=args.preflight,
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "summary": payload.get("summary"),
                "runtime": payload.get("runtime"),
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
