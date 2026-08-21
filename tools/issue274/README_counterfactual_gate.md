# Issue #274 — final same-input counterfactual numbering gate

## Why v5 failed on 68/68 pages

`two_homr_full68_fresh_summary_v5.json` successfully established that the retained Issue #264 `_02` report is a valid post-PR #265 semantic-support run.  The baseline contract itself passed: 68 pages, 68 retained numbering artifacts, fresh current-HOMR semantic support on all pages, no historical detector artifact runtime input, and no non-index gate failures.

The mistake was the next step: v5 treated a **different production run** as a pixel-exact numbering reference.  The authoritative A/original staff segmentation is produced by HOMR and is not the variable Issue #274 is changing.  Between two independent runs its connected-component bbox can move or fragment by a few pixels.  Because v5 compared staff bboxes and measure bboxes exactly, every page was reported changed.

A structural audit of the v5 report gives the following split:

- 60/68 pages: active system grouping, staves-per-system, measure counts and measure-number sequences are identical; only serialized bbox coordinates differ;
- 5/68 additional pages: the active grouping/numbering structure is still identical and only zero-measure `empty_systems` segmentation differs;
- 3/68 pages have an active structural difference between the two independent runs:
  - `Shostakovich-Sym5-Va/page_005`: the `_02` A/staff mask splits one physical staff into two horizontal components, producing 9 active systems / 34 measures versus fresh 8 / 31;
  - `Shostakovich-Sym5-Va/page_012`: the `_02` final active system contains a horizontally fragmented extra staff component (3 extracted staves versus fresh 2), while measure numbering is unchanged;
  - `Va__Prokofiev_Symphony5/page_021`: the independent runs differ in whether one adjacent staff pair is grouped, shifting the later active-system numbering layout.

These observations are evidence that v5 is not a controlled Issue #274 comparison.  They are not sufficient evidence that any of the three pages is a two-HOMR regression because v5 changed both the detector-barline producer **and** the independently rerun A/staff geometry at once.

## Causal acceptance contract

`verify_two_homr_full68_counterfactual.py` fixes the comparison variable rather than weakening an exact comparator until it passes.

For each of the 68 canonical pages it takes the actual fresh #274 production inputs from that page's manifest and freezes:

1. the authoritative A/original staff mask;
2. the fresh post-PR #265 current-HOMR connector semantic support resolved from that staff path;
3. the fresh page image.

It then runs current CPU-only `MeasureNumberingPipeline` twice while changing exactly one input:

- control: retained accepted C/pinned-x4 detector barlines;
- candidate: the actual fresh two-HOMR accepted barlines recorded by the fresh manifest.

The gate has two mandatory links:

1. **reconstruction integrity:** the candidate CPU reconstruction must match the actual fresh serialized `numbering_base.json` exactly, excluding only `page_number` ordinal;
2. **causal topology equivalence:** with A geometry, connector semantics and image fixed, control and candidate must have identical serialized staff grouping (including staff bbox membership), measure-number sequences, and empty-system grouping on all 68 pages.

Measure bbox geometry differences between control and candidate are reported separately (exact and 2/5/10/15 px summaries).  They do not replace the topology gate.  Detector physical-event coverage remains a separate already-recorded mandatory gate.

This counterfactual reruns only deterministic CPU numbering.  It does not rerun HOMR, SR, detector inference, dense candidate generation, CNN, MMR or OCR.

## Semantic-artifact failure policy

The current numbering implementation no longer silently falls back when a resolved current-HOMR connector semantic bundle has a missing sibling staff mask or a staff-count mismatch.  Those conditions are artifact-contract violations and raise `RuntimeError`.

Therefore the counterfactual cannot hide a stale/mismatched semantic bundle by switching to A/Proxy geometry: such a page is recorded as an error and the gate fails.
