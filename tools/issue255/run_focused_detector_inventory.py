#!/usr/bin/env python3
"""Run the Issue #255 focused detector inventory with corrected classification."""

from __future__ import annotations

from tools.issue255 import trace_focused_detector_boundaries as implementation
from tools.issue255.first_loss_boundary import classify_first_loss_boundary

# Keep the existing CLI and report implementation while replacing the v1 classifier.
implementation._first_loss_boundary = classify_first_loss_boundary


def main() -> int:
    return implementation.main()


if __name__ == "__main__":
    raise SystemExit(main())
