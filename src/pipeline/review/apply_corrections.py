import argparse
import datetime as dt
import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from src.pipeline.core.config import load_yaml
from src.pipeline.main import run_pipeline
from src.pipeline.review.manual_correction_handoff import (
    canonicalize_manual_correction_outputs,
    load_manual_correction_handoff,
    validate_manual_correction_handoff,
)
from src.pipeline.utils.io import ensure_dir

logger = logging.getLogger(__name__)


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
    validate_manual_correction_handoff(raw_payload, handoff_path=handoff_path, mode="base_v1")

    # 2. Check corrections dir
    corrections_dir = package_root / "corrections"
    if not corrections_dir.is_dir():
        raise FileNotFoundError(f"Corrections directory not found: {corrections_dir}")

    # 3. Canonicalize outputs
    canonical_paths = canonicalize_manual_correction_outputs(corrections_dir, overwrite=overwrite)

    # 4. Find/Load source config
    source_config: Dict[str, Any] = {}
    if config_path:
        source_config_path = Path(config_path)
        if source_config_path.suffix in (".yaml", ".yml"):
            source_config = load_yaml(source_config_path)
        else:
            source_config = json.loads(source_config_path.read_text(encoding="utf-8"))
    else:
        # Try to find manifest.json in the parent of package root
        manifest_path = package_root.parent / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(
                "Source config path not provided and manifest.json not found in parent directory."
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if "config" not in manifest:
            raise ValueError("manifest.json does not contain a 'config' key.")
        source_config = manifest["config"]

    # 5. Create rerun config
    rerun_config = deepcopy(source_config)

    if "inputs" not in rerun_config:
        rerun_config["inputs"] = {}

    rerun_config["inputs"]["measure_overrides"] = str(canonical_paths["measure_overrides"])
    rerun_config["inputs"]["barline_overrides"] = str(canonical_paths["barline_overrides"])

    if "steps" not in rerun_config:
        rerun_config["steps"] = {}
    rerun_config["steps"]["apply_measure_overrides"] = True
    rerun_config["steps"]["apply_barline_overrides"] = True

    # Avoid infinite recursion of review package generation
    if "outputs" in rerun_config and "review" in rerun_config["outputs"]:
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
