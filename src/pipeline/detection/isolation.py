"""Lightweight supervision for page-isolated production detection."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.pipeline.core.run_ids import build_probe_run_id
from src.pipeline.detection.input_contract import build_detector_input_contract

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ISOLATED_EXECUTION_MODE = "isolated_per_page"


def _validate_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, Mapping):
        raise ValueError("Isolated detector page lacks input contract")
    required = {
        "mode": "fresh_upstream",
        "fresh_upstream_authoritative": True,
        "override_keys": [],
    }
    mismatches = {
        key: {"expected": expected, "actual": contract.get(key)}
        for key, expected in required.items()
        if contract.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"Isolated detector fresh contract mismatch: {mismatches}")
    return dict(contract)


def _copy_probe_page(
    *,
    config: Mapping[str, Any],
    image: Path,
    source_root: Path,
    target_root: Path,
) -> Path:
    detection = config.get("detection")
    if not isinstance(detection, Mapping):
        raise ValueError("Detector config lacks detection settings")
    configured_score = detection.get("probe_score_name")
    score_name = str(configured_score) if configured_score else None
    page_run_id = build_probe_run_id(image, score_name=score_name)
    source = source_root / page_run_id
    if not source.is_dir():
        raise FileNotFoundError(f"Missing isolated probe page: {source}")
    target = target_root / page_run_id
    if target.exists():
        raise FileExistsError(target)
    shutil.copytree(source, target)
    return target


def _copy_hybrid_downstream_artifacts(
    *,
    image: Path,
    source_root: Path,
    target_root: Path,
) -> None:
    """Copy hybrid artifacts required by numbering after detector scoring."""
    stem = image.stem
    source_baseline = source_root / "baseline" / "batch" / stem
    target_baseline = target_root / "baseline" / "batch" / stem
    target_baseline.mkdir(parents=True, exist_ok=True)
    copied_mask = False
    for pattern in (
        "*_debug_3_staff.png",
        "*_staff_mask.png",
        "*_connector_symbols.png",
        "*_connector_brace_dot.png",
    ):
        for source in source_baseline.glob(pattern):
            shutil.copy2(source, target_baseline / source.name)
            if pattern in {"*_debug_3_staff.png", "*_staff_mask.png"}:
                copied_mask = True
    if not copied_mask:
        raise FileNotFoundError(f"Missing isolated baseline staff mask: {source_baseline}")

    source_hybrid = source_root / "hybrid_results" / f"{stem}_hybrid.json"
    if not source_hybrid.is_file():
        raise FileNotFoundError(source_hybrid)
    target_hybrid = target_root / "hybrid_results" / source_hybrid.name
    target_hybrid.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_hybrid, target_hybrid)


def _run_page_worker(
    *,
    config: Mapping[str, Any],
    image: Path,
    page_id: str,
    run_id: str,
    page_root: Path,
    dry_run: bool,
) -> dict[str, Any]:
    page_root.mkdir(parents=True, exist_ok=False)
    page_config = copy.deepcopy(dict(config))
    detection = page_config.get("detection")
    if not isinstance(detection, dict):
        detection = dict(detection or {})
        page_config["detection"] = detection
    # Keep every worker self-contained. This is an execution-path override only;
    # it does not substitute detector candidates or historical artifacts.
    detection["hybrid_output_root"] = str((page_root / "hybrid_output").resolve())

    request = {
        "schema_version": "pipeline.detector_isolated_page_request.v1",
        "config": page_config,
        "image": str(image.resolve()),
        "page_id": page_id,
        "run_id": run_id,
        "run_dir": str((page_root / "run").resolve()),
        "dry_run": dry_run,
    }
    request_path = page_root / "request.json"
    result_path = page_root / "result.json"
    request_path.write_text(
        json.dumps(request, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    command = [
        sys.executable,
        "-m",
        "src.pipeline.detection.isolated_page_worker",
        "--request",
        str(request_path),
        "--result",
        str(result_path),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT), env.get("PYTHONPATH", "")]).strip(
        os.pathsep
    )
    log_path = page_root / "worker.log"
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
    if process.returncode != 0:
        tail = ""
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-40:])
        except OSError:
            pass
        detail = f"Isolated detector page failed ({process.returncode}): {image}"
        if tail:
            detail += f"\n--- worker log tail ---\n{tail}"
        raise RuntimeError(detail)
    if not result_path.is_file():
        raise FileNotFoundError(f"Isolated detector worker did not write result: {result_path}")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or payload.get("status") != "completed":
        raise ValueError(f"Incomplete isolated detector page result: {result_path}")
    return dict(payload)


def run_detection_isolated_per_page(
    config: Mapping[str, Any],
    images: Sequence[Path],
    page_ids: Sequence[str],
    run_id: str,
    run_dir: Path,
    *,
    dry_run: bool,
    in_memory_images: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the verified detector with one disposable Python process per page."""
    if len(images) != len(page_ids):
        raise ValueError("images/page_ids length mismatch")
    if not images:
        raise ValueError("Page-isolated detection requires at least one page")
    if in_memory_images:
        raise ValueError("Page-isolated detection requires persisted image files")

    detection = config.get("detection")
    if not isinstance(detection, Mapping):
        raise ValueError("Detector config lacks detection settings")
    if detection.get("execution_mode") != ISOLATED_EXECUTION_MODE:
        raise ValueError(
            f"Page-isolated detector requires detection.execution_mode={ISOLATED_EXECUTION_MODE}"
        )

    aggregate_probe_root = run_dir / "intermediate" / "probe_scan"
    aggregate_hybrid_root = run_dir / "intermediate" / "isolated_hybrid"
    page_runs_root = run_dir / "intermediate" / "detector_page_runs"
    aggregate_probe_root.mkdir(parents=True, exist_ok=True)
    aggregate_hybrid_root.mkdir(parents=True, exist_ok=True)
    page_runs_root.mkdir(parents=True, exist_ok=True)

    if dry_run:
        contract = build_detector_input_contract(dict(detection))
        return {
            "commands": [["isolated_per_page:detector", str(image)] for image in images],
            "hybrid_output_dir": aggregate_hybrid_root,
            "probe_output_dir": aggregate_probe_root,
            "detector_input_contract": contract,
            "detector_input_contract_path": None,
            "detector_route": detection.get("detector_route"),
            "homr_profile": detection.get("homr_profile"),
            "execution_mode": ISOLATED_EXECUTION_MODE,
            "page_runs": [],
        }

    canonical_contract: dict[str, Any] | None = None
    commands: list[list[str]] = []
    page_runs: list[dict[str, Any]] = []
    for index, (image, page_id) in enumerate(zip(images, page_ids, strict=True), start=1):
        image = Path(image).resolve()
        if not image.is_file():
            raise FileNotFoundError(image)
        page_root = page_runs_root / f"{index:03d}_{image.parent.name}_{image.stem}"
        page_run_id = f"{run_id}__{index:03d}_{image.stem}"
        payload = _run_page_worker(
            config=config,
            image=image,
            page_id=str(page_id),
            run_id=page_run_id,
            page_root=page_root,
            dry_run=False,
        )
        contract = _validate_contract(payload.get("detector_input_contract"))
        if canonical_contract is None:
            canonical_contract = contract
        elif contract != canonical_contract:
            raise ValueError(f"Detector input contract drift at {image}")
        if payload.get("detector_route") != detection.get("detector_route"):
            raise ValueError(f"Detector route drift at {image}")
        if payload.get("homr_profile") != detection.get("homr_profile"):
            raise ValueError(f"HOMR profile drift at {image}")

        probe_root = Path(str(payload["probe_output_dir"])).resolve()
        hybrid_root = Path(str(payload["hybrid_output_dir"])).resolve()
        _copy_probe_page(
            config=config,
            image=image,
            source_root=probe_root,
            target_root=aggregate_probe_root,
        )
        _copy_hybrid_downstream_artifacts(
            image=image,
            source_root=hybrid_root,
            target_root=aggregate_hybrid_root,
        )
        commands.extend(payload.get("commands", []))
        page_runs.append(
            {
                "image": str(image),
                "page_id": str(page_id),
                "run_id": page_run_id,
                "page_root": str(page_root),
                "hybrid_output_dir": str(hybrid_root),
                "probe_output_dir": str(probe_root),
            }
        )

    if canonical_contract is None:
        raise RuntimeError("No isolated detector pages completed")
    contract_path = run_dir / "intermediate" / "detector_input_contract.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        json.dumps(canonical_contract, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {
        "commands": commands,
        "hybrid_output_dir": aggregate_hybrid_root,
        "probe_output_dir": aggregate_probe_root,
        "detector_input_contract": canonical_contract,
        "detector_input_contract_path": contract_path,
        "detector_route": detection.get("detector_route"),
        "homr_profile": detection.get("homr_profile"),
        "execution_mode": ISOLATED_EXECUTION_MODE,
        "page_runs": page_runs,
        "historical_detector_artifact_runtime_input": False,
    }
