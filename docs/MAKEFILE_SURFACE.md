# Maintained Makefile Surface

The root `Makefile` is the supported repository entrypoint for everyday development,
validation, canonical runtime operations, and a small set of retained historical reproductions.
`make help` labels each entry by role. This inventory classifies every root target; Issue-specific
targets are retained for provenance and are not promoted as general workflows.

## Maintained user and developer entrypoints

| Target | Classification | Notes |
| --- | --- | --- |
| `help` | Maintained user entrypoint | Lists described root targets. |
| `run-pipeline` | Maintained runtime entrypoint | Uses the canonical image, interpreter, and `/workspace` bind mount from `ENVIRONMENTS.md`. |
| `docker-build` | Maintained runtime entrypoint | Builds the selected image without implicit cleanup. |
| `docker-clean`, `docker-clean-full` | Maintained runtime helpers | Container removal and explicit image removal remain separate. |
| `setup-local-worktree-links` | Maintained developer helper | Delegates to `scripts/setup_local_worktree_links.sh`. |
| `promote-log` | Maintained developer helper | Promotes a run into an existing retained log category. |
| `repo-tree` | Maintained developer helper | Optional overview; requires the external `tree` command. |
| `issue-post-mortem` | Maintained Issue workflow helper | Review completed Issue work and preserve relevant disposition/provenance. |
| `visual-diff` | OMR visual inspection helper | Collects recent debug images for visual review. |
| `clean-artifacts`, `clean-logs` | Maintained cleanup helpers | `clean-logs` is limited to documented category roots and protects retained directories. |
| `format` | Maintained code helper | Applies Ruff formatting and fixes. |

## Maintained validation and evaluation

| Target | Classification | Notes |
| --- | --- | --- |
| `lint`, `test-fast`, `test` | Maintained validation | `test-fast` is lightweight; `test` runs all `tests/`. |
| `run-smoke`, `verify-pipeline-smoke`, `verify-gpu-smoke` | Maintained validation | Production pipeline checks; see `ENVIRONMENTS.md` and `dev/VALIDATION_POLICY.md`. |
| `verify-service-readiness-smoke`, `verify-service-readiness-container` | Maintained validation | One-job service-readiness container checks. |
| `verify-full-eval` | Maintained opt-in evaluation | Long-running full evaluation wrapper. |
| `local-pr-validation` | Maintained validation helper | Delegates to `scripts/local_pr_validation.sh`. |
| `check-makefile` | Maintained static validation | Checks literal repository path references in root Makefile recipes. |

## Retained Issue-specific reproduction targets

These are kept because their evaluator, fixture, or regeneration steps support the Issue #120
historical contract. Their defaults may require operator-held data, models, Docker, or GPU assets.

| Targets | Classification | Implementation |
| --- | --- | --- |
| `eval-issue120-full` | Issue #120 reproduction | `tools/issue120/eval_full68_from_intermediates.py` and provenance tool |
| `verify-issue120-stage-b`, `verify-issue120-stage-b-native` | Issue #120 reproduction | Stage-B scorer/evaluator; Docker or host Python route |
| `regen-issue120-stage-d-upstream`, `verify-issue120-stage-d` | Issue #120 reproduction | Stage-D generation and Stage-C verifier |
| `summarize-issue120-stage-d`, `compare-issue120-stage-d-boxes` | Issue #120 reproduction | Drift and box-statistics analysis tools |

Stage-E targets remain available, but were removed from the root help surface because their
contract is confined to Issue #120. Invoke them explicitly with:

```bash
make -f tools/issue120/Makefile.stage_e.mk <target>
```

The historical `run-smoke-sr` alias is retained as a deprecated compatibility target and points
to `run-smoke`.

## Removed stale targets

- `check-consistency` referenced the absent `tools/check_repo_consistency.py`; no current repository
  contract requires that manifest/freshness checker. `check-makefile` now guards the narrower,
  verifiable Makefile contract instead.
- `setup-worktree` referenced an absent helper script. Worktree creation is available through Git
  and is not given a misleading Make target until a maintained workflow exists.

## Reference-check contract

`tools/check_makefile_references.py`, exposed as `make check-makefile`, scans literal references to
repository scripts, source, configs, and tests in recipes. It checks the root Makefile and the
standalone Issue #120 Stage-E Makefile. It intentionally ignores variable-expanded paths and
operator data/model paths, whose availability depends on the local environment. The PR validation
workflow runs it automatically. Run `make help` alongside it when changing targets or their
descriptions.
