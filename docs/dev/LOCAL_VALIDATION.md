# Local validation environments

Use these environments to finish authorized validation without asking the user to move a
command into Docker. Select the environment first, then run the required check. If a tool is
absent on the host, use the prepared environment below. Start an existing compatible stopped
development container or prepare its missing development tools when needed within the task;
keep production images and other tasks' containers intact. Report Blocked only when the
available routes actually cannot complete the check, with the reason and attempted recovery.

## Available environments

Observed on 2026-10-20; this is a discovery map, not a guarantee that a mutable tag/container
has stayed unchanged. Inspect current identities and capabilities before reuse.

| Environment | Available tools / paths | Use |
| --- | --- | --- |
| Host WSL shell | Git, gh, Docker CLI; Node v22.19.0/npm 11.6.4 via the user's nvm PATH | Worktree/Git provenance, GitHub, Docker launch. Host Python does not establish availability of repository pytest/dependencies. |
| `pdfscore_pipeline_pytest_dev` | Image `5311cf22ab01`; `/opt/venv_pipeline/bin/python` 3.12.15, pytest 8.4.2, Git 2.34.1, make 4.3, bash | Python unit/fast checks and compatible pipeline validation; manager checkout mounted at `/workspace`. **No Node, npm, npx, or Chromium.** No published ports in this snapshot. |
| Local image `mcp/playwright:latest` | Image `8771dc4666e7`; Node v22.23.1/npm 10.9.8, Playwright `1.61.0-alpha-1781023400000` at `/app/node_modules/playwright`, Chromium 149.0.7827.22 at `/ms-playwright/chromium-1226/chrome-linux64/chrome` | Disposable browser runner. Override its MCP entrypoint with `--entrypoint node`; give the script, source, evidence directory, and server network explicitly. |
| `pdfscore_pipeline_gpu` production image | `/opt/venv_pipeline/bin/python`, production model/runtime assets | Canonical GPU/pipeline smoke via maintained Makefile targets. pytest and Node are not part of this image's contract. |

The browser image's default headless-shell executable was absent in this snapshot. Use the
verified full Chromium executable explicitly with `CHROMIUM_PATH` as below; do not stop at
the default launch error or install another browser unnecessarily. A host Node installation
also does not imply that `require('playwright')` resolves; the host default lookup did not
resolve it in this snapshot.

Issue-scoped release/candidate containers are not general development environments. In
particular, a container may mount a frozen `/tmp/...-nogit` release tree read-only. Preserve
that isolation and its candidate identity; do not repoint it or treat it as the active worktree.

## Worktree and mount contract

For normal issue development use `<manager-checkout>/.worktrees/issue<N>`; add a descriptive
suffix for simultaneous worktrees on the same Issue. Create topic branches from current
`origin/develop`, and keep the manager checkout on its existing branch:

```bash
# Run from the manager checkout, e.g. /home/masaki_muramatsu/ws_PDFScoreBar.
git fetch origin develop
mkdir -p .worktrees
git worktree add -b fix/issue435 .worktrees/issue435 origin/develop
cd .worktrees/issue435
```

Use an unused path/branch; resume an existing worktree instead of recreating it. `.worktrees/`
is excluded by both Git and Docker build context rules. For an existing manager checkout
whose branch predates these rules, add `/.worktrees/` to its local `.git/info/exclude` until
its tracked ignore rule is available. Keep nested worktrees out of Docker build contexts too;
use the topic checkout's updated `.dockerignore` when building. Do not bulk scan the manager
checkout for validation; run from the selected issue worktree.

| Host path | Shared Python container path |
| --- | --- |
| `<manager-checkout>` | `/workspace` |
| `<manager-checkout>/.worktrees/issue435` | `/workspace/.worktrees/issue435` |

A bind mount of the manager directory exposes worktrees created under it later. `/tmp` and
sibling worktrees are outside this mount and are not the normal development layout. Move an
existing issue worktree with `git worktree move OLD NEW` when its paths are not retained
provenance or used by a running task. Otherwise preserve it and provide an explicit dedicated
mount. Frozen release/export directories and disposable test fixtures may remain in `/tmp`
when their own contracts require it; do not migrate historical artifacts as cleanup.

Set both the container working directory and `PYTHONPATH` to the issue path. Record Git
provenance on the host: worktree `.git` pointers contain host paths that need not resolve
inside Docker. Do not rewrite them to make container Git work. If a check genuinely requires
access to the worktree's Git metadata inside a container, prepare a dedicated environment
with the necessary paths explicitly mounted, or run that check on a host with its required
dependencies; do not silently omit it.

`scripts/docker_container_preflight.sh` currently requires the active checkout to be mounted
**directly** at `/workspace`; use it only for that dedicated-container layout. It rejects the
shared nested-worktree layout by design. For the shared layout, inspect the manager bind
source and verify the nested worktree's files/import path as described below.

## Python validation from an issue worktree

Run Docker and networked gh commands outside a restricted Codex sandbox from the first
attempt (`sandbox_permissions: require_escalated` where available). Use the same mechanism
for Git operations that write protected shared `.git` metadata. A sandbox refusal is separate
from missing container tools; do not repeat an identical denied attempt.

From the host issue worktree, set its paths and inspect the shared container:

```bash
manager_root=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
issue_relative=$(realpath --relative-to="$manager_root" "$PWD")
container_worktree="/workspace/$issue_relative"
git rev-parse HEAD
docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}} {{json .Mounts}}'
```

Verify that the `/workspace` bind source is `manager_root`, that the issue files are visible
under `container_worktree`, and that the interpreter can import pytest. If the mount is for
another checkout, choose/create the correctly mounted development container using the
[environment setup](../ENVIRONMENTS.md#persistent-pytest-capable-pipeline-container). Before
pipeline use, resolve the inspected immutable image against this worktree with the documented
image resolver and run the required production preflight; tool availability alone is not
GPU/model compatibility evidence. Run Docker-launching targets such as `make verify-gpu-smoke`
on the **host from the issue worktree**; their maintained wrapper mounts that checkout directly
at `/workspace`. Do not launch those targets inside the Python development container.

Execute checks as the host UID/GID to avoid creating root-owned logs. Create `artifacts/`
and the issue's evidence directory as that user; inspect any existing log's permissions.

```bash
mkdir -p artifacts logs/issue435/validation
docker exec --user "$(id -u):$(id -g)" -w "$container_worktree" \
  -e PYTHONPATH="$container_worktree" pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest --version

# Choose the required check; do not run tests just to validate a docs-only change.
docker exec --user "$(id -u):$(id -g)" -w "$container_worktree" \
  -e PYTHONPATH="$container_worktree" pdfscore_pipeline_pytest_dev \
  make test-fast PYTHON=/opt/venv_pipeline/bin/python
```

For a focused suite, replace `make ...` with
`/opt/venv_pipeline/bin/python -m pytest <selected-tests>`. Confirm any worktree-local
`.venv_pdf/bin/python` is compatible before using make, since that target prefers it over
`PYTHON`. Do not run host `make test-fast` merely to discover that pytest only exists in Docker.

## Browser validation

Use this after starting the review server in the shared Python container on port 8010 with a
fresh copied review package, following [Review acceptance](REVIEW_ACCEPTANCE.md#browser-workflow).
The browser runner shares that container's network namespace, so `127.0.0.1:8010` reaches the
server without publishing new ports. Its own `/workspace` mount is the active issue worktree,
read-only, with a separate writable evidence bind at `/evidence`. Retained data outside that worktree needs explicit
mounts on the server side as described in [Local worktree data](local_worktree_data.md#docker-mounts).

```bash
# Run from the host issue worktree; use the Issue/run ID for the current task.
mkdir -p logs/issue435/validation/browser
browser_image=$(docker image inspect mcp/playwright:latest --format '{{.Id}}')
chromium_path=$(docker run --rm --entrypoint node "$browser_image" \
  -p 'require("/app/node_modules/playwright").chromium.executablePath()')
docker run --rm --network container:pdfscore_pipeline_pytest_dev \
  --user "$(id -u):$(id -g)" \
  -v "$PWD":/workspace:ro \
  -v "$PWD/logs/issue435/validation/browser":/evidence \
  -w /workspace \
  -e PLAYWRIGHT_MODULE=/app/node_modules/playwright \
  -e CHROMIUM_PATH="$chromium_path" \
  --entrypoint node "$browser_image" \
  tools/review_correction/browser_acceptance.cjs http://127.0.0.1:8010 /evidence
```

This is browser execution, not a production image dependency. Reuse the local image; no
Node installation in the Python container is needed. If the server runs elsewhere, explicitly
choose networking that reaches it and verify the URL from the browser runner before the gate.
A `--version`, import probe, blank-page browser launch, or HTTP reachability check is environment
preparation, not a passed browser acceptance test. Report the actual gate separately using
[validation evidence rules](VALIDATION_POLICY.md#validation-status-and-evidence).
