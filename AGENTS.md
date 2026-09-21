# AGENTS.md

Repository-specific guidance for AI agents and human-assisted development.

Keep this file limited to durable PDFScoreBar rules. Task-specific plans, current branch state,
container state, run tags, and issue handoff notes do not belong here.

## 1. Resolve the active task from current evidence

- Treat the latest user instruction as the active scope.
- For changing facts, verify the current Issue/PR, repository source/tests, and Git state instead of
  trusting an older chat, handoff, generated graph, or historical document.
- Use older Issues and history documents only when they materially explain a contract, regression
  guard, accepted result, or design lineage for the current task.
- When sources disagree, prefer current source/tests and the latest authoritative record for the same
  target. Preserve superseded results as history rather than averaging them with corrected results.

## 2. Work autonomously inside the authorized scope

- Once implementation, validation, or PR creation is authorized, carry the task through without
  repeated confirmation loops.
- Ask for approval only when a destructive or irreversible operation is not already implied by the
  task, such as deleting user data, force-updating shared history, removing retained datasets/models,
  or merging a PR.
- Do not expand the implementation beyond the requested task. Report unrelated improvements
  separately.
- Investigation-only requests should remain read-only unless the user or active task explicitly
  authorizes implementation.

## 3. Branch and GitHub policy

- Normal feature, fix, refactor, documentation, and performance work branches from `develop` and
  opens a PR to `develop`; `main` is the stable/release branch. See `docs/BRANCH_POLICY.md` when
  creating or changing branches or PRs.
- Use a topic branch. Do not merge to `develop` or `main` automatically.
- An Issue is useful when the task is Issue-driven, but repository maintenance does not require
  inventing an Issue solely to satisfy an agent workflow.
- When creating a PR, follow `.github/pull_request_template.md`. Use `N/A` for Related Issue when
  there is genuinely no Issue.

## 4. Environment and command selection

- Read `docs/ENVIRONMENTS.md` when the task will run Docker, GPU, models, datasets, the full
  pipeline, or another environment-sensitive command. Do not require it for unrelated docs or
  static repository edits.
- Prefer maintained Makefile targets and existing scripts when they fit the task, but inspect current
  source/help before assuming a target, container name, interpreter path, or local mount is current.
- If GPU, Docker, dataset, model, sandbox, or network constraints block a check, report the attempted
  check and exact reason. Do not treat a blocked check as a pass.
- Keep large datasets, model artifacts, caches, and generated evaluation output out of git unless an
  explicit retention policy says otherwise.
- Keep issue-scoped generated logs and retained artifacts under one issue root:
  `logs/issue<N>/<purpose-or-run>/...`. Do not create new sibling roots such as
  `logs/issue<N>_foo` and `logs/issue<N>_bar` for the same Issue. Preserve existing historical
  directories unless a deliberate migration is needed; do not rewrite old evidence solely for cleanup.

## 5. Validation

- Use `docs/dev/VALIDATION_POLICY.md` to choose validation based on changed behavior and risk.
- Run the smallest checks that establish the relevant contract, then add smoke/full evaluation only
  when the change category requires it.
- Do not impose universal `make format`, `make lint`, GPU smoke, or full-evaluation gates on changes
  for which the validation policy says they are irrelevant.
- Add or update tests when behavior changes. For docs-only or metadata-only work, state why runtime
  tests are not applicable.
- Before reporting completion, record commands/checks run, pass/fail status, and any skipped or
  deferred validation with the reason.

## 6. Evaluation and experiment invariants

For performance, detector, evaluation, model/runtime, or replacement investigations:

- treat the user/Issue acceptance criteria, primary metrics, target dataset, and required regression
  gates as the evaluation contract for that run;
- do not redefine success after seeing results: switching the primary metric, narrowing the dataset,
  excluding failing cases, changing tolerance/seed/filter/config, or introducing a compensating
  threshold change creates a new experiment and does not erase the original result;
- report every originally required gate and any regression even when another metric improves; never
  describe accuracy/quality as preserved unless the agreed regression gates actually pass;
- compare candidates on equivalent inputs before making causal performance claims;
- record enough provenance to reproduce material results: source/candidate commit, runtime/model
  identity, fixed inputs/config, command, and retained log/artifact path;
- keep production behavior unchanged until the candidate passes the required correctness gate;
- treat silent fallback or unknown runtime provenance as invalid evidence;
- do not compensate for a component change by silently retuning unrelated thresholds;
- reuse retained outputs for corrected rescoring when the outputs remain valid instead of rerunning
  expensive inference solely because an evaluation harness was wrong;
- validate the semantic downstream contract when geometry/grouping changes; raw count or byte
  equality alone may be insufficient;
- prefer `unit_size` or another documented resolution-normalized unit for new geometric thresholds
  unless the relevant contract explicitly requires pixel coordinates.

If the evaluation contract itself must change, state the proposed change and reason explicitly. Keep
the result under the old contract visible, and obtain user/Issue approval before treating the new
contract as the authoritative pass/fail criterion.

## 7. Skills and auxiliary agents

- Repository skills are optional helpers, not a mandatory routing layer.
- Do not invoke a skill merely to read an Issue/PR, summarize a diff, create a PR, update docs,
  generate tests, inspect dependencies, or report status when the task can be handled directly.
- Use a repository skill only when its narrow, project-specific workflow materially improves the
  result.
- Graphify is an optional navigation aid for complex cross-module dependency/call-path questions.
  Direct source/tests remain authoritative. Do not install, refresh, or rebuild Graphify merely
  because a code question was asked.
- Cross-model consultation (Codex/Gemini or other agents) is optional. Do not delegate by default,
  and do not create consultation logs or lessons solely to satisfy an agent workflow.

## 8. Documentation and durable history

- Keep durable design contracts and accepted experiment history in the repository or authoritative
  Issue/PR record; keep transient plans and action queues out of general project documentation.
- `docs/HISTORY_INDEX.md`, when present, is a navigation layer only. Read only the history lineage
  relevant to the active task.
- Do not treat `docs/ai-workflow/LESSONS.md`, old Issue notes, or generated Graphify output as current
  repository state without checking current source/tests.

## 9. Completion report

For non-trivial work, report:

- what changed and why;
- validation performed and its result;
- checks skipped/deferred and the reason;
- experiment/evaluation provenance when relevant;
- remaining risks or decisions;
- external actions taken, such as created/updated Issues or PRs.
