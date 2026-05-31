# Historical Stage/Issue/Phase Naming Audit

Issue: #160

## Purpose

This audit records remaining `stage`, `issue`, and `phase` naming outside the production detector-route API. Its purpose is to help future readers distinguish durable runtime/config/API surface from historical provenance, compatibility shims, and subsystem-internal workflow wording.

This PR is documentation-only. It does not change detector behavior, detector thresholds, CNN scoring, NMS policy, evaluation targets, or pipeline output semantics.

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
git grep -n -E 'stage_e|Stage E|issue53|Issue53|Issue #53|phase|Phase|stage [A-Z]|Stage [A-Z]' \
  -- src tools configs tests docs experiments ':!logs' ':!*.json'
```

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

Historical Stage E names remain only for checkpoint compatibility and provenance. This audit extends that boundary to the broader repository instead of reopening detector behavior.

## Classification summary

| Category | Summary | Action in this PR |
| --- | --- | --- |
| historical provenance | Issue-specific checkpoint names, old diagnostic stages, training/evaluation source paths, and historical docs/experiments | Keep and document as intentional |
| user-facing wording | CLI/log/report text that says `Stage`, `Phase`, or old Issue names but is not a production config/API key | Do not rename in this PR; consider follow-up only when wording is actively confusing |
| production API/config surface | Current detector-route module/config keys and orchestrator-facing names | No behavior change here; #158 already moved the dense route production surface to semantic names |
| obsolete wrapper/tool | Legacy wrappers and old diagnostics that exist mainly for reproduction or historical comparison | Do not delete here; mark archive/deprecation candidates for a separate cleanup issue |

## Detailed inventory

### 1. Stage E full-pipeline checkpoint surface

Representative names:

- `tools/issue120/run_stage_e_full_pipeline.py`
- `tools/issue120/eval_stage_e_from_manifest.py`
- `tools/issue120/attach_stage_e_eval_contract.py`
- `configs/issue120_stage_e_full_pipeline.yaml`
- `docs/ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md`
- `issue141.stage_e_full_pipeline.v1`
- `logs/issue120_e2e_recovery/stage_e_full_pipeline/`

Classification: historical provenance.

Rationale:

- These names identify the #141/#156 canonical Stage E full-pipeline checkpoint and its reproducibility contract.
- The names are part of the checkpoint command/schema/log path vocabulary, not the new production detector-route API.
- Renaming them would require an explicit compatibility and migration plan.

Decision: keep as-is. New code should not introduce additional Stage E names unless it is explicitly checkpoint compatibility or provenance documentation.

### 2. `stage_e_dense_full_pipeline` compatibility shim

Representative names:

- `src/pipeline/detector_routes/stage_e_dense_full_pipeline.py`
- `StageEDenseRouteArtifacts`
- `STAGE_E_EXPECTED_PAGES`
- `load_stage_e_image_paths`
- `reconstruct_stage_e_dense_route`
- compatibility wrappers around historical `issue53_root` / `regenerate_issue53_candidates`

Classification: historical provenance / compatibility shim.

Rationale:

- This module preserves old import and artifact access paths for the Stage E checkpoint.
- The production implementation lives in `src.pipeline.detector_routes.dense_full_pipeline`.
- The shim is intentionally narrow and should not be used by new production code.

Decision: keep as-is. A future removal requires a compatibility plan and confirmation that no tracked checkpoint command still imports it.

### 3. Dense full-pipeline execution `phase` wording

Representative names:

- `_phase_summary`
- `phase_summaries`
- execution summary field `phases`
- phase names such as `load_route_image_paths`, `dense_candidate_reconstruction`, and `probe_rescue_candidate_reconstruction`

Classification: user-facing wording / internal workflow label.

Rationale:

- These names describe runtime substeps in the dense full-pipeline reconstruction summary.
- They are not historical `Stage A/B/C/D/E` names and do not encode old Issue numbers.
- Because execution summaries may be consumed by scripts or review notes, renaming is a schema-affecting change and should not be done inside this audit PR.

Decision: keep. If the execution summary schema becomes durable public API, create a follow-up issue to decide whether `phases` should remain generic step terminology or migrate to `steps`.

### 4. Historical Issue53 training/evaluation provenance

Representative names:

- Paths or comments referring to `logs/issue53_full_eval_rescue_v1`
- Historical CNN/detector training or evaluation configs that identify Issue53-derived rescue data
- Documentation that explains the origin of recovered dense/probe candidates

Classification: historical provenance.

Rationale:

- These names point at the origin of old model/data artifacts.
- Renaming them would make historical model lineage less clear and could break reproducibility notes.
- They should not be treated as current detector-route API.

Decision: keep. If any active production config still accepts `issue53_*` as a key, track it as a separate compatibility/removal issue; do not silently alias it.

### 5. Legacy Issue #120 Stage B/C/D diagnostics and Makefile targets

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

Classification: historical provenance, with some obsolete wrapper/tool candidates.

Rationale:

- These names preserve the Issue #120 recovery sequence and remain useful for reproducing or comparing diagnostic checkpoints.
- The Makefile targets are explicit Issue #120 maintenance commands, not general production API.
- Some wrappers may be candidates for archive or deprecation after Stage E checkpoint compatibility is no longer needed.

Decision: keep historical reports and commands needed for reproduction. For wrappers that are no longer used by any maintained command, create a separate archive/deprecation issue rather than deleting them in this audit PR.

### 6. HOMR evaluator `phase` wording

Representative names:

- HOMR evaluator phase logs
- HOMR integration comments that describe recognizer phases or timing segments
- Stage E reports that mention HOMR/SR/OMR-inclusive full-pipeline execution

Classification: user-facing wording / subsystem-internal workflow label.

Rationale:

- These phase labels belong to the HOMR/evaluator workflow and do not define detector-route API.
- They are useful as progress or timing markers.
- They should not be mixed with detector accuracy stages.

Decision: keep unless a future logging cleanup standardizes progress wording across all external recognizer integrations.

### 7. Downstream numbering pipeline Phase A/B/C labels

Representative names:

- Downstream measure-numbering reports or logs that use `Phase A`, `Phase B`, or `Phase C`.

Classification: user-facing wording.

Rationale:

- These labels describe downstream numbering/measure-count workflow, not detector candidate generation or detector-route API.
- Renaming can affect review notes, log parsing, or local debugging habits.
- Detector metrics must not be mixed with downstream measure-count metrics.

Decision: keep in this PR. A future wording cleanup may rename them to `numbering step` labels if the downstream UX is revised.

### 8. Historical experiments and refactor notes

Representative names:

- `experiments/` entries with `stage`, `phase`, `Issue53`, or old Issue #120 labels
- `docs/refactors/` notes that preserve prior design decisions or abandoned routes

Classification: historical provenance.

Rationale:

- These files are historical records, not current runtime/config surface.
- Renaming would obscure the context of old experiments and could make old commands harder to map back to their original issue.

Decision: keep. Archive only when the project adopts a broader experiment-retention policy.

## Follow-up candidates

These are intentionally not changed in this PR:

1. Decide whether dense route execution summary `phases` should remain the generic schema term or be renamed to `steps` under a versioned schema migration.
2. Review old Issue #120 diagnostic wrappers after Stage E checkpoint compatibility is no longer needed, and archive/delete only with an explicit reproduction impact check.
3. Review downstream numbering `Phase A/B/C` wording if the downstream command/report UX is revised.
4. Periodically rerun the grep inventory before large detector-route refactors and confirm no new production config/API keys use `stage_e`, `issue53`, or historical Issue names.

## Current guidance for future changes

- Do not introduce `stage_e` or `issue53` in new production detector-route code.
- Use `dense_full_pipeline`, `probe_rescue`, and semantic detector config keys for current runtime behavior.
- Keep Stage E names only when referring to the canonical checkpoint, historical logs, compatibility shims, or documentation of provenance.
- Keep Issue53 names only when referring to historical model/data lineage or compatibility views.
- Treat generic `phase` wording as acceptable for internal workflow/log segments unless it becomes a durable public schema or conflicts with detector-route naming.
- Do not rename checkpoint commands, log directories, or contract schemas without a migration layer.

## Verification notes

Documentation-only change.

Checks appropriate for this PR:

```bash
git diff --check
git grep -n -E 'stage_e|Stage E|issue53|Issue53|Issue #53|phase|Phase|stage [A-Z]|Stage [A-Z]' \
  -- src tools configs tests docs experiments ':!logs' ':!*.json'
```

Skipped checks:

- Python tests: not required because no Python behavior changed.
- GPU smoke: not required because no GPU, Docker, model loading, or runtime output behavior changed.
- Full evaluation: not required because detector thresholds, CNN scoring, NMS, evaluation target, and output semantics are unchanged.

## Result

The remaining historical Stage/Issue/Phase names are documented as provenance, compatibility, internal workflow wording, or future cleanup candidates. No production detector-route behavior is changed by this audit.
