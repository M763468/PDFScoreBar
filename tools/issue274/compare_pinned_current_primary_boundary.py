#!/usr/bin/env python3
"""Compare pinned Stage-E and current raw primary HOMR on identical retained x4 proxies.

Issue #274 causal gate.

This experiment deliberately stops before PDFScoreBar thin-barline recovery, XML/TrOMR,
OMR-DLN, dense probe, CNN, and MMR.  Each case uses one byte-identical proxy image for
both runtimes and fingerprints the first primary-HOMR stage that differs.

The pinned cell uses the exact stage_e_verified runtime contract:
- /opt/venv_stage_e_homr/bin/python
- /opt/homr_stage_e_profile
- /opt/pdfscore_stage_e_profile
- pinned commit markers/models declared by stage_e_verified_homr.json

The current cell uses /opt/venv_pipeline/bin/python and the current workspace source.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from tools.issue274 import capture_primary_homr_stage_boundary as base

ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = ROOT / "configs/detector_profiles/stage_e_verified_homr.json"
AB_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/stage_e_ab_01/"
    "issue274_homr_x4_stage_e_ab.json"
)
OUT_DEFAULT = Path(
    "logs/issue274_homr_unification_analysis/pinned_current_primary_boundary_01"
)
DEFAULT_CASES = (
    ("Shostakovich-Sym5-Va", "page_013"),
    ("Sibelius-Violin_Concerto-Viola", "page_004"),
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return base.sha(path)


def _latest_compat_module() -> Any:
    """Load the workspace compatibility module without resolving `src` via PYTHONPATH.

    The pinned child deliberately has /opt/pdfscore_stage_e_profile first on PYTHONPATH.
    Loading by absolute file path keeps the compatibility shim itself current while the
    evaluator imported below still comes from the pinned PDFScore source, matching the
    production profile architecture.
    """
    path = ROOT / "src/pipeline/detection/homr_profile_compat.py"
    spec = importlib.util.spec_from_file_location("issue274_current_profile_compat", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load compatibility module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _segmentation_runtime() -> dict[str, Any]:
    try:
        import homr.segmentation.config as seg_config

        result = {
            "module": str(Path(seg_config.__file__).resolve()),
            "segmentation_version": str(getattr(seg_config, "segmentation_version", None)),
        }
        for key in ("segnet_path_onnx", "segnet_path_onnx_fp16"):
            value = getattr(seg_config, key, None)
            path = None if value is None else Path(str(value))
            result[key] = base.file_info(path)
        return result
    except Exception as error:  # noqa: BLE001
        return {"error": repr(error)}


def _runtime_markers() -> dict[str, Any]:
    candidates = (
        Path("/opt/homr_stage_e_profile_commit.txt"),
        Path("/opt/pdfscore_stage_e_profile_commit.txt"),
    )
    return {
        str(path): (
            path.read_text(encoding="utf-8").strip() if path.is_file() else None
        )
        for path in candidates
    }


def run_cell(runtime: str, proxy: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=False)
    cell_proxy = out / proxy.name
    shutil.copy2(proxy, cell_proxy)

    # `src.homr_eval_scripts` resolves to current or pinned PDFScore according to
    # the child process PYTHONPATH prepared by the master.
    evaluator = importlib.import_module("src.homr_eval_scripts.homr_evaluator")
    compat_module = _latest_compat_module()
    compat = compat_module.install_homr_api_compat(evaluator)

    config = evaluator.ProcessingConfig(True, False, False, False, -1)
    tuning = dict(evaluator.DEFAULT_TUNING)

    state: dict[str, Any] = {
        "callables": {
            key: base.callable_info(getattr(evaluator, key))
            for key in (
                "load_and_preprocess_predictions",
                "predict_symbols",
                "break_wide_fragments",
                "combine_noteheads_with_stems",
                "detect_staff",
            )
        }
    }
    originals = base.capture_wrappers(evaluator, state)
    session_cache = base.enable_segnet_cache()
    try:
        result = evaluator.detect_staffs_with_barlines(
            str(cell_proxy),
            config,
            tuning,
        )
    finally:
        for key, original in originals.items():
            setattr(evaluator, key, original)

    multi_staffs, preprocessed, debug, title_future, primary, notehead, staff = result
    cancel = getattr(title_future, "cancel", None)
    if callable(cancel):
        cancel()

    state["return"] = {
        "primary_barlines": base.boxes_info(primary),
        "preprocessed": base.arr_info(preprocessed),
        "staff_mask": base.arr_info(staff),
        "notehead_mask": base.arr_info(notehead),
        "multi_staff_count": len(multi_staffs),
        "membership": [len(getattr(item, "staffs", [])) for item in multi_staffs],
    }

    report = {
        "schema_version": "issue274.pinned_current_primary_cell.v1",
        "status": "completed",
        "runtime": runtime,
        "python": sys.executable,
        "python_version": sys.version,
        "sys_path": sys.path,
        "proxy": base.file_info(cell_proxy),
        "evaluator_source": base.file_info(Path(evaluator.__file__).resolve()),
        "compat": compat,
        "segnet_session_cache": session_cache,
        "segmentation_runtime": _segmentation_runtime(),
        "profile_commit_markers": _runtime_markers(),
        "state": state,
    }
    _write_json(out / "cell_report.json", report)
    return 0


def _profile_environment(profile: dict[str, Any]) -> tuple[str, dict[str, str]]:
    runtime = profile["runtime"]
    python = str(runtime["python"])
    entries = [
        str(runtime["homr_source"]),
        str(runtime["pdfscore_source"]),
        f'{runtime["pdfscore_source"]}/src',
        str(ROOT),
    ]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    if existing:
        entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    env.setdefault("HOME", "/tmp")
    return python, env


def _current_environment() -> tuple[str, dict[str, str]]:
    python = "/opt/venv_pipeline/bin/python"
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    entries = [str(ROOT)]
    if existing:
        entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return python, env


def _parse_cases(values: list[str]) -> list[tuple[str, str]]:
    if not values:
        return list(DEFAULT_CASES)
    result: list[tuple[str, str]] = []
    for value in values:
        if ":" not in value:
            raise ValueError(f"Invalid --case {value!r}; expected SCORE:page_XXX")
        score, page = value.rsplit(":", 1)
        result.append((score, page))
    return result


def _run_child(
    *,
    python: str,
    env: dict[str, str],
    runtime: str,
    proxy: Path,
    output: Path,
    log: Path,
) -> dict[str, Any]:
    command = [
        python,
        str(Path(__file__).resolve()),
        "--cell-runtime",
        runtime,
        "--proxy",
        str(proxy),
        "--cell-output",
        str(output),
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if process.returncode:
        tail = "\n".join(
            log.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        )
        raise RuntimeError(
            f"{runtime} primary cell failed ({process.returncode})\n{tail}"
        )
    return _load_json(output / "cell_report.json")


def _validate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    runtime = profile["runtime"]
    expected_homr = profile["homr"]["commit"]
    expected_pdfscore = profile["pdfscore_evaluator"]["commit"]
    homr_marker = Path(str(runtime["homr_commit_marker"]))
    pdfscore_marker = Path(str(runtime["pdfscore_commit_marker"]))
    actual_homr = (
        homr_marker.read_text(encoding="utf-8").strip()
        if homr_marker.is_file()
        else None
    )
    actual_pdfscore = (
        pdfscore_marker.read_text(encoding="utf-8").strip()
        if pdfscore_marker.is_file()
        else None
    )
    return {
        "name": profile.get("name"),
        "python": base.file_info(Path(str(runtime["python"]))),
        "homr_source": str(runtime["homr_source"]),
        "pdfscore_source": str(runtime["pdfscore_source"]),
        "homr_commit": {"expected": expected_homr, "actual": actual_homr},
        "pdfscore_commit": {"expected": expected_pdfscore, "actual": actual_pdfscore},
        "valid": actual_homr == expected_homr and actual_pdfscore == expected_pdfscore,
    }


def run_master(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    ab = base.ws_path(args.ab_report, workspace).resolve()
    out = base.ws_path(args.output_root, workspace).resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Output must be new/empty: {out}")
    out.mkdir(parents=True, exist_ok=True)

    profile = _load_json(PROFILE_PATH)
    profile_validation = _validate_profile(profile)
    if not profile_validation["valid"]:
        raise RuntimeError(f"Pinned profile validation failed: {profile_validation}")

    current_python, current_env = _current_environment()
    pinned_python, pinned_env = _profile_environment(profile)

    case_reports = []
    for score, page in _parse_cases(args.case):
        case = base.resolve_case(ab, score, page, workspace)
        case_root = out / score / page
        case_root.mkdir(parents=True, exist_ok=True)
        proxy_path = case_root / "shared_proxy.png"
        proxy_meta = base.make_proxy(case["sr"], proxy_path)
        retained = {}
        for key in ("b_proxy", "c_proxy"):
            path = case[key]
            retained[key] = {
                "artifact": base.file_info(path),
                "exact": path.is_file() and _sha(path) == _sha(proxy_path),
            }
        if not all(item["exact"] for item in retained.values()):
            raise RuntimeError(
                f"Generated proxy differs from retained B/C proxy for {score}/{page}: "
                f"{retained}"
            )

        current = _run_child(
            python=current_python,
            env=current_env,
            runtime="current",
            proxy=proxy_path,
            output=case_root / "current",
            log=case_root / "current.log",
        )
        pinned = _run_child(
            python=pinned_python,
            env=pinned_env,
            runtime="pinned_stage_e_verified",
            proxy=proxy_path,
            output=case_root / "pinned",
            log=case_root / "pinned.log",
        )
        comparison = base.compare(current, pinned)
        case_reports.append(
            {
                "score": score,
                "page": page,
                "inputs": {
                    "x4_sr": base.file_info(case["sr"]),
                    "shared_proxy": proxy_meta,
                    "retained_proxy_checks": retained,
                    "retained_b_detection": base.file_info(case["b"]),
                    "retained_c_detection": base.file_info(case["c"]),
                },
                "current": current,
                "pinned": pinned,
                "comparison": comparison,
            }
        )

    divergent = [
        case for case in case_reports if not case["comparison"]["all_exact"]
    ]
    first_stages = [
        case["comparison"]["first_divergence"]["stage"]
        for case in divergent
        if case["comparison"]["first_divergence"] is not None
    ]
    if not divergent:
        decision = "pinned_and_current_primary_exact_on_all_cases"
    elif len(set(first_stages)) == 1:
        decision = f"consistent_first_divergence_{first_stages[0].replace('.', '_')}"
    else:
        decision = "pinned_current_primary_divergence_is_page_dependent"

    report = {
        "schema_version": "issue274.pinned_current_primary_boundary.v1",
        "status": "completed",
        "decision": decision,
        "scope": {
            "cases": len(case_reports),
            "primary_homr_executions": len(case_reports) * 2,
            "shared_proxy_per_case": True,
            "thin": False,
            "xml_tromr": False,
            "sr": False,
            "omr_dln": False,
            "dense": False,
            "cnn": False,
            "mmr": False,
        },
        "profile": profile_validation,
        "cases": case_reports,
        "interpretation_rule": (
            "Only the first divergent primary stage is causal for this gate. "
            "If primary stages are exact, retained B/C final differences must be "
            "attributed after primary extraction (for example thin/post-processing)."
        ),
    }
    output = out / "issue274_pinned_current_primary_boundary.json"
    _write_json(output, report)
    print(
        json.dumps(
            {"status": "completed", "decision": decision, "output": str(output)},
            ensure_ascii=False,
        )
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--workspace", type=Path, default=Path("/workspace"))
    result.add_argument("--ab-report", type=Path, default=AB_DEFAULT)
    result.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    result.add_argument(
        "--case",
        action="append",
        default=[],
        help="Focused case as SCORE:page_XXX; defaults to Sym5 p013 and Sibelius p004.",
    )
    result.add_argument(
        "--cell-runtime",
        choices=("current", "pinned_stage_e_verified"),
    )
    result.add_argument("--proxy", type=Path)
    result.add_argument("--cell-output", type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.cell_runtime:
            if args.proxy is None or args.cell_output is None:
                raise ValueError("--cell-runtime requires --proxy and --cell-output")
            return run_cell(
                args.cell_runtime,
                args.proxy.resolve(),
                args.cell_output.resolve(),
            )
        return run_master(args)
    except Exception as error:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
