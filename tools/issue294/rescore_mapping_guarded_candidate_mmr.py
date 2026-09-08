#!/usr/bin/env python3
"""CLI shim for the Issue #294 mapping-guarded retained MMR rescore.

The completed full68 MMR audit consumed ``score_to_dict(score)`` numbering payloads,
which intentionally move no-measure systems out of the index-bearing ``systems``
array into ``empty_systems``.  The retained rescore must reconstruct that exact
serialization contract before spatially rebasing retained actual overrides.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.measure_numbering.serialization import score_to_dict
from tools.issue294 import _mapping_guarded_candidate_mmr_rescore as _impl


def _score_to_numbering(score: Any) -> dict[str, Any]:
    """Return the exact index-bearing numbering contract used by the MMR audit."""

    return score_to_dict(score)


def _score_shape(score: Any) -> dict[str, Any]:
    """Summarize the serialized non-empty systems used by MMRProcessor."""

    numbering = _score_to_numbering(score)
    pages = numbering.get("pages")
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError("Numbering payload must contain exactly one page")
    systems = pages[0].get("systems")
    if not isinstance(systems, list):
        raise ValueError("Numbering payload lacks systems")
    measure_counts = [len(system["measures"]) for system in systems]
    return {
        "total_measures": sum(measure_counts),
        "system_staff_counts": [len(system["staves"]) for system in systems],
        "system_measure_counts": measure_counts,
    }


# Patch the implementation module's dynamic globals before exporting/running it.
# This keeps the evaluation implementation centralized while restoring the exact
# serialization contract used by run_full68_mmr_audit.py.
_impl._score_to_numbering = _score_to_numbering
_impl._score_shape = _score_shape

_assert_source_numbering_shape = _impl._assert_source_numbering_shape
_rebase_accepted_expected_to_candidate = _impl._rebase_accepted_expected_to_candidate
main = _impl.main
run = _impl.run

__all__ = [
    "_assert_source_numbering_shape",
    "_rebase_accepted_expected_to_candidate",
    "_score_shape",
    "_score_to_numbering",
    "main",
    "run",
]


if __name__ == "__main__":
    raise SystemExit(main())
