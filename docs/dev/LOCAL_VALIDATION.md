# Local validation environments

[日本語](LOCAL_VALIDATION.ja.md)

Choose an environment that can run the required check against the active issue worktree.
Use this guide with the validation levels in [Validation Policy](VALIDATION_POLICY.md). A tool
or container observed previously is a lead to verify, not a guarantee that it still exists or
is compatible. Keep production images and containers used by other worktrees intact.

## Environment selection and preflight

| Environment | Use | Verify before use |
| --- | --- | --- |
| Host shell | Git provenance, Markdown/shell checks, GitHub CLI, Docker launch | Required command exists; host Python alone does not establish that pytest or project dependencies are installed. |
| Persistent Python validation container | Repository pytest and Python checks | Running container, immutable image ID, `/workspace` bind source, issue files visible, interpreter and pytest available. |
| Production GPU image | Maintained pipeline/GPU validation through repository Make targets | Use `make verify-gpu-smoke` and its source/image/asset preflight; this image intentionally does not provide pytest or browser tooling. |
| Browser runner | Node/Playwright/Chromium acceptance checks | Browser image, Playwright module, Chromium executable, network route to the server, read-only source mount and writable evidence mount. |

For environment-sensitive checks, establish these facts before execution and include them in
the evidence:

1. The tested worktree path, branch, commit, and dirty diff on the host.
2. The selected Python executable or immutable Docker image ID and container.
3. The actual bind mount and path to the tested files inside the container. Do not infer the
   source from the host working directory or container name.
4. The executing UID/GID and write access to each output directory and existing log.
5. Availability of Docker, `gh`, and any sandbox permission needed by the command. If an
   authorized route is denied, record the exact command and error and use another available
   environment when possible.

For pipeline use, additionally resolve the image against the active worktree and run the
production preflight described in [Environment & Tooling](ENVIRONMENTS.md). A tool
availability probe is not a passed application acceptance test. Report the actual check as
Passed, Failed, Blocked, or Not run under the [evidence rules](VALIDATION_POLICY.md#validation-status-and-evidence).

## Worktree and mount contract

Keep the manager checkout on its current task. Create normal issue worktrees beneath its
`.worktrees/` directory, from the current `origin/develop`. Set `ISSUE_ID` to the target
numeric Issue number in the shell before running the commands; the examples do not prompt:

```bash
# Run from the manager checkout.
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  manager_root="$(git rev-parse --show-toplevel)"
  git fetch origin develop
  mkdir -p "$manager_root/.worktrees"
  git -C "$manager_root" worktree add \
    -b "fix/issue${ISSUE_ID}" \
    "$manager_root/.worktrees/issue${ISSUE_ID}" origin/develop
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

Use an unused path and branch; resume an existing worktree instead of recreating it. Add a
purpose suffix only when simultaneous worktrees for one Issue are needed. Do not mechanically
move existing worktrees, active experiments, or frozen release candidates. A dedicated
candidate container that mounts its candidate directly at `/workspace` remains an explicit
exception.

The standard shared Python container mounts the manager checkout at `/workspace`; therefore
`<manager-checkout>/.worktrees/issue<issue-id>` appears at
`/workspace/.worktrees/issue<issue-id>`. Confirm the actual source and nested path before use:

```bash
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  manager_root="$(git rev-parse --show-toplevel)"
  issue_root="$manager_root/.worktrees/issue${ISSUE_ID}"
  container_issue="/workspace/.worktrees/issue${ISSUE_ID}"
  docker inspect pdfscore_pipeline_pytest_dev \
    --format '{{.Image}} {{json .Mounts}}'
  docker exec pdfscore_pipeline_pytest_dev \
    test -f "$container_issue/AGENTS.md"
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

[`scripts/docker_container_preflight.sh`](../../scripts/docker_container_preflight.sh) is
intentionally for a dedicated container whose active checkout is mounted directly at
`/workspace`. It rejects a nested issue worktree. For the shared layout, verify the manager
bind source, nested files, and import path with the commands above; do not weaken the script's
direct-mount check. A linked worktree's `.git` file contains an absolute host path, so Git
commands inside the container need an explicit mapping to the worktree's administrative
directory under the manager checkout's `/workspace/.git`. Record branch and commit on the
host; do not rewrite the host `.git` pointer.

`.worktrees/` is ignored by Git and excluded from Docker build context. For an older manager
checkout that does not yet have these tracked ignore rules, use its local
`.git/info/exclude` until the rule is available. Do not include nested issue source in image
builds.

## Python and pytest

Use the persistent Python validation container for pytest when it is available and mounted to
the manager checkout. Run checks as the host UID/GID so generated files remain editable by
the host user. Do not use `scripts/docker_container_preflight.sh` for the nested layout above.

From the issue worktree on the host:

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
manager_root="$(dirname "$git_common_dir")"
issue_root="$PWD"
issue_relative="$(realpath --relative-to="$manager_root" "$issue_root")"
container_issue="/workspace/$issue_relative"
git rev-parse HEAD
docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}} {{json .Mounts}}'
docker exec --user "$(id -u):$(id -g)" \
  -w "$container_issue" -e PYTHONPATH="$container_issue" \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest --version
```

### Git-dependent pytest suites

The nested worktree's `.git` pointer is a host path and cannot be followed inside the shared
container. Run suites that invoke Git from a disposable clone that has its own `.git`
directory, placed under the issue log root so that it is visible through the `/workspace`
mount:

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
manager_root="$(dirname "$git_common_dir")"
clone="logs/issue${ISSUE_ID}/pytest-clone/$(git rev-parse --short HEAD)"
git clone -q --no-hardlinks . "$clone"
container_clone="/workspace/$(realpath --relative-to="$manager_root" "$PWD/$clone")"
docker exec --user "$(id -u):$(id -g)" \
  -w "$container_clone" -e PYTHONPATH="$container_clone" -e HOME=/tmp \
  pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest \
  tests/test_docker_runtime_contract.py tests/test_distribution_surface.py \
  tests/test_release_candidate.py tests/test_doc_translations.py
```

`git clone` stops if the path already exists; delete a previous clone only after checking that
it is the disposable clone. The clone contains only committed `HEAD` content, so commit (or make
a temporary WIP commit of) the changes under test first and report the tested commit. Remove
the clone when the run is finished.

Do not pass `GIT_DIR` or `GIT_WORK_TREE` to pytest. These variables override `git -C <dir>`
and are inherited by every subprocess, so fixtures that run `git init`, `git config`,
`git add -f -A`, or `git commit` in a temporary directory would write into the mapped worktree:
its branch receives a commit containing untracked and ignored files, and the shared
`.git/config` receives `core.worktree` and test `[user]` values (#513). `tests/conftest.py`
and `tools/release_candidate.py` therefore drop the variables listed by
`git rev-parse --local-env-vars`; a run that relies on them cannot resolve the issue worktree
and fails instead. If the manager `.git` directory is not visible under the inspected
`/workspace` mount, use a host runner with the required dependencies. Do not report a
Git-dependent suite as passed based only on `pytest --version` or a test run without Git
access.

#### Detecting and recovering from leaked fixture writes

Runs that followed the earlier `GIT_DIR`/`GIT_WORK_TREE` instructions may have changed the
checkout. Check the shared configuration and the recent commits of each affected branch:

```bash
git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
common_config="$git_common_dir/config"
git config --file "$common_config" --get-all core.worktree
git config --file "$common_config" --get-regexp '^user\.'
git log -5 --format='%h %an <%ae> %s' <branch>
git -C "$(dirname "$git_common_dir")" rev-parse --show-toplevel
```

Signs of contamination are a `core.worktree` entry in the shared config (the manager checkout's
`--show-toplevel` then points at another worktree), `[user]` values such as
`Distribution test` / `distribution-test@example.invalid` or `Release tests` /
`release-tests@example.invalid`, and commits such as `fixture candidate` by those identities.
To recover, after confirming that each value was not set intentionally (the fixture replaces
an existing repository-level `[user]` value, so restore that value instead of unsetting it if
the checkout had one):

```bash
git config --file "$common_config" --unset-all core.worktree
git config --file "$common_config" --unset user.name
git config --file "$common_config" --unset user.email
# On the affected branch, only while the fixture commit is unpublished and is HEAD:
git reset --mixed HEAD~1
```

`git reset --mixed` removes the commit and keeps its files in the working tree, so files that
were untracked or ignored before the run become untracked or ignored again. If the commit has
already been pushed, revert it instead of rewriting shared history.

Read the maintained `FAST_TESTS` list from the issue worktree's Makefile, then invoke pytest
directly with the container interpreter:

```bash
mapfile -t fast_tests < <(
  sed -n 's/^FAST_TESTS ?= //p' Makefile | tr ' ' '\n'
)
fast_tests_valid=1
if ((${#fast_tests[@]} == 0)); then
  printf 'FAST_TESTS was not found or is empty; stopping before pytest.\n' >&2
  fast_tests_valid=0
fi
for test_path in "${fast_tests[@]}"; do
  if [[ ! -f "$test_path" ]]; then
    printf 'FAST_TESTS entry is not a file: %s; stopping before pytest.\n' "$test_path" >&2
    fast_tests_valid=0
  fi
done
if ((fast_tests_valid)); then
  docker exec --user "$(id -u):$(id -g)" \
    -w "$container_issue" -e PYTHONPATH="$container_issue" \
    pdfscore_pipeline_pytest_dev \
    /opt/venv_pipeline/bin/python -m pytest "${fast_tests[@]}"
fi
```

For a focused suite, replace the test array with the selected paths/options. `make test-fast`
prefers `.venv_pdf/bin/python` when that file exists, even if `PYTHON` is set; calling the
container interpreter directly avoids silently selecting a host/worktree interpreter. Do not
run host `make test-fast` just to discover that pytest is absent. Create output directories as
the executing user and check existing log ownership before commands that redirect to them.

## Browser validation

Use the prepared Node/Playwright/Chromium runner when the Python container lacks browser
tools. Follow [Review Acceptance](REVIEW_ACCEPTANCE.md#browser-workflow) to start the server
and prepare a fresh writable review package. The example below assumes that the browser runner
shares the server container's network namespace; select and verify an explicit route if it
does not. The runner mounts source read-only and writes evidence to a separate directory.

```bash
if [[ "${ISSUE_ID:-}" =~ ^[0-9]+$ ]]; then
  issue_root="$PWD"
  browser_evidence="$issue_root/logs/issue${ISSUE_ID}/validation/browser"
  mkdir -p "$browser_evidence"
  browser_image="$(docker image inspect mcp/playwright:latest --format '{{.Id}}')"
  chromium_path="$(docker run --rm --entrypoint node "$browser_image" \
    -p 'require("/app/node_modules/playwright").chromium.executablePath()')"
  docker run --rm --network container:pdfscore_pipeline_pytest_dev \
    --user "$(id -u):$(id -g)" \
    -v "$issue_root:/workspace:ro" \
    -v "$browser_evidence:/evidence" \
    -w /workspace \
    -e PLAYWRIGHT_MODULE=/app/node_modules/playwright \
    -e CHROMIUM_PATH="$chromium_path" \
    --entrypoint node "$browser_image" \
    tools/review_correction/browser_acceptance.cjs \
    http://127.0.0.1:8010 /evidence
else
  printf 'Set ISSUE_ID to the active Issue number before running this block.\n' >&2
fi
```

The Playwright/Chromium image is a browser runner, not a production image dependency. A
version check, import probe, blank-page launch, or HTTP probe only establishes environment
readiness; it does not pass browser acceptance. Keep application acceptance results separate
from those probes.

## Local data and navigation

Keep datasets, logs, models, and caches outside issue source worktrees where practical. Use
[`local_worktree_data.md`](local_worktree_data.md) for symlink and explicit Docker mount rules;
Docker cannot follow a host-only symlink unless its target is mounted into the container.
Use [Environment & Tooling](ENVIRONMENTS.md) for maintained images, asset ownership, and
runtime compatibility. This file owns the worktree and validation commands; linked documents
should point here rather than duplicate those procedures.
