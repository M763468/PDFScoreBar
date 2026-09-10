#!/usr/bin/env python3
"""Run the committed Issue #277 production MMRProcessor across retained full68 data.

This validation-only runner directly instantiates ``MMRProcessor`` from
``src.measure_numbering.mmr``. It reuses Phase-A numbering and #274 MMR support
artifacts, running only MMR CNN and RapidOCR. Detector, HOMR, SR, OMR, grouping,
and numbering are never re-executed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.mmr import MMRClassifier, MMROCREngine, MMRProcessor
from src.measure_numbering.rapidocr_provider import (
    collect_rapidocr_providers,
    create_mmr_rapidocr,
    providers_include_cuda,
)
from tools.issue264.run_phase_c_mmr_regression import build_page_specs

DEFAULT_REUSE_ROOT = PROJECT_ROOT / "logs/issue274_full68_mmr_reuse"
DEFAULT_NUMBERING_ROOT = (
    PROJECT_ROOT
    / "logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02"
)
DEFAULT_MODEL = PROJECT_ROOT / "tools/mmr_training/models/mmr_classifier_best.pth"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "logs/issue277/issue277_production_full68_01/production_mmr_full68_01.json"
)
EXPECTED_PAGES = 68
_SHA1_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_host_git_head(value: str | None) -> str:
    if value is None or not _SHA1_RE.fullmatch(value.strip()):
        raise RuntimeError("ISSUE277_GIT_HEAD must be the 40-hex HEAD from this worktree")
    return value.strip().lower()


class CountingOCR:
    """Count real RapidOCR calls without changing OCR behavior."""

    def __init__(self, wrapped: Any):
        self.wrapped = wrapped
        self.calls = 0

    def __call__(self, image: Any):
        self.calls += 1
        return self.wrapped(image)


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
        for path in (
            spec.image,
            numbering_root / "intermediate" / spec.page_id / "numbering_base.json",
            reuse_root / "intermediate" / spec.page_id / "mmr_support.json",
        ):
            if not path.is_file():
                missing.append(str(path))
    if not model_path.is_file():
        missing.append(str(model_path))
    if missing:
        raise FileNotFoundError("Missing production full68 inputs:\n" + "\n".join(missing))
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
    git_head: str,
    preflight_only: bool = False,
) -> dict[str, Any]:
    specs, preflight = _preflight(reuse_root, numbering_root, model_path)
    if preflight_only:
        payload = {
            "schema_version": "issue277.production_mmr_full68.preflight.v1",
            "status": "preflight_passed",
            "git_head": git_head,
            "preflight": preflight,
        }
        _write_json(output_path, payload)
        return payload

    import cv2
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the canonical production full68 MMR run")
    device = torch.device("cuda")
    provider = create_mmr_rapidocr(provider_mode)
    providers = collect_rapidocr_providers(provider)
    if provider_mode == "cuda" and not providers_include_cuda(providers):
        raise RuntimeError(f"RapidOCR CUDA requested but not confirmed: {providers}")

    ocr_counter = CountingOCR(provider)
    classifier = CountingClassifier(MMRClassifier(model_path, device))
    processor = MMRProcessor(
        model_path,
        device,
        classifier=classifier,
        ocr_engine=MMROCREngine(ocr_engine=ocr_counter),
    )

    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    started_all = time.perf_counter()
    page_rows: list[dict[str, Any]] = []
    all_overrides: list[dict[str, Any]] = []
    total_support_stats: Counter[str] = Counter()

    for index, spec in enumerate(specs, start=1):
        image = cv2.imread(str(spec.image))
        if image is None:
            raise FileNotFoundError(spec.image)
        page_data = _load_json(
            numbering_root / "intermediate" / spec.page_id / "numbering_base.json"
        )
        support = _load_json(reuse_root / "intermediate" / spec.page_id / "mmr_support.json")
        processor.support_stats = {
            "phase_a_ocr_fallback": 0,
            "alternate_veto_suppression": 0,
        }
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
                "output": str(page_output),
            }
        )
        print(
            f"production full68: {index}/{len(specs)} {spec.page_id} "
            f"overrides={len(overrides)} ocr_calls={ocr_counter.calls - before_ocr} "
            f"elapsed={elapsed_page:.3f}s",
            flush=True,
        )

    torch.cuda.synchronize()
    elapsed_all = time.perf_counter() - started_all
    payload = {
        "schema_version": "issue277.production_mmr_full68.v1",
        "status": "completed",
        "git_head": git_head,
        "execution_contract": {
            "processor_class": "src.measure_numbering.mmr.MMRProcessor",
            "targeted_retry_processor_used": False,
            "detector_reexecuted": False,
            "homr_reexecuted": False,
            "sr_reexecuted": False,
            "omr_reexecuted": False,
            "grouping_reexecuted": False,
            "numbering_reexecuted": False,
            "mmr_cnn_reexecuted": True,
            "rapidocr_reexecuted": True,
            "frozen_A_geometry_used": False,
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
        git_head=resolve_host_git_head(os.environ.get("ISSUE277_GIT_HEAD")),
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
