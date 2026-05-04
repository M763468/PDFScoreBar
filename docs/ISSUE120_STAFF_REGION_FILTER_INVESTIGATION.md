# Issue 120 Staff Region Filter Investigation

## Scope

This investigation follows Prompt 1 in
`docs/ISSUE120_NEXT_SESSION_HANDOFF_PROMPTS.md`.

No implementation or config changes were made. The work only traced existing artifacts and
recorded a narrow verification proposal.

Generated artifacts:

- `logs/issue120_e2e_recovery/staff_region_filter_investigation/trace_examples.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_filter_summary.md`

## Findings

The current CNN-stage staff overlap filter is effectively disabled.

- Config sets `staff_vov_threshold: 0.0` in
  `configs/evaluation2_e2e_verification_full_v12_restore.yaml`.
- `src/pipeline/steps/filters.py::filter_by_staff_overlap` keeps a candidate when
  `max_vov >= vov_threshold`.
- With threshold `0.0`, any valid bbox is kept, including boxes with zero vertical overlap.

The seed-stage and CNN-stage staff filters are different mechanisms.

- `candidate_filter_kwargs.min_staff_overlap_ratio` is a pixel overlap check against a
  staff mask inside `filter_probe_candidates`.
- In this v12 restore config, seed generation applies that check with
  `min_staff_overlap_ratio: 0.02`.
- Main pass2 probe scan sets `enable_heuristic_filters: false`, so this candidate filter
  does not protect pass2 scan candidates.
- CNN scoring does not use the injected staff mask directly in this run. It receives
  `bands_from=probe_seeds` and rebuilds vertical bands from seed boxes.

## Trace Summary

All 29 provisional `fp_out_of_staff` rows were traced.

| item | count |
| --- | ---: |
| total `fp_out_of_staff` rows | 29 |
| seed-stage origin | 23 |
| pass2-scan-only origin | 6 |
| rows still present in filtered CNN JSON | 29 |
| rows attributed to disabled CNN staff filter | 29 |

By score:

| score | count |
| --- | ---: |
| `Shostakovich-Sym5-Va` | 16 |
| `Sibelius-Violin_Concerto-Viola` | 8 |
| `Va__Prokofiev_Symphony5` | 3 |
| `Va_Prokofiev_Symphony1` | 2 |

Representative rows:

| score/page | bbox | origin | CNN score | seed mask overlap | CNN band VOV |
| --- | --- | --- | ---: | ---: | ---: |
| `Shostakovich-Sym5-Va/page_003` | `[871, 3436, 875, 3508]` | seed | 0.846945 | 0.000000 | 0.361111 |
| `Shostakovich-Sym5-Va/page_007` | `[1794, 381, 1798, 447]` | seed | 0.887104 | 0.000000 | 0.454545 |
| `Shostakovich-Sym5-Va/page_009` | `[778, 1092, 782, 1154]` | pass2 scan | 0.826356 | 0.000000 | 1.000000 |
| `Sibelius-Violin_Concerto-Viola/page_004` | `[912, 1138, 916, 1210]` | seed | 0.996044 | 0.072917 | 0.500000 |
| `Va__Prokofiev_Symphony5/page_008` | `[2686, 2981, 2690, 3054]` | pass2 scan | 0.996812 | 0.000000 | 1.000000 |

The trace indicates that simply enabling a CNN-stage VOV threshold may not be enough:
22 of the 29 rows already have `cnn_band_max_vov >= 0.5` against the current seed-derived
bands. This points to permissive or mislocalized seed-derived bands for many examples, not
only a disabled threshold.

## Narrow Verification Proposal

Do not repeat the rejected `staffcov_v1` broad sweep.

Instead, run a replay-only experiment over existing `pipeline2_no_peak_scored.json` outputs:

1. Rebuild the current CNN-stage seed-derived bands exactly as `cnn_scoring.py` does.
2. Apply VOV thresholds `0.0`, `0.1`, `0.25`, and `0.5` to scored candidates.
3. Regenerate filtered candidate JSONs under a new `logs/` experiment directory.
4. Run the existing full 68-page measure-count KPI.
5. Accept no setting unless the current best `abs_delta_sum=4` does not worsen.

If this replay worsens count KPI, the next investigation should focus on only the six
pass2-scan-only `fp_out_of_staff` rows and on why seed-derived bands are broad enough to
cover visually outside-staff candidates.

## Follow-up: Staff Recognition, Local Distribution, and FN Risk

Additional diagnostics were generated after reviewing the remaining unknowns:

- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_recognition_replay_summary.md`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_vov_replay_summary_by_page.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/staff_vov_replay_dropped_predictions.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/gt_staff_band_diagnostics.csv`
- `logs/issue120_e2e_recovery/staff_region_filter_investigation/fp_out_of_staff_local_context.csv`

### How Staff Is Recognized

There are two different "staff" concepts in this run:

- Seed filtering uses injected HOMR `debug_3_staff.png` line masks with
  `candidate_filter_kwargs.min_staff_overlap_ratio`.
- Main pass2 probe scan and CNN-stage VOV filtering use seed-derived row-stat bands rebuilt
  from `probe_seeds`, not direct staff-region masks.

This distinction matters because the injected mask is a line-like staff mask, while the
CNN-stage VOV bands are median vertical ranges inferred from seed boxes. A candidate can
look outside the real staff while still overlapping a seed-derived band.

### How Overlap Is Judged

The CNN-stage filter computes only vertical overlap:

```text
overlap = min(box_y2, band_y2) - max(box_y1, band_y1)
vov = max(0, overlap) / candidate_height
keep if max_vov >= staff_vov_threshold
```

It does not check horizontal staff-mask pixels, and at the current threshold `0.0` it keeps
all valid boxes.

The direct line-mask pixel overlap is not a safe replacement. On all 3581 GT boxes:

| condition | count |
| --- | ---: |
| `debug_3_staff` pixel overlap `< 0.02` | 3235 |
| `debug_3_staff` pixel overlap `== 0` | 3220 |
| `debug_3_staff` mask-band VOV `< 0.25` | 2676 |
| `debug_3_staff` mask-band VOV `< 0.5` | 3140 |

This indicates that the raw line mask is not a reliable "inside staff region" test for
thin GT/predicted barline boxes without first converting it into robust staff-region bands.

### Distribution Around `fp_out_of_staff`

For the 29 visually/provisionally outside-staff FP rows:

| check | count |
| --- | ---: |
| seed-mask pixel overlap `< 0.02` | 23 |
| seed-mask pixel overlap `== 0` | 23 |
| seed-derived CNN band VOV `< 0.1` | 0 |
| seed-derived CNN band VOV `< 0.25` | 2 |
| seed-derived CNN band VOV `< 0.5` | 7 |
| nearest GT within 40 px | 26 |
| local FN near the FP | 2 |

So the apparent outside-staff FPs are usually close in X to a GT barline, but vertically
misaligned or on a neighboring/non-staff line. They are not remote random detections.

### What Happens If The Current VOV Filter Is Tightened

Replay over all 68 pages using current seed-derived bands:

| threshold | delta TP | delta FP | delta FN | dropped predictions | dropped base TP | dropped `fp_out_of_staff` |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.1 | -5 | -1 | +5 | 6 | 5 | 0 |
| 0.25 | -15 | -3 | +15 | 21 | 15 | 2 |
| 0.5 | -46 | -14 | +46 | 69 | 46 | 7 |

This confirms that a broad VOV threshold on current seed-derived bands is not count-safe.
It removes some FPs, but it also removes true matched predictions.

Representative FN-increase examples:

| threshold | score/page | dropped TP | matched GT | seed-band VOV | note |
| ---: | --- | --- | --- | ---: | --- |
| 0.25 | `Shostakovich-Sym5-Va/page_006` | `[911, 2990, 913, 3086]` | `[917, 2985, 921, 3082]` | 0.229167 | true barline; seed band covers only lower part |
| 0.25 | `Sibelius-Violin_Concerto-Viola/page_006` | `[1552, 4072, 1563, 4178]` | `[1556, 4072, 1560, 4175]` | 0.245283 | true barline; seed band too short/mispositioned |
| 0.5 | `Va__Prokofiev_Symphony5/page_002` | multiple GT-matched predictions | GT indices 0-4 | 0.018-0.064 | seed band is near only the lower edge of the true GT boxes |

The FN increase is therefore not evidence that GT is outside staff. It shows that the
current staff representation used for filtering is sometimes wrong or too narrow for real
GT barlines.

### Updated Conclusion

The remaining outside-staff-looking FP problem is not solved by simply enabling the current
CNN-stage VOV filter. The current filter uses seed-derived vertical bands that often overlap
the FP and sometimes fail to cover true GT-matched barlines. The next safe direction is to
derive a robust staff-region representation first, then replay it against both:

- all visually outside-staff FP, and
- all GT/TP boxes that would become FN.
