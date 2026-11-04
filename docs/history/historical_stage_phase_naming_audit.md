# Historical Stage/Issue/Phase Naming Audit

Issue: #160

## Purpose

This audit records the boundary between the canonical full-pipeline runtime surface and historical Stage/Issue/Phase names retained only for validation, reproduction, or provenance.

The goal is not to document historical names in place and accept them everywhere. The goal is to keep the main pipeline understandable without knowing the Issue #120/#141 Stage E recovery history, while still preserving a replay path for historical checkpoints.

## Current boundary

Canonical runtime surface:

- `src/pipeline/main.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/detection/*`
- `src/pipeline/detector_routes/dense_full_pipeline.py`
- `configs/dense_full_pipeline.yaml`

Historical / validation / reproduction surface:

- `tools/issue120/*`
- `configs/issue120_stage_e_full_pipeline.yaml`
- `docs/ISSUE*_*.md`
- compatibility shims retained for historical checkpoint replay

A reader should be able to understand normal full-pipeline execution from `src/pipeline/main.py` and canonical config files without knowing the Stage E recovery sequence.

## Scope

Primary target areas for the inventory:

- `src`
- `tools`
- `configs`
- `tests`
- `docs`
- `experiments`

Excluded areas:

- `logs`
- generated artifacts
- large result artifacts
- transient local output
- JSON result files unless they are tracked contract/schema examples that intentionally preserve reproducibility metadata

The canonical local refresh command is:

```bash
git grep -i -n -E 'stage_?e|stage [a-z]|issue ?#? ?53|issue53|phase' \
  -- src tools configs tests docs experiments ':!logs' ':!*.json'
```

## Changes made for #160

This issue moves the repository closer to that boundary with small, low-risk changes:

1. `src/pipeline/main.py` keeps generic pipeline-entrypoint wording. The production entrypoint comment no longer refers to a Stage E-specific caller.
2. `configs/dense_full_pipeline.yaml` provides a canonical dense full-pipeline config for `src.pipeline.main`.
3. `configs/issue120_stage_e_full_pipeline.yaml` remains as the historical Issue #120/#141 Stage E reproduction config.
4. This audit now treats historical naming as something to isolate from the canonical surface, not merely annotate.

## Existing detector-route boundary from #158

Issue #158 already separated the production dense detector-route API from Stage E / Issue53 historical naming. New production detector-route code should use semantic dense-route names such as:

- `src.pipeline.detector_routes.dense_full_pipeline`
- `reconstruct_dense_full_pipeline_route`
- `DenseRouteArtifacts`
- `probe_rescue_root`
- `regenerate_probe_rescue_candidates`
- `detection.precomputed_probe_candidates_root`
- `detection.cnn_bands_from`
- `detection.probe_use_original_images`

Historical Stage E names should remain only for checkpoint compatibility and provenance.

## Classification summary

| Category | Summary | Action in this PR |
| --- | --- | --- |
| canonical runtime surface | Full pipeline entrypoint, orchestrator, detection package, current dense-route config | Keep Stage/Issue-specific names out |
| historical reproduction surface | Issue #120/#141 checkpoint commands/config/docs and old diagnostic stages | Keep, but isolate under tools/docs/historical config |
| compatibility shim | Old import or artifact views retained only for checkpoint replay | Keep narrow; do not use in new production code |
| generic workflow wording | Non-historical `phase` wording used as local workflow/progress terminology | Allowed only when it does not encode historical Stage/Issue meaning |
| obsolete wrapper/tool | Legacy diagnostics that exist mainly for reproduction or comparison | Track for separate archive/deprecation work |

## Detailed inventory and decisions

### 1. Canonical full-pipeline entrypoint

Representative files:

- `src/pipeline/main.py`
- `src/pipeline/orchestrator.py`
- `src/pipeline/detection/*`
- `configs/dense_full_pipeline.yaml`

Classification: canonical runtime surface.

Decision:

- Use semantic pipeline and detector terminology.
- Do not mention `Stage E`, `Issue120`, or `Issue53` in normal entrypoint comments, CLI help, or canonical config names.
- Historical names may still appear in artifact paths supplied by a user config, but they should not define the current API.

### 2. Stage E full-pipeline checkpoint surface

Representative names:

- `tools/issue120/run_stage_e_full_pipeline.py`
- `tools/issue120/eval_stage_e_from_manifest.py`
- `tools/issue120/attach_stage_e_eval_contract.py`
- `configs/issue120_stage_e_full_pipeline.yaml`
- `docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`
- `issue141.stage_e_full_pipeline.v1`
- `logs/issue120_e2e_recovery/stage_e_full_pipeline/`

Classification: historical reproduction surface.

Decision:

- Keep these names only as Issue #120/#141 reproduction and validation vocabulary.
- Do not treat `tools/issue120/run_stage_e_full_pipeline.py` as the canonical full-pipeline implementation.
- The tool may prepare historical inputs, collect runtime summaries, attach evaluation contracts, and call `src.pipeline.main.run_pipeline`; it should not define the canonical naming policy.

### 3. `stage_e_dense_full_pipeline` compatibility shim

Representative names:

- `src/pipeline/detector_routes/stage_e_dense_full_pipeline.py`
- `StageEDenseRouteArtifacts`
- `STAGE_E_EXPECTED_PAGES`
- `load_stage_e_image_paths`
- `reconstruct_stage_e_dense_route`
- compatibility wrappers around historical `issue53_root` / `regenerate_issue53_candidates`

Classification: compatibility shim.

Decision:

- Keep as a narrow checkpoint replay surface.
- New production code should import `src.pipeline.detector_routes.dense_full_pipeline` directly.
- Future deletion requires a compatibility plan and confirmation that no maintained historical replay command imports it.

### 4. Dense full-pipeline execution `phase` wording

Representative names:

- `_phase_summary`
- `phase_summaries`
- execution summary field `phases`
- phase names such as `load_route_image_paths`, `dense_candidate_reconstruction`, and `probe_rescue_candidate_reconstruction`

Classification: generic workflow wording.

Decision:

- Keep for now because these names describe runtime substeps and do not encode `Stage A/B/C/D/E` or an old Issue number.
- If the execution summary schema becomes durable public API, decide separately whether `phases` should migrate to `steps` under a versioned schema migration.

### 5. Historical Issue53 training/evaluation provenance

Representative names:

- Paths or comments referring to `logs/issue53_full_eval_rescue_v1`
- Historical CNN/detector training or evaluation configs that identify Issue53-derived rescue data
- Documentation that explains the origin of recovered dense/probe candidates

Classification: historical provenance.

Decision:

- Keep where the name identifies historical model/data lineage.
- Do not use `issue53_*` as a new production config/API key.
- Active production config keys must use semantic names; removed detector-route keys should fail rather than silently alias.

### 6. Legacy Issue #120 Stage B/C/D diagnostics and Makefile targets

Representative names:

- `ISSUE120_STAGE_B_*`
- `ISSUE120_STAGE_D_*`
- `verify-issue120-stage-b`
- `verify-issue120-stage-b-native`
- `regen-issue120-stage-d-upstream`
- `verify-issue120-stage-d`
- `summarize-issue120-stage-d`
- `compare-issue120-stage-d-boxes`
- tools under `tools/issue120/` that mention Stage B/C/D diagnostics

Classification: historical reproduction surface / obsolete wrapper candidates.

Decision:

- Keep historical reports and commands needed for reproducibility.
- Do not use these targets as examples for new production naming.
- Create a separate archive/deprecation issue before deleting wrappers that may still be useful for checkpoint replay.

### 7. HOMR evaluator `phase` wording

Representative names:

- HOMR evaluator phase logs
- HOMR integration comments that describe recognizer phases or timing segments
- Stage E reports that mention HOMR/SR/OMR-inclusive full-pipeline execution

Classification: generic workflow wording or historical documentation, depending on location.

Decision:

- Keep subsystem-internal phase labels when they are plain progress/timing terminology.
- Do not mix those labels with detector recovery Stage names.

### 8. Downstream numbering pipeline Phase A/B/C labels

Representative names:

- Downstream measure-numbering reports or logs that use `Phase A`, `Phase B`, or `Phase C`.

Classification: generic workflow wording.

Decision:

- Keep in this PR because it is downstream workflow wording, not detector candidate-generation history.
- Consider a future wording cleanup if the downstream user-facing UX is revised.

### 9. Historical experiments and refactor notes

Representative names:

- `experiments/` entries with `stage`, `phase`, `Issue53`, or old Issue #120 labels
- `docs/refactors/` notes that preserve prior design decisions or abandoned routes

Classification: historical provenance.

Decision:

- Keep as historical records.
- Archive only under a broader experiment-retention policy.

## Current guidance for future changes

- Run normal full-pipeline work through `src.pipeline.main` and canonical configs.
- Add new general-purpose configs under semantic names, not Issue/Stage names.
- Keep Stage E names only under Issue #120/#141 reproduction, historical docs, or explicit compatibility shims.
- Keep Issue53 names only for historical model/data lineage or compatibility views.
- Treat generic `phase` wording as acceptable only when it means a local workflow segment rather than a historical recovery stage.
- Do not rename checkpoint commands, log directories, or contract schemas without a migration layer.

## Follow-up candidates

These are intentionally not completed in this PR:

1. Decide whether dense route execution summary `phases` should remain the generic schema term or migrate to `steps` under a versioned schema migration.
2. Review old Issue #120 diagnostic wrappers after Stage E checkpoint compatibility is no longer needed, and archive/delete only with an explicit reproduction impact check.
3. Review downstream numbering `Phase A/B/C` wording if the downstream command/report UX is revised.
4. Periodically rerun the grep inventory before large detector-route refactors and confirm no new production config/API keys use `stage_e`, `issue53`, or historical Issue names.

## Verification notes

Checks appropriate for this PR:

```bash
git diff --check
git grep -i -n -E 'stage_?e|stage [a-z]|issue ?#? ?53|issue53|phase' \
  -- src tools configs tests docs experiments ':!logs' ':!*.json'
```

Local checkout-based checks were not run in this environment because `git clone` could not resolve `github.com`. GPU smoke and full evaluation were not run because this change is a naming-boundary/configuration cleanup and does not intentionally change detector thresholds, CNN scoring, NMS policy, or output semantics.

## Result

The canonical full-pipeline entrypoint remains `src.pipeline.main`, with a semantic dense full-pipeline config available for normal use. Historical Stage/Issue names are retained for reproduction and provenance, but they are explicitly isolated from the canonical runtime surface.
