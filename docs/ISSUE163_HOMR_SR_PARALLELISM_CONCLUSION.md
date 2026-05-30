# Issue 163 HOMR/SR overlap experiment conclusion

Issue: #163

This document is the develop-branch record for the Issue #163 experiment conclusion. It intentionally records the result without adopting the experimental runtime code.

## Branch handling

- Experimental branch retained for reproduction: `perf/issue163-homr-sr-route-parallelism`
- Final experimental evidence commit: `0bf863c01d304c53820de88bfc44939fc7dcc04d`
- Develop adoption scope: docs only

The experimental runner, config overlays, and Make targets remain on the experimental branch. They are not adopted into `develop` by this docs-only conclusion.

## Final decision

Do not adopt HOMR/SR route or phase overlap scheduling as the default Stage E behavior.

Rejected modes:

- `baseline_sr_subprocess_overlap`
- `inprocess_sr_prep_baseline_overlap`

Default sequential HOMR baseline followed by HOMR SR remains the recommended canonical behavior.

No follow-up adoption issue should be created from the current evidence.

## Evidence summary

### Route-level subprocess overlap

This mode ran HOMR baseline and HOMR SR as separate subprocess routes.

Result:

- canonical detector contract preserved
- total runtime: 9764.83 sec
- pipeline runtime: 9704.30 sec
- HOMR overlap experiment duration: 9368.13 sec
- HOMR baseline subprocess duration: 5438.08 sec
- HOMR SR subprocess duration: 9368.13 sec
- peak GPU memory: 6780 MB
- peak process-tree RSS: 7525986304 bytes

Decision: rejected because it substantially regressed runtime and GPU memory.

### Granular in-process phase overlap, full Stage E

This mode overlapped HOMR baseline full route with SR image preparation only, then ran SR HOMR inference after both phases completed.

Result:

- canonical detector contract preserved
- total runtime: 7736.00 sec
- pipeline runtime: 7673.71 sec
- HOMR granular experiment duration: 7309.15 sec
- HOMR baseline full route: 2198.31 sec
- HOMR SR preparation: 2747.39 sec
- HOMR SR inference: 4561.69 sec
- peak GPU memory: 4332 MB
- peak process-tree RSS: 5814255616 bytes

Decision: rejected as an adoption candidate. It removed most of the subprocess regression, but did not improve runtime relative to the accepted sequential reference.

### Local HOMR-only A/B/C mechanism-isolation experiment

The local A/B/C experiment used a fixed 10-image subset and stopped after HOMR baseline/SR output generation.

| Condition | Runner mode | Meaning |
| --- | --- | --- |
| A | `default_sequential` | existing HOMR baseline, then existing HOMR SR route |
| B | `phase_split_sequential` | baseline full route, then SR preparation only, then SR HOMR inference |
| C | `phase_split_overlap` | baseline full route overlapped with SR preparation, then SR HOMR inference |

All conditions reported `image_count=10`.

| Metric | A default | B phase-split sequential | C phase-split overlap |
| --- | ---: | ---: | ---: |
| total runtime | 1215.02 sec | 1217.86 sec | 1234.45 sec |
| baseline duration | 279.96 sec | 281.30 sec | 383.47 sec |
| SR full route | 935.05 sec | n/a | n/a |
| SR preparation | n/a | 190.34 sec | 454.67 sec |
| SR inference | n/a | 746.22 sec | 779.69 sec |
| peak GPU memory | 4715 MB | 4712 MB | 5400 MB |
| peak process-tree RSS | 5279535104 bytes | 5540466688 bytes | 5762867200 bytes |

Interpretation:

- A and B were effectively equivalent for runtime.
- Phase splitting alone did not improve runtime.
- C was slower than both A and B.
- C increased peak GPU memory by about 688 MB compared with B.
- C overlapped baseline and SR preparation mechanically, but both phases slowed under overlap, so contention erased the expected benefit.

Decision: no adoption and no further A/B/C experiment.

## Reproduction reference

Use the experimental branch and final evidence commit:

```bash
git fetch origin
git checkout perf/issue163-homr-sr-route-parallelism
git reset --hard 0bf863c01d304c53820de88bfc44939fc7dcc04d
```

The local A/B/C runner added on that branch is:

```text
tools/issue163/run_homr_phase_mode_experiment.py
```

The fixed 10-image subset used for the final A/B/C run was:

```text
data/evaluation2/images/Shostakovich-Festival_Overture_Va/page_003.png
data/evaluation2/images/Shostakovich-Festival_Overture_Va/page_006.png
data/evaluation2/images/Va__Prokofiev_Symphony5/page_009.png
data/evaluation2/images/Va__Prokofiev_Symphony5/page_010.png
data/evaluation2/images/Shostakovich-Sym5-Va/page_012.png
data/evaluation2/images/Shostakovich-Sym5-Va/page_004.png
data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_004.png
data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_009.png
data/evaluation2/images/Va_Prokofiev_Symphony1/page_002.png
data/evaluation2/images/Va_Prokofiev_Symphony1/page_005.png
```

Create the subset file:

```bash
mkdir -p logs/issue163_homr_phase_abcs_clean
cat > logs/issue163_homr_phase_abcs_clean/image_subset.txt <<'EOF'
data/evaluation2/images/Shostakovich-Festival_Overture_Va/page_003.png
data/evaluation2/images/Shostakovich-Festival_Overture_Va/page_006.png
data/evaluation2/images/Va__Prokofiev_Symphony5/page_009.png
data/evaluation2/images/Va__Prokofiev_Symphony5/page_010.png
data/evaluation2/images/Shostakovich-Sym5-Va/page_012.png
data/evaluation2/images/Shostakovich-Sym5-Va/page_004.png
data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_004.png
data/evaluation2/images/Sibelius-Violin_Concerto-Viola/page_009.png
data/evaluation2/images/Va_Prokofiev_Symphony1/page_002.png
data/evaluation2/images/Va_Prokofiev_Symphony1/page_005.png
EOF
```

Run the A/B/C comparison:

```bash
make run-issue163-homr-phase-abcs \
  ISSUE163_HOMR_PHASE_ABCS_IMAGE_LIST=logs/issue163_homr_phase_abcs_clean/image_subset.txt \
  ISSUE163_HOMR_PHASE_ABCS_OUTPUT=logs/issue163_homr_phase_abcs_clean
```

Expected evidence files:

```text
logs/issue163_homr_phase_abcs_clean/A_default_sequential/runtime_summary.json
logs/issue163_homr_phase_abcs_clean/A_default_sequential/resource_samples.summary.json
logs/issue163_homr_phase_abcs_clean/A_default_sequential/homr_phase_mode_summary.json

logs/issue163_homr_phase_abcs_clean/B_phase_split_sequential/runtime_summary.json
logs/issue163_homr_phase_abcs_clean/B_phase_split_sequential/resource_samples.summary.json
logs/issue163_homr_phase_abcs_clean/B_phase_split_sequential/homr_phase_mode_summary.json

logs/issue163_homr_phase_abcs_clean/C_phase_split_overlap/runtime_summary.json
logs/issue163_homr_phase_abcs_clean/C_phase_split_overlap/resource_samples.summary.json
logs/issue163_homr_phase_abcs_clean/C_phase_split_overlap/homr_phase_mode_summary.json
logs/issue163_homr_phase_abcs_clean/C_phase_split_overlap/homr_route_parallel_experiment_summary.json
```

Generated files under `logs/` are evidence artifacts and must not be committed.

## Follow-up direction

Future runtime work should not continue with route/phase overlap scheduling unless new evidence changes the resource profile. If Stage E runtime remains a priority, use separate issues focused on:

- SR image/cache reuse across repeated Stage E attempts.
- Avoiding unnecessary repeated image copy/preparation work in the Stage E runner.
- Reducing redundant HOMR preparation work while preserving output layout and provenance.
- Page chunking only if it preserves cache behavior and stays below resource limits.
