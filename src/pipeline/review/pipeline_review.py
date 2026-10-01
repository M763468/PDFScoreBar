"""Review-package configuration, prerequisites and corrected manifest selection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from src.pipeline.core.config import get_nested


@dataclass(frozen=True)
class ReviewPackageConfig:
    enabled: bool
    review_root: Path
    overwrite: bool
    source_pipeline_command: str | None


def resolve_review_package_config(config: Dict[str, Any], run_dir: Path) -> ReviewPackageConfig:
    """Resolve the config-first review package output contract.

    This is intentionally scoped to the low-level ``run_pipeline()`` layout.
    The #226/#227 public ``OUTPUT_DIR/{final,review,debug}`` materializer is
    a separate follow-up surface.
    """
    review_cfg = get_nested(config, "outputs", "review", default={}) or {}
    if not isinstance(review_cfg, dict):
        raise ValueError("outputs.review must be a mapping when provided.")

    enabled = bool(review_cfg.get("manual_correction_package", False))
    review_root_raw = review_cfg.get("root")
    if review_root_raw:
        review_root = Path(str(review_root_raw))
        if not review_root.is_absolute():
            review_root = run_dir / review_root
    else:
        review_root = run_dir / "review"

    source_pipeline_command_raw = review_cfg.get("source_pipeline_command")
    source_pipeline_command = (
        str(source_pipeline_command_raw) if source_pipeline_command_raw else None
    )

    return ReviewPackageConfig(
        enabled=enabled,
        review_root=review_root,
        overwrite=review_cfg.get("overwrite") is not False,
        source_pipeline_command=source_pipeline_command,
    )


def validate_review_package_prerequisites(
    config: Dict[str, Any], review_config: ReviewPackageConfig
) -> None:
    if not review_config.enabled:
        return

    required_steps = {
        "numbering_base": get_nested(config, "steps", "numbering_base", default=False),
    }
    missing = [name for name, enabled in required_steps.items() if not enabled]
    if missing:
        raise ValueError(
            "outputs.review.manual_correction_package requires these steps to be enabled: "
            + ", ".join(missing)
        )


def resolved_for_manifest(
    *,
    review_enabled: bool,
    page_ids: List[str],
    resolved: List[Dict[str, Any]],
    page_ctx: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    manifest_resolved = []
    for page_id, item in zip(page_ids, resolved):
        manifest_item = dict(item)
        corrected_path = page_ctx.get(page_id, {}).get("barlines_path")
        if review_enabled and corrected_path and Path(corrected_path).exists():
            manifest_item["barlines_json"] = str(corrected_path)
        manifest_resolved.append(manifest_item)
    return manifest_resolved
