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
from src.pipeline.steps.manual_corrections import merge_barline_overrides, merge_measure_overrides
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


def _input_override_path(
    source_config: Dict[str, Any],
    key: str,
    *,
    base_dir: Path | None,
) -> Optional[Path]:
    inputs = source_config.get("inputs")
    if not isinstance(inputs, dict):
        return None
    raw_path = inputs.get(key)
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidates = [path]
    if not path.is_absolute() and base_dir is not None:
        candidates.append(base_dir / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _mmr_suppression_override_payload(
    staging_paths: Dict[str, List[str | Path]],
) -> Optional[Dict[str, Any]]:
    """Encode MMR suppress operations as neutral user overrides.

    The final numbering phase merges freshly generated MMR overrides first and
    user overrides second. A same-key user override with ``skip=0`` therefore
    cancels the automatic MMR skip without disabling MMR for unrelated pages.
    """

    overrides: List[Dict[str, Any]] = []
    seen: set[tuple[int, int, int]] = set()
    for path in _unique_existing_paths(staging_paths.get("mmr_measure_span", [])):
        payload = _read_json_object_if_exists(path)
        if not payload:
            continue
        items = payload.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or item.get("op") != "suppress":
                continue
            try:
                key = (int(item["page"]), int(item["system"]), int(item["measure"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid MMR suppress correction item: {item}") from exc
            if key in seen:
                continue
            seen.add(key)
            page, system, measure = key
            overrides.append(
                {
                    "page": page,
                    "system": system,
                    "measure": measure,
                    "skip": 0,
                    "comment": "manual MMR suppression",
                    "source": "manual:mmr_measure_span_suppress",
                }
            )
    if not overrides:
        return None
    return {"measure_overrides": overrides, "overrides": deepcopy(overrides)}


def _merge_existing_override_inputs(
    *,
    canonical_paths: Dict[str, Path],
    source_config: Dict[str, Any],
    config_base_dir: Path | None,
    staging_paths: Dict[str, List[str | Path]],
) -> Dict[str, Any]:
    existing_measure_path = _input_override_path(
        source_config, "measure_overrides", base_dir=config_base_dir
    )
    existing_barline_path = _input_override_path(
        source_config, "barline_overrides", base_dir=config_base_dir
    )

    current_measure_payload = _read_json_object_if_exists(canonical_paths["measure_overrides"])
    current_barline_payload = _read_json_object_if_exists(canonical_paths["barline_overrides"])
    suppression_payload = _mmr_suppression_override_payload(staging_paths)

    measure_payloads: List[Optional[Dict[str, Any]]] = []
    if existing_measure_path and existing_measure_path != canonical_paths["measure_overrides"].resolve():
        measure_payloads.append(_read_json_object_if_exists(existing_measure_path))
    measure_payloads.append(current_measure_payload)
    measure_payloads.append(suppression_payload)

    barline_payloads: List[Optional[Dict[str, Any]]] = []
    if existing_barline_path and existing_barline_path != canonical_paths["barline_overrides"].resolve():
        barline_payloads.append(_read_json_object_if_exists(existing_barline_path))
    barline_payloads.append(current_barline_payload)

    measure_payload = merge_measure_overrides(*measure_payloads)
    barline_payload = merge_barline_overrides(*barline_payloads)

    canonical_paths["measure_overrides"].write_text(
        json.dumps(measure_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    canonical_paths["barline_overrides"].write_text(
        json.dumps(barline_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "existing_measure_overrides": str(existing_measure_path) if existing_measure_path else None,
        "existing_barline_overrides": str(existing_barline_path) if existing_barline_path else None,
        "mmr_suppressions_encoded": bool(suppression_payload),
    }


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
    for page in normalized.get("pages", []):
        manual_outputs = page.get("manual_outputs", {})
        for key in staging_paths:
            if key in manual_outputs and manual_outputs[key]:
                staging_paths[key].append(package_root / manual_outputs[key])

    # 2. Check corrections dir
    corrections_dir = package_root / "corrections"
    # We don't raise an error here if it doesn't exist, as canonicalize will create it if needed.

    # 3. Canonicalize outputs
    canonical_paths = canonicalize_manual_correction_outputs(
        corrections_dir,
        overwrite=overwrite,
        staging_paths=staging_paths,
    )

    # 4. Find/Load source config
    source_config: Dict[str, Any] = {}
    config_base_dir: Path | None = None
    if config_path:
        source_config_path = Path(config_path).resolve()
        config_base_dir = source_config_path.parent
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
        config_base_dir = manifest_path.parent

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

    carried_forward = _merge_existing_override_inputs(
        canonical_paths=canonical_paths,
        source_config=source_config,
        config_base_dir=config_base_dir,
        staging_paths=staging_paths,
    )

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
        **carried_forward,
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
