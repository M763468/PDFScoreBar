# Issue 120 Stage D 12-Page Drift Findings

## Purpose

This note records the remaining #147 drift after near-exact Issue #36 v12 regeneration.

Read with:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_PRODUCER_FINDINGS.md
docs/refactors/issue120/ISSUE120_STAGE_D_PROVENANCE_CHECKLIST.md
```

## Current reproduction status

Issue #36 GT-prep v12 regeneration with the historical summary parameters gives a close but not exact reproduction:

```text
historical_raw      files=68 total=27758
repro_raw           files=68 total=27445
historical_filtered files=68 total=22565
repro_filtered      files=68 total=22335
```

Byte comparison:

```text
historical_raw vs repro_raw
  left_files=68 missing=0 mismatch=12

historical_filtered vs repro_filtered
  left_files=68 missing=0 mismatch=12
```

The same 12 pages mismatch in raw and filtered outputs, so the remaining drift starts in raw candidate generation, not final filtering.

## Mismatch pages

```text
Shostakovich-Festival_Overture_Va/page_001
Shostakovich-Sym5-Va/page_004
Shostakovich-Sym5-Va/page_005
Shostakovich-Sym5-Va/page_008
Shostakovich-Sym5-Va/page_012
Shostakovich-Sym5-Va/page_013
Sibelius-Violin_Concerto-Viola/page_004
Va_Prokofiev_Symphony1/page_004
Va__Prokofiev_Symphony5/page_002
Va__Prokofiev_Symphony5/page_003
Va__Prokofiev_Symphony5/page_009
Va__Prokofiev_Symphony5/page_021
```

## Drift shape

The mismatches are mostly near-identical boxes with small y-boundary changes. Examples:

```text
Shostakovich-Sym5-Va/page_008:
  historical: (275, 1161, 279, 1263)
  repro:      (275, 1161, 279, 1264)

Shostakovich-Sym5-Va/page_012:
  historical: (510, 1893, 514, 1992)
  repro:      (510, 1891, 514, 1991)

Va__Prokofiev_Symphony5/page_002:
  historical: (531, 2237, 535, 2347)
  repro:      (531, 2237, 535, 2345)

Va__Prokofiev_Symphony5/page_021:
  historical: (703, 1782, 707, 1891)
  repro:      (703, 1779, 707, 1889)
```

Some pages also lose candidates without replacement:

```text
Shostakovich-Sym5-Va/page_005 raw:
  left=317 right=295 missing_from_repro=22 extra_in_repro=0

Va__Prokofiev_Symphony5/page_003 raw:
  left=549 right=519 missing_from_repro=30 extra_in_repro=0
```

This points to row-stat band resolution or `detect_probe_scan` implementation drift rather than final-filter drift.

## Input metadata check

All 12 mismatch pages have inventory inputs with mtimes on 2026-01-31, before the v12 generation window on 2026-02-12.

The checked fields are:

```text
image
staff_mask
hybrid_predictions
run_dir
```

The final two pages also show pre-v12 input mtimes:

```text
Va__Prokofiev_Symphony5/page_009
  image:              2026-01-31T02:40:15
  staff_mask:         2026-01-31T11:38:37
  hybrid_predictions: 2026-01-31T11:43:49
  run_dir:            2026-01-31T11:43:49

Va__Prokofiev_Symphony5/page_021
  image:              2026-01-31T02:40:19
  staff_mask:         2026-01-31T12:31:53
  hybrid_predictions: 2026-01-31T12:37:11
  run_dir:            2026-01-31T12:37:11
```

There is currently no evidence that the 12-page drift is caused by post-v12 input-file modification.

## Working conclusion

The remaining exact-reproduction boundary is most likely one of:

1. `detect_probe_scan` implementation drift between the v12 generation commit window and current code;
2. environment-level drift such as OpenCV / numpy behavior;
3. input drift not visible from mtime/hash alone, although current evidence does not support this.

The next diagnostic should run the Issue #36 v12 generation command using the historical commit implementation, starting with commit:

```text
edf7bf6 GT seeds: switch probe generation default to row_stats (v9)
```

If the historical commit reproduces byte identity, the remaining boundary is implementation drift.

If it does not, compare row-stat band boundaries on one high-drift page, for example:

```text
Va_Prokofiev_Symphony1/page_004
Va__Prokofiev_Symphony5/page_009
```

## Routing decision

If historical implementation reproduces the exact v12 root:

```text
Stage-D exact reconstruction requires the historical Issue #36 probe-detector behavior.
```

If historical implementation remains near-but-not-exact:

```text
Stage-D reconstruction is provenance-complete enough to proceed to detector-level scoring/evaluation, while byte identity remains an environment/input boundary.
```

Detector-level metrics must remain separate from downstream measure-count metrics.
