#!/usr/bin/env python3
"""Run Stage E with an Issue #179 RapidOCR CUDA provider experiment patch.

This wrapper intentionally avoids changing the normal Stage E runner. It applies
temporary in-process monkey patches before delegating to
tools/issue120/run_stage_e_full_pipeline.py.

Modes:
- default: no PDFSCORE_RAPIDOCR_USE_CUDA, RapidOCR() remains default.
- CUDA opt-in: PDFSCORE_RAPIDOCR_USE_CUDA=1 passes
  det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True to Stage E RapidOCR
  constructors used by MMR and HOMR title detection.

The wrapper writes rapidocr_provider_summary.json under the Stage E run root so
default and CUDA runs can be compared without committing logs.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import runpy
import sys
import time
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOGGER = logging.getLogger("issue179.rapidocr_cuda_experiment")

RAPIDOCR_USE_CUDA_ENV = "PDFSCORE_RAPIDOCR_USE_CUDA"
RAPIDOCR_CUDA_KWARGS: dict[str, bool] = {
    "det_use_cuda": True,
    "cls_use_cuda": True,
    "rec_use_cuda": True,
}


def _env_flag_enabled(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(val) for key, val in value.items()}
    return repr(value)


def _collect_providers(obj: Any, *, max_depth: int = 5) -> dict[str, list[str]]:
    """Best-effort ONNX Runtime provider discovery from a RapidOCR object graph."""
    providers: dict[str, list[str]] = {}
    seen: set[int] = set()

    def visit(value: Any, path: str, depth: int) -> None:
        if id(value) in seen:
            return
        seen.add(id(value))

        get_providers = getattr(value, "get_providers", None)
        if callable(get_providers):
            try:
                provider_list = get_providers()
            except Exception as exc:  # pragma: no cover - defensive provider introspection
                providers[path] = [f"<provider inspection failed: {exc!r}>"]
            else:
                providers[path] = [str(item) for item in provider_list]

        if depth >= max_depth:
            return

        if isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{path}.{key}", depth + 1)
            return

        if isinstance(value, (list, tuple)):
            for idx, item in enumerate(value):
                visit(item, f"{path}[{idx}]", depth + 1)
            return

        attrs = getattr(value, "__dict__", None)
        if isinstance(attrs, dict):
            for key, item in attrs.items():
                if key.startswith("__"):
                    continue
                visit(item, f"{path}.{key}", depth + 1)

    visit(obj, "root", 0)
    return providers


class RapidOCRPatchRecorder:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.instances: list[dict[str, Any]] = []
        self.patches: dict[str, dict[str, Any]] = {}

    def make_factory(self, original: Callable[..., Any], *, component: str) -> Callable[..., Any]:
        def _factory(*args: Any, **kwargs: Any) -> Any:
            use_cuda = _env_flag_enabled(RAPIDOCR_USE_CUDA_ENV)
            ctor_kwargs = dict(kwargs)
            if use_cuda:
                for key, value in RAPIDOCR_CUDA_KWARGS.items():
                    ctor_kwargs.setdefault(key, value)

            started = time.perf_counter()
            try:
                engine = original(*args, **ctor_kwargs)
            except TypeError as exc:
                if use_cuda:
                    raise RuntimeError(
                        f"{component}: RapidOCR constructor rejected CUDA opt-in kwargs "
                        f"{sorted(RAPIDOCR_CUDA_KWARGS)}. This run must not be treated as a "
                        "valid CUDA comparison."
                    ) from exc
                raise
            duration_sec = time.perf_counter() - started

            self.instances.append(
                {
                    "component": component,
                    "rapidocr_class": f"{getattr(original, '__module__', '<unknown>')}."
                    f"{getattr(original, '__name__', type(original).__name__)}",
                    "cuda_requested": use_cuda,
                    "constructor_args_count": len(args),
                    "constructor_kwargs": _jsonable(ctor_kwargs),
                    "duration_sec": duration_sec,
                    "providers_by_path": _collect_providers(engine),
                }
            )
            return engine

        return _factory

    def install_mmr_patch(self) -> None:
        import src.measure_numbering.mmr as mmr

        if getattr(mmr, "_PDFSCORE_ISSUE179_RAPIDOCR_PATCHED", False):
            self.patches["mmr"] = {"installed": False, "reason": "already_patched"}
            return

        original = mmr.RapidOCR
        mmr._PDFSCORE_ISSUE179_ORIGINAL_RAPIDOCR = original
        mmr.RapidOCR = self.make_factory(original, component="src.measure_numbering.mmr")
        mmr._PDFSCORE_ISSUE179_RAPIDOCR_PATCHED = True
        self.patches["mmr"] = {
            "installed": True,
            "original": f"{getattr(original, '__module__', '<unknown>')}."
            f"{getattr(original, '__name__', type(original).__name__)}",
        }

    def install_homr_title_patch(self) -> None:
        import homr.title_detection as title_detection

        if getattr(title_detection, "_PDFSCORE_ISSUE179_RAPIDOCR_PATCHED", False):
            self.patches["homr_title_detection"] = {
                "installed": False,
                "reason": "already_patched",
            }
            return

        original = title_detection.RapidOCR
        already_initialized = getattr(title_detection, "_reader", None) is not None
        title_detection._PDFSCORE_ISSUE179_ORIGINAL_RAPIDOCR = original
        title_detection.RapidOCR = self.make_factory(
            original,
            component="homr.title_detection",
        )
        title_detection._PDFSCORE_ISSUE179_RAPIDOCR_PATCHED = True
        self.patches["homr_title_detection"] = {
            "installed": True,
            "already_initialized_before_patch": already_initialized,
            "original": f"{getattr(original, '__module__', '<unknown>')}."
            f"{getattr(original, '__name__', type(original).__name__)}",
        }

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": "tools.issue179.rapidocr_provider_summary.v1",
            "started_at_epoch": self.started_at,
            "finished_at_epoch": time.time(),
            "env": {
                RAPIDOCR_USE_CUDA_ENV: os.environ.get(RAPIDOCR_USE_CUDA_ENV),
                "cuda_enabled": _env_flag_enabled(RAPIDOCR_USE_CUDA_ENV),
            },
            "patches": self.patches,
            "instances": self.instances,
        }


def _extract_output_root(stage_e_args: list[str]) -> Path:
    for idx, arg in enumerate(stage_e_args):
        if arg == "--output-root" and idx + 1 < len(stage_e_args):
            return Path(stage_e_args[idx + 1])
        if arg.startswith("--output-root="):
            return Path(arg.split("=", 1)[1])
    return Path("logs/issue120_e2e_recovery")


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=(
            "Issue #179 wrapper for default-vs-CUDA RapidOCR Stage E experiments. "
            "Unknown args are forwarded to tools/issue120/run_stage_e_full_pipeline.py."
        )
    )
    parser.add_argument(
        "--rapidocr-provider-summary",
        type=Path,
        default=None,
        help=(
            "Output path for RapidOCR constructor/provider summary. Defaults to "
            "<output-root>/stage_e_full_pipeline/rapidocr_provider_summary.json."
        ),
    )
    parser.add_argument(
        "--skip-mmr-rapidocr-patch",
        action="store_true",
        help="Do not patch src.measure_numbering.mmr RapidOCR construction.",
    )
    parser.add_argument(
        "--skip-homr-title-rapidocr-patch",
        action="store_true",
        help="Do not patch homr.title_detection RapidOCR construction.",
    )
    return parser.parse_known_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    wrapper_args, stage_e_args = parse_args()
    recorder = RapidOCRPatchRecorder()

    if not wrapper_args.skip_mmr_rapidocr_patch:
        recorder.install_mmr_patch()
    if not wrapper_args.skip_homr_title_rapidocr_patch:
        recorder.install_homr_title_patch()

    output_root = _extract_output_root(stage_e_args)
    summary_path = wrapper_args.rapidocr_provider_summary or (
        output_root / "stage_e_full_pipeline" / "rapidocr_provider_summary.json"
    )

    LOGGER.info(
        "Issue #179 RapidOCR wrapper enabled. %s=%r patches=%s summary=%s",
        RAPIDOCR_USE_CUDA_ENV,
        os.environ.get(RAPIDOCR_USE_CUDA_ENV),
        sorted(recorder.patches),
        summary_path,
    )

    stage_e_script = PROJECT_ROOT / "tools" / "issue120" / "run_stage_e_full_pipeline.py"
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(stage_e_script), *stage_e_args]
        runpy.run_path(str(stage_e_script), run_name="__main__")
    finally:
        sys.argv = original_argv
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(recorder.summary(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        LOGGER.info("RapidOCR provider summary written to %s", summary_path)


if __name__ == "__main__":
    main()
