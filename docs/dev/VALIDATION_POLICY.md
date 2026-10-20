# Validation Policy

This document defines how to choose validation for local automation and manual PR work. It is intentionally stricter than a simple optional helper script: automation should make skipped validation visible and should detect scope drift early.

## Principles

- Match validation to the changed behavior, not to the convenience of the runner.
- Start with lightweight checks, then add smoke or full evaluation when the diff can affect runtime behavior.
- A skipped check is acceptable only when the reason is recorded.
- Evaluation-sensitive changes require either supporting evaluation artifacts or an explicit human decision to skip or defer evaluation.
- Web or cloud-only edits are not final validation for GPU, Docker, dataset, or full pipeline behavior.
- Before an evaluation-sensitive run, identify the acceptance criteria, primary metrics, target dataset/input set, and regression gates that determine PASS/FAIL.
- Do not change those criteria after observing results and then describe the original run as passing. A post-result metric/dataset/config/tolerance/seed/filter change is a new evaluation unless the original contract explicitly allowed it.
- Report regressions against the original contract even when an alternate metric improves.

## Change type matrix

| Change type | Minimum validation | GPU smoke | Full evaluation | Required report fields |
| --- | --- | --- | --- | --- |
| Docs only | `git diff --check` and local review of touched links/commands | Not required | Not required | Changed docs, reason, skipped checks |
| Shell scripts / Makefile | `bash -n` for touched scripts, `make help`, relevant `--help` or metadata-only command | Required if Docker/GPU/pipeline commands are invoked or changed | Not required unless evaluation flow changes | Command, exit code, log path |
| Python utility | Targeted pytest or import/compile check plus `make test-fast` when applicable | Required if the utility loads models, data, Docker, GPU, or pipeline code | Usually not required | Test list and skipped checks |
| Engine contract / service boundary | PR `engine-contract` gate plus `make test-fast`; add `make verify-service-readiness-smoke` when executor/container/public artifact wiring changes | Required only when the production GPU/model path is exercised or changed | Not required for contract/serialization/artifact-gate-only changes; required by the affected accuracy policy when numerical behavior changes | Contract version, affected public surfaces, commands, skipped checks |
| Pipeline / detector / orchestrator | `make test-fast` plus targeted tests | Required | Required when behavior, candidate generation, routing, or outputs can change; otherwise explicitly skip with reason | Commit, config, input data, log path, risk |
| Docker / GPU / model loading | Syntax/build check where practical plus `make verify-gpu-smoke` | Required | Required if runtime output or evaluation behavior may change | Environment, image/container, command, log path |
| Evaluation config / metric / threshold / seed / dataset selection | Static diff review plus targeted command that reads the config | Required when local pipeline is affected | Required by default, or human-approved skip/defer | Original contract, changed contract if any, config/data, metric impact, commit, log path |
| Baseline / canonical target | Reproduction command plus comparison artifact | Required when pipeline is involved | Required by default | Baseline, candidate, per-gate delta, PASS/FAIL under the original contract, log path |
| Dependency / build configuration | Relevant install/build/smoke check | Required if GPU/Docker/runtime stack is affected | Depends on affected behavior; document decision | Changed files, environment, failure mode risk |

For the v1 engine boundary, see [`ENGINE_SERVICE_READINESS.md`](../ENGINE_SERVICE_READINESS.md)
for the clean container smoke and its separation from production accuracy evidence.

## Validation status and evidence

Use one row per check in PRs and completion reports. A report-level tested revision/environment
may cover multiple rows when identical. Record the following four statuses explicitly:

| Status | Meaning for the current attempt |
| --- | --- |
| Passed / 今回実行して成功 | The check ran to completion and its acceptance condition passed. |
| Failed / 今回実行して失敗 | The check ran and reported a test/assertion or acceptance failure. |
| Blocked / 実行できず | A prerequisite, permission, environment, or launcher failure prevented completion. Test results remain unknown or partial. |
| Not run / 未実行 | The check was not attempted; explain why it was skipped or deferred. |

A nonzero launcher exit alone does not establish a test failure. For example, failure to open
`artifacts/test_fast.log` before pytest starts is **Blocked**, not a failing test suite.
If tests partially ran before an environment failure, record the partial counts and retain
Blocked for the incomplete check. Never infer success from an existing log file.

For every attempted check, record:

- The tested commit (`git rev-parse HEAD`), or the base commit plus an identified uncommitted
  diff (for example, a retained patch and its digest). If files changed after a check, state
  whether that check still covers the final diff and why; rerun when affected behavior changed.
- The exact command, working directory, and relevant environment: host interpreter or Docker
  image ID, container, and checkout mount. Record configuration/inputs when relevant.
- Status, exit code when available (otherwise explain why), and a log/artifact path or concise
  output. For Blocked, include the attempted command, concrete error, and alternative checks
  completed with their limits. For Not run, include the reason and any follow-up needed.

Historical results belong in a separate paragraph labeled **Historical evidence** with the
original revision, environment, command and evidence reference when available. Explicitly
state that they were not rerun for the current change; missing provenance remains unknown.
A previous commit, another worktree, CI, or another environment passing does not establish a
current rerun. Preserve separate attempts when a blocked check is later retried successfully.

Before execution, follow the [environment preflight](../ENVIRONMENTS.md#execution-preflight)
to avoid selecting unavailable tools or testing a different checkout.

Example (illustrative only; these rows are not actual validation results):

Tested target: commit `<sha>` plus retained `logs/issue<N>/validation/<run>/changes.patch`
(SHA-256 `<digest>`). Working directory: `/workspace` in `<container>`, image `<image-id>`,
with the active worktree mounted there.

| Check | Current status | Command / evidence |
| --- | --- | --- |
| Focused pytest | Passed | `docker exec -w /workspace -e PYTHONPATH=/workspace <container> /opt/venv_pipeline/bin/python -m pytest tests/test_python_env.py`; exit 0, `<run>/pytest.log`. |
| Fast tests | Blocked | `docker exec -w /workspace <container> make test-fast PYTHON=/opt/venv_pipeline/bin/python`; exit 2, `artifacts/test_fast.log: Permission denied` before pytest started. Focused pytest above covers only its selected module. |
| GPU smoke | Not run | Docs-only change; no runtime behavior changed. |

Historical evidence: fast tests passed on `<older-sha>` in `<other-environment>`
(command and log: `<reference>`); not rerun successfully for the current target.
If an assertion fails during a completed run, record **Failed** and its failure summary.

## Evaluation contract integrity

For any run used to justify an accuracy, quality, compatibility, or performance claim:

1. Record the contract before interpreting the result: acceptance criteria, primary metrics, dataset/input scope, thresholds/tolerances, seed when relevant, baseline/canonical target, and required regression gates.
2. Evaluate the candidate against that contract on equivalent inputs.
3. Report every required gate, not only the metrics that improved.
4. If a required gate fails, the run is a failure under that contract. Do not rename the goal, switch to a more favorable metric, drop failing cases, narrow the dataset, or retune unrelated thresholds and then describe the original result as preserving accuracy.
5. If evidence shows the original contract or harness was wrong, preserve the old result, explain the defect, define the corrected contract, and run or rescore a clearly labeled new evaluation. The corrected result supersedes the old one only for the corrected contract; it does not retroactively make the old run a pass.

## Sensitive change detection

Local validation scripts should inspect the diff and report categories. At minimum, the following paths or terms are sensitive:

- `configs/`
- `src/pipeline/`
- `tools/issue120/`
- `experiments/`
- `Dockerfile`
- `requirements.txt`
- `pyproject.toml`
- `Makefile`
- files or diffs mentioning `threshold`, `seed`, `dataset`, `metric`, `evaluation`, `baseline`, `canonical`, `filter`, `detector`, `orchestrator`, or `route`

A sensitive match does not always mean the PR is wrong. It means the report must explain which stronger checks were run or why they were skipped.

## Local full evaluation authorization

Full evaluation remains a human-controlled validation level, but once the user or issue explicitly authorizes it, local automation may start it without asking again for that PR. The resulting report must include the command, commit, config/data inputs, exit status, and log path.

## PR summary expectations

A non-trivial PR or validation comment should include:

- Changed files and intent.
- Detected change categories.
- Required validation according to this policy.
- Commands actually run.
- Log paths and exit codes.
- Required or recommended checks that were skipped, with exact reason.
- For evaluation-sensitive work: original evaluation contract, baseline, candidate result, per-gate deltas, and PASS/FAIL without substituting alternate success criteria.
- Remaining risks and any human decisions still needed.
