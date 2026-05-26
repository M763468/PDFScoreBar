#!/usr/bin/env python3
"""Compatibility wrapper for the dense probe-candidate detector route.

The formal pipeline entrypoint is:

    python -m src.pipeline.detector_routes.dense_probe_candidate_route

This wrapper is kept for the #149 command surface and delegates to the regular
detector-level partial route used by #151.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.detector_routes.dense_probe_candidate import (  # noqa: E402
    build_arg_parser,
    config_from_args,
    resolve_paths,
    run_dense_probe_candidate_route,
)


def main() -> None:
    parser = build_arg_parser(description=__doc__)
    args = parser.parse_args()
    config = config_from_args(args)
    summary = run_dense_probe_candidate_route(config)
    paths = resolve_paths(config)
    print(f"Issue36 dense bands -> probe-rescue validation complete: {paths.eval_output_dir}")
    if summary:
        print(
            "Detector: "
            f"TP={summary.get('tp')} FP={summary.get('fp')} FN={summary.get('fn')} "
            f"Pred={summary.get('pred')} GT={summary.get('gt')}"
        )


if __name__ == "__main__":
    main()
