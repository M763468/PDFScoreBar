import argparse
import datetime as dt
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.pipeline.core.config import load_yaml
from src.pipeline.main import run_pipeline
from src.pipeline.review.manual_correction_handoff import (
    canonicalize_manual_correction_outputs,
    load_manual_correction_handoff,
    validate_manual_correction_handoff,
)
from src.pipeline.steps.manual_corrections import merge_measure_overrides
from src.pipeline.utils.io import ensure_dir

logger = logging.getLogger(__name__)


def _resolve_source_manifest_path(payload: dict[str, Any], package_root: Path) -> Path:
    source_manifest = payload.get("source_manifest")
    source_artifact_root = payload.get("source_artifact_root")

    if source_manifest:
        manifest_path = Path(str(source_manifest))
        if not manifest_path.is_absolute():
            if source_artifact_root:
                manifest_path = Path(str(source_artifact_root)) / manifest_path
            else:
                manifest_path = package_root / manifest_path
        return manifest_path.resolve()

    return (package_root.parent / "manifest.json").resolve()


def _unique_existing_paths(paths: List[str | Path]) -> List[Path]:
    unique: List[Path] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _read_json_object_if_exists(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _rewrite_measure_overrides_with_source_mmr_base(
    *,
    output_path: Path,
    source_mmr_override_paths: List[str | Path],
    staging_paths: Dict[str, List[str | Path]],
) -> None:
    """Preserve source MMR overrides so manual suppressions can remove them.

    GUI ``mmr_measure_span`` corrections are delta operations. In particular,
    ``op: suppress`` removes an existing MMR override rather than emitting a
    tombstone. Corrected reruns must therefore canonicalize against the source
    run's MMR override payloads and then disable fresh MMR generation for the
    rerun, otherwise the suppressed automatic override can reappear.
    """

    source_mmr_payloads = [
        _read_json_object_if_exists(path) for path in _unique_existing_paths(source_mmr_override_paths)
    ]
    measure_construction_payloads = [
        _read_json_object_if_exists(path)
        for path in _unique_existing_paths(staging_paths.get("measure_construction", []))
    ]
    mmr_measure_span_payloads = [
        _read_json_object_if_exists(path)
        for path in _unique_existing_paths(staging_paths.get("mmr_measure_span", []))
    ]

    measure_payload = merge_measure_overrides(
        *source_mmr_payloads,
        *measure_construction_payloads,
        *mmr_measure_span_payloads,
    )
    output_path.write_text(
        json.dumps(measure_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def apply_corrections_and_rerun(
    handoff_path: str | Path,
    config_path: Optional[str | Path] = None,
    output_root: Optional[str | Path] = None,
    run_id: Optional[str] = None,
    overwrite: bool = False,
    dry_run: bool = False,
) -> Path:
    """Apply manual corrections and trigger a corrected pipeline rerun."""
    handoff_path = Path(handoff_path).resolve()
    package_root = handoff_path.parent

    # 1. Load & validate handoff
    raw_payload = load_manual_correction_handoff(handoff_path)
    normalized = validate_manual_correction_handoff(
        raw_payload, handoff_path=handoff_path, mode="base_v1"
    )

    # Collect custom staging paths from normalized handoff
    staging_paths: Dict[str, List[str | Path]] = {
        "mmr_measure_span": [],
        "measure_construction": [],
        "barline_construction": [],
    }
    source_mmr_override_paths: List[str | Path] = []
    for page in normalized.get("pages", []):
        manual_outputs = page.get("manual_outputs", {})
        for key in staging_paths:
            if key in manual_outputs and manual_outputs[key]:
                staging_paths[key].append(package_root / manual_outputs[key])
        mmr_overrides = page.get("mmr_overrides")
        if mmr_overrides:
            source_mmr_override_paths.append(package_root / mmr_overrides)

    # 2. Check corrections dir
    corrections_dir = package_root / "corrections"
    # We don't raise an error here if it doesn't exist, as canonicalize will create it if needed.

    # 3. Canonicalize outputs
    canonical_paths = canonicalize_manual_correction_outputs(
        corrections_dir,
        overwrite=overwrite,
        staging_paths=staging_paths,
    )
    if source_mmr_override_paths:
        _rewrite_measure_overrides_with_source_mmr_base(
            output_path=canonical_paths["measure_overrides"],
            source_mmr_override_paths=source_mmr_override_paths,
            staging_paths=staging_paths,
        )

    # 4. Find/Load source config
    source_config: Dict[str, Any] = {}
    if config_path:
        source_config_path = Path(config_path)
        if source_config_path.suffix in (".yaml", ".yml"):
            source_config = load_yaml(source_config_path)
        else:
            source_config = json.loads(source_config_path.read_text(encoding="utf-8"))
        if not isinstance(source_config, dict):
            raise ValueError("Source configuration must be a dictionary/mapping.")
    else:
        manifest_path = _resolve_source_manifest_path(normalized, package_root)
        if not manifest_path.exists():
            raise FileNotFoundError(f"Source manifest not found: {manifest_path}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest.json must be a JSON object.")
        if "config" not in manifest:
            raise ValueError("manifest.json does not contain a 'config' key.")
        source_config = manifest["config"]
        if not isinstance(source_config, dict):
            raise ValueError("Source configuration must be a dictionary/mapping.")

        # We can also use this to set default output_root
        if not output_root:
            output_root = manifest_path.parent.parent

    # 5. Create rerun config
    rerun_config = deepcopy(source_config)

    if not isinstance(rerun_config.get("inputs"), dict):
        rerun_config["inputs"] = {}

    rerun_config["inputs"]["measure_overrides"] = str(canonical_paths["measure_overrides"])
    rerun_config["inputs"]["barline_overrides"] = str(canonical_paths["barline_overrides"])

    if not isinstance(rerun_config.get("steps"), dict):
        rerun_config["steps"] = {}
    rerun_config["steps"]["apply_measure_overrides"] = True
    rerun_config["steps"]["apply_barline_overrides"] = True
    if source_mmr_override_paths:
        rerun_config["steps"]["mmr_overrides"] = False

    if not isinstance(rerun_config.get("outputs"), dict):
        rerun_config["outputs"] = {}
    if not isinstance(rerun_config["outputs"].get("review"), dict):
        rerun_config["outputs"]["review"] = {}

    # Avoid infinite recursion of review package generation
    rerun_config["outputs"]["review"]["manual_correction_package"] = False

    # 6. Setup new run dir
    run_id_value = run_id or f"corrected_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if output_root:
        out_root = Path(output_root)
    else:
        # Default to the same root as the original run
        out_root = package_root.parent.parent

    new_run_dir = out_root / run_id_value
    ensure_dir(new_run_dir)

    new_config_path = new_run_dir / "corrected_pipeline_config.json"
    new_config_path.write_text(
        json.dumps(rerun_config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    summary = {
        "source_handoff": str(handoff_path),
        "measure_overrides": str(canonical_paths["measure_overrides"]),
        "barline_overrides": str(canonical_paths["barline_overrides"]),
        "source_mmr_overrides": [str(path) for path in _unique_existing_paths(source_mmr_override_paths)],
        "rerun_mmr_overrides_enabled": bool(rerun_config["steps"].get("mmr_overrides", False)),
        "run_id": run_id_value,
        "output_dir": str(new_run_dir),
    }

    # Write summary in the new run dir
    summary_path = new_run_dir / "review" / "correction_summary.json"
    ensure_dir(summary_path.parent)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # Also write a summary back in the corrections dir
    back_summary_path = corrections_dir / "apply_summary.json"
    back_summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    if dry_run:
        logger.info(f"Dry run. Would execute pipeline with config: {new_config_path}")
        return new_run_dir

    # 7. Execute
    logger.info(f"Executing corrected pipeline rerun: {run_id_value}")
    run_pipeline(
        config_path=new_config_path,
        run_id=run_id_value,
        output_root=out_root,
        dry_run=dry_run,
    )

    return new_run_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply manual corrections and rerun the pipeline.")
    parser.add_argument("handoff", type=Path, help="Path to review/manual_correction_input.json")
    parser.add_argument("--config", type=Path, help="Path to original pipeline config (yaml/json).")
    parser.add_argument("--output-root", type=Path, help="Root directory for the corrected run.")
    parser.add_argument("--run-id", type=str, help="Run ID for the corrected run.")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing canonical override files."
    )
    parser.add_argument("--dry-run", action="store_true", help="Dry run.")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    apply_corrections_and_rerun(
        handoff_path=args.handoff,
        config_path=args.config,
        output_root=args.output_root,
        run_id=args.run_id,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
