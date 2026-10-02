"""Operations supplied by the orchestrator to the numbering phases.

Capture these at dispatch time so legacy orchestrator hooks remain effective.
Model persistence, configuration and telemetry stay on the orchestrator context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class NumberingPhaseServices:
    apply_barline_overrides: Callable[..., Any]
    merge_measure_overrides: Callable[..., Any]
    normalize_barlines: Callable[..., Any]
    empty_numbering_payload: Callable[..., Any]
    final_numbering_metadata: Callable[..., Any]
    load_movement_boundary_payload: Callable[..., Any]
    movement_boundaries_for_page: Callable[..., Any]
    persisted_final_next_number: Callable[..., Any]
    rebase_mmr_overrides_to_page_local: Callable[..., Any]
    reject_movement_boundaries_on_excluded_pages: Callable[..., Any]
    run_mmr_batch: Callable[..., Any]
    ensure_dir: Callable[..., Any]
    load_json: Callable[..., Any]
    score_to_dict: Callable[..., Any]
    write_json: Callable[..., Any]
    tqdm: Callable[..., Any]
    torch: Any
    logger: Any
