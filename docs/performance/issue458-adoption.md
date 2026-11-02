# Issue 458: production-code integration decision

The owner approved integrating resource-bounded source concurrency into the
production code path in [PR467 comment6578962019](https://github.com/M763468/PDFScoreBar/pull/467#issuecomment-6578962019).
The measured deployment may explicitly select two workers using the
[environment-specific configuration](issue458-source-concurrency.md).
The common production and smoke settings remain **one worker**. Worker count,
validated count, threads and resource envelope remain configurable; no GPU-specific
worker count is hardcoded into scheduling.

The exact-shape/error-policy example is not a common configuration for every
user. Comprehensive operational fail-safe selection/rejection, resource budgets,
timeouts and coordination with other settings are separate design work. This PR
preserves explicit pre-start serial selection/rejection, timeout/cancellation
and no-silent-retry behavior without redesigning the configuration system.
Rollback restores the generic one-worker block for a fresh job; a failed run
retains its diagnosis and is never silently rerun or marked successful.

## Acceptance evidence and retained limits

The original 4.900958% result remains Failed under its original >=5% gate.
The independent [reassessment](issue458-reassessment.md) measured 8.45% median
reduction with four improving pairs and tested semantic/correction/resource/
failure contracts. Those results support the owner's integration decision;
no new performance experiment or full68 was requested or run for this finishing
change. Root performance, other hardware/shapes, physical VRAM-exhaustion recovery
and full68 remain unverified. Allocator-budget OOM is a separate verified case.

## Integration and CI corrections

Latest develop `08788cb2d6e1eb32890f10eb78cb17d278f32f86` was merged without
rewriting the feature branch. Its incoming changes were documentation/metadata;
application source, production configuration, models and build dependencies are
unchanged from the tested feature source.

The distribution manifest now includes `source_concurrency.py`, which is imported
even by the generic serial path. Its missing entry would otherwise leave the
minimal package without a required module. The maintained-contract group now
classifies `tests/test_issue458_source_concurrency.py`. The exact distribution
contains 118 files, including 89 under src. Both Japanese architecture documents
translate the concurrency additions and record the current English source hashes;
no translation or repository-surface gate was disabled.

Local tested commit: `9e3720e313d44e31474b3f66e1d7aae8509c477e` (the same
application/manifest/translation diff as this report commit). Working directory:
manager `.worktrees/issue458`; host Python is the inspected classifier venv.
Source-focused tests use inspected image5311cf22… in the shared container,
manager mounted at /workspace, matching nested PYTHONPATH and UID1000/GID1001.

| Check | This attempt | Command / evidence under logs/issue458/adoption-integration |
| --- | --- | --- |
| Surface before correction | Failed | python3 tools/check_repository_surface.py; validation/surface-before.log; module/import/test classification errors |
| Surface after correction | Passed | same command, exit0; runtime closure includes the new module |
| Translation provenance | Passed | python3 tools/verification/check_doc_translations.py; 19 files, matching current original SHA-256 |
| Lint/format | Passed | make lint; validation/lint.log; exit0,1216 files formatted |
| Makefile references | Passed | make check-makefile; validation/makefile.log; exit0 |
| Release/translation tests | Passed | python3 -m pytest tests/test_release_candidate.py tests/test_doc_translations.py -q; validation/release-translations.log; 32 passed +4 subtests, exit0 |
| Source scheduling guards | Passed | docker exec --user1000:1001 -w /workspace/.worktrees/issue458 -e PYTHONPATH=/workspace/.worktrees/issue458 pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python -m pytest tests/test_issue458_source_concurrency.py -q; validation/source-focused.log; 17 passed, exit0 |
| Two independent static distribution candidates | Passed | release_candidate.py create with frozen source/main SHAs outside source checkout; materialize_distribution.py check --git-checkout; cmp candidate-a.json candidate-b.json; validation/candidate-*.json; identical commit/tree and 118 shipped files |
| Candidate-local module import | Passed | import src.pipeline.detection.source_concurrency from candidate cwd, verify __file__ is inside candidate; validation/candidate-import.log |
| Initial candidate launcher attempts | Blocked, corrected | source-local output and mutable refs rejected by tool contract; corrected to /tmp + full 40-character SHAs before successful static checks |
| New GPU/E2E/full68 runs | Not run | no numerical/runtime behavior changes; existing experiment evidence retained, lightweight packaging/provenance checks cover this diff |

The static candidates are validation-only independent repositories: their reports
have release_accepted:false. No main promotion or service deployment is performed.
Remote CI status is verified on the pushed PR head and reported in the PR/Issue;
Ready/merge remains a separate decision after green CI.
