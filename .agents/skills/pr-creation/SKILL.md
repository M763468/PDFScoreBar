---
name: pr-creation
description: Use when the user or active repository workflow explicitly requires creating a PDFScoreBar pull request.
---

# pr-creation

Prepare a PR description using `.github/pull_request_template.md` and the current diff. Normal PRs
target `develop` per `docs/BRANCH_POLICY.md`. Run the script only when the user or active repository
workflow explicitly requires creating the PR; it performs an external GitHub write. Report the URL.
