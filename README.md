# PDF Score Measure Number Adder

This repository is an experimental workspace for automatically adding measure numbers to PDF sheet music.

The current repository map and operating rules are maintained in `docs/README.md`.

## Current branch policy

- `develop` is the active integration branch.
- `main` is the stable/release branch.
- Normal work branches should target `develop`.
- Promotion from `develop` to `main` must use a dedicated promotion PR with explicit validation results.

See `docs/BRANCH_POLICY.md` for the standing policy and `AGENTS.md` for agent operating rules.

## Main code areas

- `src/`: pipeline and reusable project code.
- `tools/`: maintained command-line utilities and evaluation helpers.
- `experiments/`: experimental scripts that are not part of normal runtime.
- `configs/`: pipeline and evaluation configuration files.
- `docs/`: project documentation, validation policy, and historical records.
- `data/`: retained evaluation fixtures and local data layout documentation.

Generated logs and run outputs should stay under ignored `logs/` paths unless a specific retention policy says otherwise.

## Validation entry points

Common validation commands are exposed through the `Makefile`:

```bash
make test-fast
make lint
make eval-issue120-stage-e-smoke
```

Select validation according to `docs/dev/VALIDATION_POLICY.md` and the scope of the current change.

## License

No explicit license has been declared in this repository.
