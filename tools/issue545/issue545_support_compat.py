"""Issue #545: which ``mmr_support_reuse`` implementations the geometry replay can evaluate.

``replay_mmr_variants.py`` builds its P0/C1/C2 candidates by patching
``_raw_mapped_bbox``.  That only changes the MMR views in the pre-#545 support
implementation (schema v1), where the current-x4 staff mapping supplies the MMR staff y.
Since #545 (schema v2) the views stay on Phase-A geometry and the mapping is diagnostic
only, so every geometry candidate would silently produce identical views.

Kept free of heavy imports so the check is testable without GPU/OCR dependencies.
"""

from __future__ import annotations

from typing import Any

X4_GEOMETRY_SCHEMA = "pipeline.mmr_support_reuse.v1"


def require_geometry_support(msr: Any, *, production_only: bool) -> None:
    """Exit unless ``msr`` can produce the requested replay candidates."""

    if production_only:
        return
    schema = getattr(msr, "SCHEMA_VERSION", None)
    if schema != X4_GEOMETRY_SCHEMA or not callable(getattr(msr, "_raw_mapped_bbox", None)):
        raise SystemExit(
            f"replay_mmr_variants: support schema {schema!r} is not {X4_GEOMETRY_SCHEMA!r}; "
            "patching _raw_mapped_bbox would not change MMR geometry, so P0/C1/C2 would be "
            "identical. Set PDFSCORE_CODE to a pre-#545 tree (e.g. 480d7bc7 or 11efed71), "
            "or pass --production-only to replay only this tree's production MMR (P0)."
        )
