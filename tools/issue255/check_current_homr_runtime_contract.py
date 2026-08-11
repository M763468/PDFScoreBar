#!/usr/bin/env python3
"""Validate the current HOMR API contract without running model inference."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _signature(callable_obj: Any) -> str:
    return str(inspect.signature(callable_obj))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _write_payload(payload: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if output is None:
        print(text, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    print(json.dumps({"status": payload.get("status"), "output": str(output)}))


def run() -> dict[str, Any]:
    import homr
    import homr.main as homr_main
    from homr.music_xml_generator import XmlGeneratorArguments
    from homr.segmentation.inference_segnet import Segnet
    from homr.transformer.configs import Config
    from src.homr_eval_scripts.core import heuristics as homr_heuristics
    from src.homr_eval_scripts.core import predictor as homr_predictor
    from src.pipeline.detection.connector_artifacts import install_homr_connector_artifact_capture
    from src.pipeline.detection.homr_profile_compat import (
        build_processing_config_compat,
        install_current_homr_consumer_compat,
        processing_config_compat_mode,
    )

    homr_file = Path(str(homr.__file__)).resolve()
    homr_main_file = Path(str(homr_main.__file__)).resolve()
    forbidden_roots = [
        (PROJECT_ROOT / "homr").resolve(),
        (PROJECT_ROOT / "external" / "homr").resolve(),
        Path("/opt/homr_stage_e_profile").resolve(),
    ]
    shadowed = [
        str(root)
        for root in forbidden_roots
        if _is_within(homr_file, root) or _is_within(homr_main_file, root)
    ]
    if shadowed:
        raise RuntimeError(
            "Current HOMR runtime is shadowed by a non-authoritative source: "
            + ", ".join(shadowed)
        )

    signatures = {
        "ProcessingConfig": _signature(homr_main.ProcessingConfig),
        "download_weights_homr_main": _signature(homr_main.download_weights),
        "download_weights_predictor_binding": _signature(homr_predictor.download_weights),
        "load_predictions_homr_main": _signature(homr_main.load_and_preprocess_predictions),
        "load_predictions_heuristics_binding": _signature(
            homr_heuristics.load_and_preprocess_predictions
        ),
        "parse_staffs": _signature(homr_main.parse_staffs),
        "Segnet": _signature(Segnet),
        "Config": _signature(Config),
        "XmlGeneratorArguments": _signature(XmlGeneratorArguments),
    }

    processing_config = build_processing_config_compat(
        homr_main.ProcessingConfig,
        enable_debug=False,
        enable_cache=True,
        write_staff_positions=False,
        use_gpu_inference=False,
    )
    transformer_config = Config()
    xml_args = XmlGeneratorArguments(False, None, None)

    compat_modes = install_current_homr_consumer_compat(
        homr_main,
        homr_predictor,
        homr_heuristics,
        use_gpu_inference=False,
    )
    connector_capture_installed = install_homr_connector_artifact_capture(
        homr_predictor.HomrPredictor
    )

    return {
        "schema_version": "issue255.current_homr_runtime_contract.v1",
        "status": "completed",
        "python": sys.executable,
        "homr": {
            "module_file": str(homr_file),
            "main_file": str(homr_main_file),
            "processing_config_mode": processing_config_compat_mode(homr_main.ProcessingConfig),
            "signatures": signatures,
            "compatibility": compat_modes,
        },
        "lightweight_construction": {
            "processing_config_type": type(processing_config).__name__,
            "transformer_config_type": type(transformer_config).__name__,
            "xml_arguments_type": type(xml_args).__name__,
            "connector_capture_installed": bool(connector_capture_installed),
        },
        "consumer_binding_after_compat": {
            "predictor_download_weights": _signature(homr_predictor.download_weights),
            "heuristics_load_predictions": _signature(
                homr_heuristics.load_and_preprocess_predictions
            ),
            "homr_main_parse_staffs": _signature(homr_main.parse_staffs),
        },
        "inference_executed": False,
        "historical_detector_artifact_runtime_input": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        payload = run()
    except Exception as error:  # noqa: BLE001
        payload = {
            "schema_version": "issue255.current_homr_runtime_contract.v1",
            "status": "failed",
            "error_type": type(error).__name__,
            "error": str(error),
            "python": sys.executable,
            "inference_executed": False,
        }
        _write_payload(payload, args.output)
        return 1
    _write_payload(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
