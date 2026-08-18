#!/usr/bin/env python3
"""Find the first current B/C primary-HOMR divergence for Issue #274.

One retained x4 image is reduced once to the exact HomrPredictor proxy contract.
Three isolated current-runtime cells then consume that same proxy:
- monolithic evaluator, C-like config (debug on, prediction cache off)
- modular core, production-B config (debug off, prediction cache on)
- modular core, config-matched to C (debug on, prediction cache off)

Only primary HOMR is run. Thin-barline recovery, XML/TrOMR parsing, SR, OMR-DLN,
dense probe, CNN and MMR are excluded.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
AB_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
    "issue274_homr_x4_stage_e_ab.json"
)
OUT_DEFAULT = Path("logs/issue274_homr_unification_analysis/primary_stage_boundary_01")
TARGET_PIXELS = 3.5 * 1000 * 1000
CELLS = {
    "monolithic_current_c_like": ("monolithic", True, False),
    "core_current_b_like": ("core", False, True),
    "core_current_config_matched": ("core", True, False),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ws_path(value: str | Path, workspace: Path) -> Path:
    text = str(value)
    if text.startswith("/workspace/"):
        return workspace / text.removeprefix("/workspace/")
    marker = "/ws_PDFScoreBar/"
    if marker in text:
        return workspace / text.split(marker, 1)[1]
    path = Path(text)
    return path if path.is_absolute() else workspace / path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_info(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"path": None if path is None else str(path), "exists": False}
    return {"path": str(path), "exists": True, "size": path.stat().st_size, "sha256": sha(path)}


def arr_info(value: Any) -> dict[str, Any]:
    if value is None:
        return {"present": False}
    array = np.ascontiguousarray(np.asarray(value))
    return {
        "present": True,
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "nonzero": int(np.count_nonzero(array)),
        "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
    }


def bbox(item: Any) -> list[int | float] | None:
    nested = getattr(item, "notehead", None)
    if nested is not None and nested is not item:
        found = bbox(nested)
        if found is not None:
            return found
    candidate = item
    convert = getattr(candidate, "to_bounding_box", None)
    if callable(convert):
        try:
            candidate = convert()
        except Exception:  # noqa: BLE001
            candidate = item
    values = getattr(candidate, "box", getattr(candidate, "bbox", None))
    if values is None and isinstance(candidate, (list, tuple)):
        values = candidate
    if values is None:
        return None
    seq = list(values)
    if len(seq) < 4:
        return None
    result: list[int | float] = []
    for value in seq[:4]:
        number = float(value)
        rounded = round(number)
        result.append(int(rounded) if abs(number - rounded) < 1e-9 else round(number, 6))
    return result


def boxes_info(items: Any) -> dict[str, Any]:
    rows = [box for item in (items or []) if (box := bbox(item)) is not None]
    ordered = json.dumps(rows, separators=(",", ":")).encode()
    sorted_rows = sorted(rows, key=lambda row: tuple(float(v) for v in row))
    multiset = json.dumps(sorted_rows, separators=(",", ":")).encode()
    return {
        "count": len(rows),
        "ordered_sha256": hashlib.sha256(ordered).hexdigest(),
        "multiset_sha256": hashlib.sha256(multiset).hexdigest(),
        "sample": rows[:8],
    }


def symbols_info(symbols: Any) -> dict[str, Any]:
    return {
        name: boxes_info(getattr(symbols, name, []))
        for name in ("noteheads", "staff_fragments", "clefs_keys", "stems_rest", "bar_lines")
    }


def callable_info(obj: Any) -> dict[str, Any]:
    original = getattr(obj, "_pdfscore_homr_consumer_original", None)
    source = inspect.getsourcefile(original or obj)
    try:
        signature = str(inspect.signature(original or obj))
    except (TypeError, ValueError):
        signature = None
    return {
        "module": getattr(original or obj, "__module__", None),
        "name": getattr(original or obj, "__qualname__", None),
        "signature": signature,
        "source": source,
        "source_sha256": sha(Path(source)) if source and Path(source).is_file() else None,
    }


def capture_wrappers(module: Any, state: dict[str, Any]) -> dict[str, Any]:
    originals: dict[str, Any] = {}

    def patch(name: str, wrapper: Any) -> None:
        originals[name] = getattr(module, name)
        setattr(module, name, wrapper(originals[name]))

    def wrap_load(original: Any) -> Any:
        def run(*args: Any, **kwargs: Any) -> Any:
            state["load_call"] = {"args": [str(x) for x in args], "kwargs": kwargs}
            predictions, debug = original(*args, **kwargs)
            state["segmentation"] = {
                name: arr_info(getattr(predictions, name, None))
                for name in ("preprocessed", "staff", "notehead", "symbols", "stems_rest", "clefs_keys")
            }
            return predictions, debug

        return run

    def wrap_symbols(original: Any) -> Any:
        def run(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            state["predict_symbols"] = symbols_info(result)
            return result

        return run

    def wrap_break(original: Any) -> Any:
        def run(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            state["break_wide_staff_fragments"] = boxes_info(result)
            return result

        return run

    def wrap_combine(original: Any) -> Any:
        def run(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            heights = []
            for item in result:
                size = getattr(getattr(item, "notehead", None), "size", None)
                if size is not None and len(size) >= 2:
                    heights.append(float(size[1]))
            state["noteheads_with_stems"] = {
                "count": len(result),
                "height_median": statistics.median(heights) if heights else None,
            }
            return result

        return run

    def wrap_detect_staff(original: Any) -> Any:
        def run(*args: Any, **kwargs: Any) -> Any:
            primary = args[4] if len(args) >= 5 else kwargs.get("bar_line_boxes", [])
            state["primary_barlines_before_detect_staff"] = boxes_info(primary)
            return original(*args, **kwargs)

        return run

    patch("load_and_preprocess_predictions", wrap_load)
    patch("predict_symbols", wrap_symbols)
    patch("break_wide_fragments", wrap_break)
    patch("combine_noteheads_with_stems", wrap_combine)
    patch("detect_staff", wrap_detect_staff)
    return originals


def enable_segnet_cache() -> dict[str, Any]:
    for name in ("homr_eval_scripts.segnet_cache", "src.homr_eval_scripts.segnet_cache"):
        try:
            module = __import__(name, fromlist=["enable_segnet_cache"])
            return {"module": name, "enabled": bool(module.enable_segnet_cache())}
        except ImportError:
            continue
    return {"module": None, "enabled": False}


def run_cell(name: str, proxy: Path, out: Path) -> int:
    implementation_name, debug_enabled, prediction_cache = CELLS[name]
    out.mkdir(parents=True, exist_ok=False)
    cell_proxy = out / proxy.name
    shutil.copy2(proxy, cell_proxy)

    import torch
    import homr.main as homr_main
    from homr import constants
    from src.pipeline.detection.homr_profile_compat import (
        build_processing_config_compat,
        install_current_homr_consumer_compat,
        install_homr_api_compat,
    )

    use_gpu = bool(torch.cuda.is_available())
    if implementation_name == "monolithic":
        from src.homr_eval_scripts import homr_evaluator as module

        compat = install_homr_api_compat(module)
        config = module.ProcessingConfig(debug_enabled, prediction_cache, False, False, -1)
        tuning = dict(module.DEFAULT_TUNING)
        detect = module.detect_staffs_with_barlines
        detect_args = (str(cell_proxy), config, tuning)
    else:
        from src.homr_eval_scripts.core import heuristics as module
        from src.homr_eval_scripts.core import predictor as predictor_module
        from src.homr_eval_scripts.core.utils import DEFAULT_TUNING

        compat = install_current_homr_consumer_compat(
            homr_main, predictor_module, module, use_gpu_inference=use_gpu
        )
        config = build_processing_config_compat(
            homr_main.ProcessingConfig,
            enable_debug=debug_enabled,
            enable_cache=prediction_cache,
            write_staff_positions=False,
            use_gpu_inference=use_gpu,
        )
        tuning = dict(DEFAULT_TUNING)
        detect = module.detect_staffs_with_barlines
        detect_args = (str(cell_proxy), config, tuning, use_gpu)

    state: dict[str, Any] = {
        "callables": {
            key: callable_info(getattr(module, key))
            for key in (
                "load_and_preprocess_predictions",
                "predict_symbols",
                "break_wide_fragments",
                "combine_noteheads_with_stems",
                "detect_staff",
            )
        }
    }
    originals = capture_wrappers(module, state)
    session_cache = enable_segnet_cache()
    try:
        result = detect(*detect_args)
    finally:
        for key, original in originals.items():
            setattr(module, key, original)

    multi_staffs, preprocessed, debug, title_future, primary, notehead, staff = result
    cancel = getattr(title_future, "cancel", None)
    if callable(cancel):
        cancel()
    state["return"] = {
        "primary_barlines": boxes_info(primary),
        "preprocessed": arr_info(preprocessed),
        "staff_mask": arr_info(staff),
        "notehead_mask": arr_info(notehead),
        "multi_staff_count": len(multi_staffs),
        "membership": [len(getattr(item, "staffs", [])) for item in multi_staffs],
    }
    median = state.get("noteheads_with_stems", {}).get("height_median")
    if median is not None:
        state["thresholds"] = {
            "average_notehead_height": median,
            "min_height": float(constants.bar_line_min_height(median)),
            "max_width": float(constants.bar_line_max_width(median)),
        }

    segmentation = {}
    try:
        import homr.segmentation.config as seg_config

        segmentation = {
            "module": str(Path(seg_config.__file__).resolve()),
            "segmentation_version": str(getattr(seg_config, "segmentation_version", None)),
            "fp16": file_info(Path(str(getattr(seg_config, "segnet_path_onnx_fp16", "")))),
        }
    except Exception as error:  # noqa: BLE001
        segmentation = {"error": repr(error)}

    report = {
        "schema_version": "issue274.primary_homr_stage_cell.v1",
        "status": "completed",
        "cell": name,
        "implementation": implementation_name,
        "debug": debug_enabled,
        "prediction_cache": prediction_cache,
        "use_gpu": use_gpu,
        "proxy": file_info(cell_proxy),
        "compat": compat,
        "segnet_session_cache": session_cache,
        "segmentation_runtime": segmentation,
        "npy_files": [file_info(path) for path in sorted(out.rglob("*.npy"))],
        "state": state,
    }
    write_json(out / "cell_report.json", report)
    return 0


def resolve_case(ab: Path, score: str, page: str, workspace: Path) -> dict[str, Any]:
    rows = load_json(ab)["hybrid_ab"]["pages"]
    matches = [row for row in rows if row["score"] == score and row["page"] == page]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one AB row for {score}/{page}, got {len(matches)}")
    row = matches[0]
    b = ws_path(row["b_current_x4_path"], workspace).resolve()
    c = ws_path(row["c_pinned_x4_path"], workspace).resolve()
    request = next(
        (
            parent / "current_homr_request.json"
            for parent in b.parents
            if (parent / "current_homr_request.json").is_file()
        ),
        None,
    )
    if request is None:
        raise FileNotFoundError(f"current_homr_request.json above {b}")
    request_data = load_json(request)
    sr = ws_path(request_data["sr_image"], workspace).resolve()
    stem = page
    return {
        "b": b,
        "c": c,
        "request": request,
        "sr": sr,
        "b_proxy": b.parent / f"{stem}_proxy.png",
        "c_proxy": c.parent / f"{stem}_proxy.png",
    }


def make_proxy(sr: Path, out: Path) -> dict[str, Any]:
    image = cv2.imread(str(sr), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(sr)
    height, width = image.shape[:2]
    pixels = height * width
    if pixels > TARGET_PIXELS * 1.5:
        scale = math.sqrt(pixels / TARGET_PIXELS)
        proxy = cv2.resize(image, (int(width / scale), int(height / scale)))
    else:
        scale = 1.0
        proxy = image
    if not cv2.imwrite(str(out), proxy):
        raise RuntimeError(f"Failed to write {out}")
    return {"sr": file_info(sr), "sr_shape": [height, width], "scale": scale, "proxy": file_info(out)}


def value_at(payload: Mapping[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def compare(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    stages = [
        ("proxy", "proxy.sha256"),
        ("seg.preprocessed", "state.segmentation.preprocessed.sha256"),
        ("seg.staff", "state.segmentation.staff.sha256"),
        ("seg.notehead", "state.segmentation.notehead.sha256"),
        ("seg.symbols", "state.segmentation.symbols.sha256"),
        ("seg.stems_rest", "state.segmentation.stems_rest.sha256"),
        ("seg.clefs_keys", "state.segmentation.clefs_keys.sha256"),
        ("symbols.noteheads", "state.predict_symbols.noteheads.multiset_sha256"),
        ("symbols.staff_fragments", "state.predict_symbols.staff_fragments.multiset_sha256"),
        ("symbols.clefs_keys", "state.predict_symbols.clefs_keys.multiset_sha256"),
        ("symbols.stems_rest", "state.predict_symbols.stems_rest.multiset_sha256"),
        ("symbols.bar_lines", "state.predict_symbols.bar_lines.multiset_sha256"),
        ("break_wide", "state.break_wide_staff_fragments.multiset_sha256"),
        ("primary_barlines", "state.primary_barlines_before_detect_staff.multiset_sha256"),
    ]
    rows = []
    first = None
    for stage, path in stages:
        a, b = value_at(left, path), value_at(right, path)
        exact = a is not None and a == b
        row = {"stage": stage, "exact": exact, "left": a, "right": b}
        rows.append(row)
        if first is None and not exact:
            first = row
    return {"all_exact": first is None, "first_divergence": first, "stages": rows}


def run_master(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    ab = ws_path(args.ab_report, workspace).resolve()
    out = ws_path(args.output_root, workspace).resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Output must be new/empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    case = resolve_case(ab, args.score, args.page, workspace)
    proxy_path = out / "shared_proxy.png"
    proxy = make_proxy(case["sr"], proxy_path)
    for key in ("b_proxy", "c_proxy"):
        retained = case[key]
        proxy[f"retained_{key}"] = {
            "artifact": file_info(retained),
            "exact": retained.is_file() and sha(retained) == sha(proxy_path),
        }

    cells = {}
    for name in CELLS:
        cell_out = out / "cells" / name
        log = out / "cells" / f"{name}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--cell",
            name,
            "--proxy",
            str(proxy_path),
            "--cell-output",
            str(cell_out),
        ]
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.run(
                command,
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                text=True,
            )
        if process.returncode:
            tail = "\n".join(
                log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:]
            )
            raise RuntimeError(f"{name} failed ({process.returncode})\n{tail}")
        cells[name] = load_json(cell_out / "cell_report.json")

    mono = cells["monolithic_current_c_like"]
    core_b = cells["core_current_b_like"]
    core_match = cells["core_current_config_matched"]
    comparisons = {
        "monolithic_vs_core_production": compare(mono, core_b),
        "monolithic_vs_core_config_matched": compare(mono, core_match),
        "core_production_vs_config_matched": compare(core_b, core_match),
    }
    matched = comparisons["monolithic_vs_core_config_matched"]
    config = comparisons["core_production_vs_config_matched"]
    if matched["all_exact"]:
        decision = (
            "primary_equivalent_when_config_matched_config_causal"
            if not config["all_exact"]
            else "primary_equivalent_current_runtime_no_primary_cause_found"
        )
    else:
        decision = "first_divergence_" + matched["first_divergence"]["stage"].replace(".", "_")

    report = {
        "schema_version": "issue274.primary_homr_stage_boundary.v1",
        "status": "completed",
        "decision": decision,
        "scope": {
            "score": args.score,
            "page": args.page,
            "primary_homr_executions": 3,
            "shared_proxy": True,
            "thin": False,
            "xml_tromr": False,
            "sr": False,
            "omr_dln": False,
            "dense": False,
            "cnn": False,
            "mmr": False,
        },
        "inputs": {
            "ab_report": file_info(ab),
            "b_detection": file_info(case["b"]),
            "c_detection": file_info(case["c"]),
            "current_request": file_info(case["request"]),
            "proxy": proxy,
        },
        "cells": cells,
        "comparisons": comparisons,
        "rule": (
            "Treat only the first divergent stage as the next causal boundary; "
            "later differences are consequences until separately proven."
        ),
    }
    output = out / "issue274_primary_stage_boundary.json"
    write_json(output, report)
    print(json.dumps({"status": "completed", "decision": decision, "output": str(output)}))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", type=Path, default=Path("/workspace"))
    result.add_argument("--ab-report", type=Path, default=AB_DEFAULT)
    result.add_argument("--score", default="Shostakovich-Sym5-Va")
    result.add_argument("--page", default="page_013")
    result.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    result.add_argument("--cell", choices=list(CELLS))
    result.add_argument("--proxy", type=Path)
    result.add_argument("--cell-output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.cell:
            if args.proxy is None or args.cell_output is None:
                raise ValueError("--cell requires --proxy and --cell-output")
            return run_cell(args.cell, args.proxy.resolve(), args.cell_output.resolve())
        return run_master(args)
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"status": "failed", "error_type": type(error).__name__, "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
