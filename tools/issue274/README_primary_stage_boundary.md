# Issue #274 primary HOMR stage-boundary experiment

This experiment is intentionally narrower than a production substitution test.

## Why

The current production route after PR #278 still runs HOMR three times per page:

1. pinned HOMR on the original image (A),
2. current HOMR on the persisted x4 image (B),
3. pinned HOMR on the same persisted x4 image (C).

The remaining reduction target is therefore B + C -> one x4 HOMR execution.

The same-predictor-lifetime posthoc gate passed 4/4 pages, including exact x4 detections,
PR #265-normalized staff/notehead masks, and exact connector `symbols` / `brace_dot` masks.
That result removes predictor-lifetime state as a causal candidate; it does not justify adding
another original-image current HOMR call back to production.

## What this experiment isolates

`capture_primary_homr_stage_boundary.py` runs one retained x4 page through three isolated cells
inside the current runtime:

- monolithic evaluator with C-like settings (`debug=true`, prediction cache off),
- modular core with production-B settings (`debug=false`, prediction cache on),
- modular core with C-like settings (`debug=true`, prediction cache off).

All cells receive the same materialized proxy image. The tool fingerprints, in order:

1. preprocessed / SegNet-derived arrays (`staff`, `notehead`, `symbols`, `stems_rest`, `clefs_keys`),
2. `predict_symbols()` bounding boxes,
3. `break_wide_fragments()` staff-fragment normalization,
4. primary barline boxes immediately before `detect_staff()`.

Only the first divergent stage is treated as the next causal boundary. Later differences are
considered consequences unless independently demonstrated otherwise.

## Deliberate exclusions

The experiment does not run thin-barline recovery, XML/TrOMR parsing, SR, OMR-DLN, dense probe,
CNN, or MMR. It performs three primary HOMR executions on one focused page.

## Default focused case

The default is score-local `Shostakovich-Sym5-Va/page_013`, a retained B/C disagreement page.
The exact persisted x4 input is resolved from the existing Stage-E A/B report and the matching
`current_homr_request.json`; no SR is regenerated.
