#!/usr/bin/env python3
"""CLI shim for the Issue #294 mapping-guarded retained MMR rescore."""

from __future__ import annotations

from tools.issue294._mapping_guarded_candidate_mmr_rescore import (
    _assert_source_numbering_shape,
    _rebase_accepted_expected_to_candidate,
    _score_to_numbering,
    main,
    run,
)

__all__ = [
    "_assert_source_numbering_shape",
    "_rebase_accepted_expected_to_candidate",
    "_score_to_numbering",
    "main",
    "run",
]


if __name__ == "__main__":
    raise SystemExit(main())
