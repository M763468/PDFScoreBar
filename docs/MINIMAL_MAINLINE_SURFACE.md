# Minimal Mainline Surface

Issue #100 defines the smallest maintained repository surface that a future PDFScoreBar mainline
extraction must preserve. This document is the human-readable contract. Its machine-readable
companion is `docs/MINIMAL_MAINLINE_SURFACE.json`.

The detailed current-tree classification remains in
`docs/REPOSITORY_SURFACE_INVENTORY.md`. This document does not repeat that audit or turn every
retained historical asset into a supported runtime API.

## Contract

A future extraction must preserve three distinct groups.

### Maintained mainline

Keep the current production/runtime, contract, correction, validation, and repository-maintenance
surface:

- `src/**`, canonical dependency/build metadata, `Dockerfile`, and `docker/**`;
- canonical runtime/smoke/review configs and detector profile/route contracts;
- model manifests/provenance under `models/**`;
- current tests and CI/validation tooling;
- current correction/GT GUI and verification tooling;
- current architecture, engine, correction, repository, and validation documentation;
- `data/evaluation2/**` as canonical validation/GT evidence.

The current dense route also has one explicit runtime-owned exception outside `src/**`:
`experiments/models/eval_omr_dln.py`. It remains part of the maintained surface until the
entrypoint is moved into `src/**` and its caller plus `docker/runtime_contract.py` are updated
coherently.

### Retained reproduction assets

These remain available but are not normal runtime entrypoints:

- `tools/issue120/**` for the accepted Issue #120 reproduction contract;
- `Dockerfile.homr` for historical/isolated HOMR evaluation.

Retaining these assets does not make the surrounding historical experiment surface part of the
minimal runtime.

### Explicitly excluded retired surface

The minimal mainline must not recreate cleanup already completed under #379-#383. The machine
contract rejects reintroduction of the retired second test tree, pre-evaluation2 tracked data trees,
obsolete setup helpers, the GroundingDINO Dockerfile, the retired tracked external/submodule surface,
and `.gitmodules`.

## Target directory structure

The target is based on current maintained responsibilities rather than old experiment-era names:

```text
.
├── src/                         # runtime and reusable engine implementation
├── configs/                     # canonical runtime + retained scoped configs
├── models/                      # model manifests/provenance
├── docker/                      # runtime contract/build support
├── tests/                       # maintained regression/contract tests
├── data/evaluation2/            # canonical validation/GT evidence
├── scripts/                     # maintained repository automation
├── tools/
│   ├── gt_relabel_gui/          # current correction/GT tooling
│   ├── verification/            # maintained verification tooling
│   └── issue120/                # retained reproduction-only surface
├── experiments/models/
│   └── eval_omr_dln.py          # temporary runtime-owned path exception
├── docs/                        # current contracts + selected durable evidence
├── .github/                     # CI/repository workflow
├── Dockerfile                   # canonical runtime image
├── Dockerfile.homr              # retained isolated/historical evaluation image
├── Makefile
├── pyproject.toml
├── README.md
└── AGENTS.md
```

This Issue does not perform the repository split or directory migration itself. A later extraction
may move the OMR-DLN entrypoint or reproduction assets into cleaner locations, but such moves must
update all runtime/reproduction references in the same change.

## Relationship to Issue #115

Issue #115 is not a blanket prerequisite for this contract. The minimal mainline retains
`src/**` as maintained source, so the current large modules can be carried without first splitting
them.

Treat #115 as a concrete prerequisite only if a later extraction step finds a module that mixes
retained and non-retained responsibilities such that ownership or publication cannot be separated
safely. Record that specific boundary instead of blocking #100 on all large-file refactoring.

At the time this contract was created, no such blocker was required to define the maintained
surface.

## Drift check

Run:

```bash
python3 tools/check_repository_surface.py
```

The check is intentionally lightweight. It verifies that:

1. every required maintained/reproduction/runtime-exception pattern still resolves to tracked files;
2. explicitly retired paths have not re-entered the tracked tree; and
3. durable repository-surface documentation still references this contract.

CI runs the same check for pull requests that can affect repository contents. The checker does not
replace behavior tests, GPU smoke, or full evaluation; those remain governed by
`docs/dev/VALIDATION_POLICY.md`.
