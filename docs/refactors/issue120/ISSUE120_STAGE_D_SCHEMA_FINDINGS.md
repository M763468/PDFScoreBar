# Issue 120 Stage D Payload Schema Findings

## Purpose

This note records the first payload-schema inspection for #147.

It should be read with:

```text
docs/refactors/issue120/ISSUE120_STAGE_D_DRIFT_RECOVERY.md
```

## Input roots inspected

Initial regenerated-source inspection:

```text
historical = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
baseline   = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline
hybrid     = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate
omr_sr     = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_omr_sr
sr         = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_sr
first_available = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_first_available
```

Issue #36 candidate-source inspection:

```text
historical    = logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
issue36_probe = logs/issue36_prep/probe_candidates_filtered_v12
baseline      = logs/issue120_e2e_recovery/stage_d_upstream_regen/bands_from_candidate_baseline
```

All inspected roots resolved the canonical 68-page manifest:

```text
resolved=68
missing=0
```

## Regenerated-source summary

```text
label            median item count   median width   median height   score keys
historical       315.0               4.0            107.0           0
baseline         123.0               1.0             97.75          0
hybrid            54.0               7.0            105.5           0
omr_sr            88.0               2.0            105.0           0
sr                63.0               7.0            105.0           0
first_available   54.0               7.0            105.5           0
```

Schema observations:

- historical payloads are list payloads with list boxes;
- baseline/hybrid/omr_sr/first_available also resolve as list-box payloads;
- sr resolves as list payloads with `orig_bbox`, `pred_bbox`, `staff_index`, and `system_index` item keys;
- none of the inspected roots have `score` keys in the sampled candidate files;
- therefore the primary difference is not scored-vs-unscored schema;
- the primary observed difference is candidate density and, secondarily, box width/source-family differences.

## Issue #36 candidate-source finding

The local Issue #36 candidate root exists and matches the historical root at the inspected schema/statistics level:

```text
label          resolved  missing  median item count  median width  median height  score keys
historical     68        0        315.0              4.0           107.0          0
issue36_probe  68        0        315.0              4.0           107.0          0
baseline       68        0        123.0              1.0            97.75         0
```

The sampled pages show identical counts and median dimensions between historical and `issue36_probe`, while regenerated `baseline` remains sparse. Examples:

```text
Shostakovich-Festival_Overture_Va/page_001: historical 269, issue36_probe 269, baseline 89
Shostakovich-Festival_Overture_Va/page_006: historical 277, issue36_probe 277, baseline 89
Shostakovich-Sym5-Va/page_007:              historical 367, issue36_probe 367, baseline 71
Shostakovich-Sym5-Va/page_011:              historical 336, issue36_probe 336, baseline 93
```

The box-tree comparison between historical and `issue36_probe` is also exact at the inspected statistic level:

```text
pages=68
nonzero_count_delta=0
all_count_ratio=1.0
max_abs_median_h_delta=0.0
max_abs_median_w_delta=0.0
max_abs_median_cx_delta=0.0
max_abs_median_cy_delta=0.0
```

## Interpretation

The initial file-family mismatch hypothesis should be narrowed:

```text
Not supported:
  historical is scored dict payloads while regenerated roots are raw box lists.

Supported:
  historical is a much denser unscored candidate/box root than any current regenerated Stage D source.

New finding:
  historical scoring_input_eval2_v12 and logs/issue36_prep/probe_candidates_filtered_v12 are equivalent at the inspected schema/statistics level.
```

The most likely Stage D gap is now:

```text
Issue #36 dense probe candidate-generation path
  -> copied/renamed/scored as Issue #44 scoring_input_eval2_v12
  -> used by Issue #53/#57 probe rescue

current Stage D sparse upstream-detector composition path
  != that dense candidate-generation path
```

The current regenerated roots are structurally valid and schema-compatible enough to be consumed, but they do not reproduce the dense candidate volume of `scoring_input_eval2_v12`.

## Historical-code clue

PR #57 / Issue #53 used:

```text
logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12
```

as `bands_from` for probe-rescue candidate generation.

Issue #44 docs identify the older candidate source family:

```text
logs/issue36_prep/probe_candidates_filtered_v12
```

The Issue #44 workflow says the CNN training candidate JSONs were from this older candidate family, while later scoring/evaluation configs were fixed to use `scoring_input_eval2_v12` as the scored/evaluated root.

This shifts #147 from current HOMR/SR/OMR detector-output composition toward recovering the Issue #36 dense probe-candidate producer.

## Next diagnostic questions

1. Were `scoring_input_eval2_v12` candidate files copied directly from `logs/issue36_prep/probe_candidates_filtered_v12`?
2. What script/config produced `probe_candidates_filtered_v12`?
3. Can that producer be rerun against the current 68-page evaluation2 images?
4. Does rerunning that producer reproduce the historical dense candidate root exactly or within acceptable drift?
5. If not, which parameter or upstream input causes candidate-density drift?

## Recommended local command

First verify byte-level identity between the historical root and Issue #36 candidate root:

```bash
python3 - <<'PY'
import hashlib
from pathlib import Path

left = Path('logs/cnn_barline_classification/issue44_baseline_v1/scoring_input_eval2_v12')
right = Path('logs/issue36_prep/probe_candidates_filtered_v12')
filename = 'pipeline2_no_peak_candidates.json'

left_files = sorted(left.rglob(filename))
missing = []
mismatch = []
for lf in left_files:
    rel = lf.relative_to(left)
    rf = right / rel
    if not rf.exists():
        missing.append(str(rel))
        continue
    lh = hashlib.sha256(lf.read_bytes()).hexdigest()
    rh = hashlib.sha256(rf.read_bytes()).hexdigest()
    if lh != rh:
        mismatch.append(str(rel))

print(f'left_files={len(left_files)}')
print(f'missing={len(missing)}')
print(f'mismatch={len(mismatch)}')
if missing:
    print('missing sample:', missing[:10])
if mismatch:
    print('mismatch sample:', mismatch[:10])
PY
```

Then search for the producer of the Issue #36 candidate root in local shell history, run logs, and repository history:

```bash
grep -R "probe_candidates_filtered_v12\|issue36_prep" -n \
  docs tools configs experiments src .github \
  2>/dev/null | tee logs/issue120_e2e_recovery/issue36_candidate_producer_grep.txt
```

If `logs/issue36_prep` contains run configs or inventories, inspect:

```bash
find logs/issue36_prep -maxdepth 3 -type f \
  \( -name '*config*' -o -name '*.yaml' -o -name '*.json' -o -name '*.txt' -o -name '*.md' \) \
  | sort | tee logs/issue120_e2e_recovery/issue36_prep_metadata_files.txt
```

Generated grep/list outputs must remain under ignored `logs/` paths.
