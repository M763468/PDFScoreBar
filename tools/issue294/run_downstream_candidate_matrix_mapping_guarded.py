#!/usr/bin/env python3
"""Run the Issue #294 downstream matrix with the mapping-guarded grouping candidate.

This is an experiment-only entrypoint. It reuses the existing downstream matrix
implementation and substitutes only the MeasureNumberingPipeline constructor with
the retained-validated MappingGuardedConnectorPositivePipeline. Production source,
config, thresholds, detector dispatch, and MMR logic remain unchanged.
"""

from __future__ import annotations

from tools.issue294 import run_downstream_candidate_matrix as matrix
from tools.issue294.evaluate_mapping_guarded_connector_positive_candidate import (
    MappingGuardedConnectorPositivePipeline,
)


def main() -> int:
    matrix.MeasureNumberingPipeline = MappingGuardedConnectorPositivePipeline
    return matrix.main()


if __name__ == "__main__":
    raise SystemExit(main())
