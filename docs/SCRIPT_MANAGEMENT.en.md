# Script management and directory rules

<!-- translation: {"original":"SCRIPT_MANAGEMENT.md","source":{"sha256":"6e48200c89a13e4ec4e620a3fc83dd257f05454075f61e26bd6f630b51821737"},"state":"reviewed"} -->

[日本語 / Original](SCRIPT_MANAGEMENT.md) (Japanese original)

Translation source: same PR / SHA-256 `6e48200c89a13e4ec4e620a3fc83dd257f05454075f61e26bd6f630b51821737`. State: `reviewed`. Meaning, constraints and exceptions were checked against the original, and English readability was reviewed.

This document defines where scripts belong in the current repository and when they are promoted, retained or deleted. The historical per-file move list remains in Git history and Issue #45 / PR #184; this document covers only the current rules.

## Basic principles

Place scripts by **responsibility and lifetime**, not by "where it happens to be used right now".

| Location | Intended role | Production dependency |
| --- | --- | --- |
| `src/pipeline/` | Implementation of the current production pipeline | authoritative runtime code |
| `tools/` | Reusable maintenance, evaluation and conversion CLIs/utilities | must not become a hidden dependency |
| `experiments/` | Hypothesis testing, comparison, reproduction, prototypes | production runtime must not depend on it |
| `tmp/` | Temporary checks and in-progress scratch | not managed by Git |

### `src/pipeline/`

Current production behavior belongs here. Production code must not import `tools/` CLIs for convenience, or search `experiments/` to implicitly determine runtime inputs.

Logic adopted from an experiment is explicitly promoted to the production side together with the required tests, config and provenance.

### `tools/`

Put CLIs/utilities reused across Issues or in day-to-day operation here. One-off scripts hard-coded to a specific page, run or debugging phase are generally not kept here.

If production needs shared logic, extract it to an appropriate library/module boundary instead of depending on the CLI script itself.

### `experiments/`

Put scripts/configs for hypothesis testing, parameter sweeps, comparisons and reproduction here. When an experiment ends, do one of the following:

- Reproduction or comparison value remains: keep it with clear provenance.
- A reusable general rule was learned: move it to current source/tests/generic docs.
- One-off with no reuse value: delete it, with Git history serving as the archive.

The existence of something in `experiments/` must never become a production runtime fallback or a model-discovery contract.

### `tmp/`

Scratch space for "make it work first and check". Treat it as covered by `.gitignore`, and promote only what proves useful to `tools/` / `experiments/` / a production module.

## Lifecycle

When adding a new script, decide in this order:

1. Check whether an existing production module / tool can already handle it.
2. Choose `tmp/` for a temporary check, `experiments/<topic>/` for hypothesis testing, or `tools/` for a repeatedly used CLI.
3. Make the purpose and input provenance clear from the file name, README and config.
4. When the experiment ends, state explicitly whether it is adopted, kept for reproduction, or deleted.
5. When deleting, confirm that important results and adoption/rejection reasons are recoverable from Issues/PRs/commits/current docs.

Do not keep files with unclear purpose or lifetime, such as `temp.py`, `test.py` or `debug_page3_fix.py`, long term.

## Historical cleanup lineage

Issue #45 / PR #184 inventoried CNN-related `tools/` / `experiments/`, deleted one-off scripts, moved active-learning scripts to `experiments/`, and moved generic diagnostic tools to `tools/diagnostics/`. For the old location of individual files, see that Issue/PR and Git history.

Issue #185 / PR #188 removed the implicit `experiments/cnn_classifier/**/best_model.pth` fallback from production CNN model resolution. Explicitly resolving the configured model path is now the production contract.

## Recovering retired scripts

To inspect a deleted one-off script for archaeology, use Git history.

```bash
git log --follow -- <old-path>
git show <commit>:<old-path>
```

Do not unconditionally return a retired script to the current workflow just because it exists in history. First check consistency with the current source/config/tests.
