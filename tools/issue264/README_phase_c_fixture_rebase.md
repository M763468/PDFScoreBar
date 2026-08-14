# Issue #264 Phase C fixture rebase diagnostic

The post-#221 MMR fixtures identify expected rests by historical
`[page, system, measure]` indices. Current Phase A grouping can legitimately change
those indices while leaving the physical score region and the MMR result unchanged.

For Phase C acceptance, historical numbering artifacts are therefore used only as
evaluation geometry:

1. read the historical measure bbox referenced by each fixture;
2. map that bbox to the current Phase A measure occupying the same page region;
3. rewrite only the fixture's `[system, measure]` indices for scoring;
4. score the already-generated current `overrides_mmr.json` against the rebased fixture.

This does not make historical numbering a production runtime input. Detector, HOMR,
MMR CNN/OCR, SR and numbering are not re-executed by the rescoring command.

Example:

```bash
/opt/venv_pipeline/bin/python \
  tools/issue264/rescore_phase_c_mmr_geometry_rebased.py \
  --report logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02/phase_c_mmr_regression_report.json
```

Output:

```text
logs/issue264_phase_c_mmr_regression/issue264_phase_c_current_production_full68_02/phase_c_mmr_geometry_rebased_score_report.json
```

Any ambiguous or weak spatial mapping fails explicitly rather than silently changing
GT. The rebase must cover all 182 expected MMR fixtures before its accuracy metrics
can be used as the Phase C acceptance evidence.
