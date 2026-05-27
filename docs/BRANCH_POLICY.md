# Branch Policy

This document records the repository branch policy decided in Issue #168 after the Issue #120 canonical rebuild was merged through PR #167.

## Branch roles

- `develop` is the active integration branch.
- `main` is the stable/release branch.
- Normal feature, fix, refactor, and performance work must branch from `develop` and open PRs against `develop`, unless the issue explicitly states otherwise.
- `develop -> main` must be done through a dedicated promotion PR, not through incidental feature PRs.

## Default issue and PR base

For new work:

- Base branch: `develop`
- PR base: `develop`

Older open issues may still contain stale text such as `Base branch: main` or `PR base: main`. Treat those fields as stale unless the issue is explicitly about release/promotion work.

When starting an older issue, restate the effective branch policy in the working session or issue comment:

- Base branch: `develop`
- PR base: `develop`

Only edit the old issue body when the issue is actively picked up and the stale branch text is likely to cause confusion.

## Promotion from `develop` to `main`

A promotion PR from `develop` to `main` is required for release/stable promotion.

The promotion PR must include, at minimum:

- normal compile/test checks relevant to the included changes
- confirmation of the Issue #120 canonical detector contract:
  - `expected_pages=68`
  - `evaluated_pages=68`
  - `missing_pages=[]`
  - `TP=3580`
  - `FP=0`
  - `FN=1`
  - `FN_det=0`
  - `FN_cnn=1`
  - `cnn_apply_nms=false`
  - `target_met.detector=true`
- an explicit note that downstream measure-count metrics are not part of the Issue #120 detector acceptance gate unless a separate canonical comparator is introduced.

## Issue #163 timing

Issue #163 should proceed from `develop` before the first `develop -> main` promotion.

Issue #163 is a HOMR/SR route parallelization runtime experiment and must remain opt-in unless safety is proven. Its output may be one of:

- no production behavior change
- an opt-in mode only
- a later default change only after detector contract and resource safety are confirmed

Whether #163 is included in the first `main` promotion must be decided after #163 acceptance results are available.

## Rationale

Issue #120 has been completed and integrated into `develop`. The accepted post-merge detector contract is the current canonical detector baseline. `main` may not represent that latest validated state until a dedicated promotion PR is performed.
