# Measure-numbering geometry scale contract

Issue #267 makes musical geometry decisions in the measure-numbering path
resolution-independent.

## Unit definition

`unit_size` is the staff-line spacing in the same coordinate frame as staff and
barline bounding boxes.

The production `StaffExtractor` estimates one page-level unit from the original
staff mask before its connected-component morphology:

1. for the page-wide estimate, find rows whose staff-mask foreground covers at least 25% of the mask width;
2. merge adjacent active rows into line runs;
3. measure adjacent run-center spacings;
4. compute the initial median spacing;
5. retain spacings between 0.5x and 1.5x that median;
6. use their mean and map it into the target/page coordinate frame.

This uses the same staff-line-spacing concept established by the canonical
`barline_staff_units.v1` work. If the conservative page-wide estimate is unavailable,
`StaffExtractor` retries the same spacing estimator inside each accepted component's
original-mask crop. This keeps short extractable systems from falling back to
post-morphology staff height without lowering the page-wide row-persistence gate.
A `Staff` carries the resolved unit internally.
The numbering JSON serializer deliberately does not expose this transient field.

For direct/synthetic `Staff` construction where no explicit unit is available,
numbering/grouping code uses `staff_height / 4` as a resolution-normalized
compatibility fallback. Production extraction should normally provide the
mask-derived unit.

## Normalized musical-geometry thresholds

| Location | Previous fixed threshold | Current rule |
| --- | ---: | ---: |
| `MeasureNumberer` barline X deduplication | 15 px | `1.2 * unit_size` |
| `MeasureNumberer` implicit system start | 50 px | `4.0 * unit_size` |
| `MeasureNumberer` minimum measure interval | 25 px | `1.0 * unit_size` |
| `SystemBuilder` aligned-barline X tolerance | 10 px | `0.4 * unit_size` |
| `SystemBuilder` connection ROI X margin | 2 px | `0.08 * unit_size` |
| `SystemBuilder` tiny inter-staff gap shortcut | 5 px | `0.2 * unit_size` |
| `SystemBuilder` absolute staff-overlap fallback | 10 px | `0.4 * unit_size` |

The SystemBuilder ratios preserve the previous nominal pixel behavior around the
accepted corpus scale of approximately 25 px per staff unit; they are not tuned
against page-specific outcomes.

Existing ratio-based logic remains ratio-based, including divisi/grouping staff
height ratios, connector density, ghost-start median/staff-height checks, and the
vertical morphology kernel derived from the actual inter-staff gap.

## Fixed-pixel operations intentionally retained

The following fixed pixel values are implementation details rather than musical
geometry acceptance thresholds and remain unchanged in this issue:

- `StaffExtractor.min_height=10` connected-component noise floor;
- `StaffExtractor` 20x1 dilation kernel;
- `StaffExtractor` 1x50 horizontal closing kernel;
- one-pixel BBox/index safety operations such as an implicit ghost-line width or
  ensuring a non-empty ROI;
- morphology minimum kernel sizes in connector-mask processing.

These operations affect raster implementation mechanics, not the logical
distance at which two barlines are considered the same measure boundary or the
logical distance used to infer system/measure structure. If future multi-DPI
evidence shows that one of these raster operations changes extracted staff
topology, it should be migrated as a separate morphology/segmentation change
with its own regression evidence.

MMR OCR crop/mask pixel geometry is outside Issue #267 scope.

## Validation contract

Resolution-independence tests cover equivalent 1x/2x geometry for:

- staff-unit estimation;
- barline deduplication;
- implicit starts;
- minimum measure width;
- aligned-barline grouping tolerance;
- small-gap connector handling;
- barline-to-staff overlap assignment.

The final acceptance check must additionally compare current accepted
numbering/physical-measure counts against the pre-#267 baseline. Unit tests alone
are not sufficient evidence that the new thresholds preserve the accepted
full-corpus counting contract.

For that final gate, replay the same retained accepted upstream inputs on
`develop` and the #267 candidate, then compare the resulting
`intermediate/page_*/numbering_base.json` signatures with:

```bash
python tools/issue267/compare_numbering_count_signatures.py \
  --baseline-run <develop-run-dir> \
  --candidate-run <issue267-run-dir> \
  --output logs/issue267/count_compare.json
```

Acceptance is based on physical-measure counting: `count_match=true` (also exposed
as the CLI-compatible `exact_match` alias), zero missing/added pages, identical
ordered per-system measure-count signatures, and a zero total physical-measure delta.
The comparator also reports `semantic_match` plus exact staff/measure/empty-system
geometry differences as diagnostics. Geometry-only drift such as a small BBox shift
is reviewable evidence but is not itself a count-regression failure.

### Local full-68 count-validation procedure

The #267 replay is intentionally downstream-only. It reuses:

- canonical retained detector barlines from
  `issue255_production_restore_full68_top_level_worker_01`;
- the accepted Issue #264 Phase-C `_02` Phase-A replay tree
  (`issue264_phase_c_current_production_full68_02/phase_a_hybrid_replay`),
  including fresh source-coordinate connector semantics;
- the retained evaluation2 page images.

It does **not** rerun detector inference, SR, HOMR, MMR CNN, or OCR.

Prepare a detached pre-#267 baseline worktree at
`6bef8bc0c74b2237ef5cda2e4e837c698eb90dde` and a candidate worktree, then run:

```bash
ARTIFACT_ROOT=/path/to/checkout-with-retained-data-and-logs
BASE_CODE_ROOT=/path/to/pre-267-worktree
CANDIDATE_CODE_ROOT=/path/to/issue267-worktree

PYTHON_BIN=/path/to/repo-python \
ARTIFACT_ROOT="$ARTIFACT_ROOT" \
BASE_CODE_ROOT="$BASE_CODE_ROOT" \
CANDIDATE_CODE_ROOT="$CANDIDATE_CODE_ROOT" \
bash "$CANDIDATE_CODE_ROOT/scripts/validate_issue267_numbering_counts.sh"
```

The wrapper refuses a baseline HEAD other than the recorded pre-#267 commit,
runs the same 68 retained inputs through both code roots, and writes:

- `baseline/intermediate/page_*/numbering_base.json`;
- `candidate/intermediate/page_*/numbering_base.json`;
- one replay provenance report for each side;
- `count_compare.json` with the physical-measure acceptance result plus exact semantic-geometry diagnostics.

The accepted Issue #264 `_02` replay directory must already exist under
`ARTIFACT_ROOT/logs/issue264_phase_c_mmr_regression/`. Do not silently
substitute a newly generated HOMR/support run for the final comparison, because
that would mix producer/runtime variation into the #267 geometry comparison.
