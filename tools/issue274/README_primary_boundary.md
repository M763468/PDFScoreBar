# Issue #274 — pinned/current primary-HOMR boundary gate

## Purpose

Determine whether the accepted pinned Stage-E x4 producer and the current x4 producer first diverge inside raw/primary HOMR or only after primary extraction.

## Failed v1 run

`compare_pinned_current_primary_boundary.py` assumed every evaluator generation exported `DEFAULT_TUNING`. The pinned PDFScore evaluator commit `bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7` predates that constant and instead constructs the primary tuning dictionary directly from argparse values in `main()`.

The failure is a harness API-compatibility bug, not an experiment result.

## v2 compatibility contract

`compare_pinned_current_primary_boundary_v2.py` keeps the v1 comparison logic but injects the exact historical primary defaults used when `stage_e_verified` supplies no tuning overrides:

- `barline_min_height_factor = 1.0`
- `barline_max_width_factor = 1.0`
- `barline_staff_overlap_min = 0.0`
- edge margins `0`
- all optional primary candidate generators disabled

The injected values and their source are written to each cell report as `primary_tuning_contract`.

The v2 default output root is:

`logs/issue274_homr_unification_analysis/pinned_current_primary_boundary_02`

The failed `_01` output should be retained.
