# Documentation guide

Start with the document that answers your question. The development repository retains
historical evidence and validation guidance; those documents are not part of the proposed
executable package.

| Question | Read first |
| --- | --- |
| What is the minimum executable subset, and is it ready to extract? | [Minimal mainline surface](MINIMAL_MAINLINE_SURFACE.md) and its [exact file list](MINIMAL_MAINLINE_SURFACE.json) |
| How does the current pipeline work? | [Pipeline architecture](PIPELINE_ARCHITECTURE.md) |
| How do I run the current repository? | [Environments](ENVIRONMENTS.md), then [manual correction workflow](manual_correction_review_package.md) if needed |
| What does an engine caller send and receive? | [Engine job contract](ENGINE_JOB_CONTRACT.md) |
| How do I change and verify this repository? | [Branch policy](BRANCH_POLICY.md) and [validation policy](dev/VALIDATION_POLICY.md) |
| Why was older code or evidence retained? | [Repository surface inventory](REPOSITORY_SURFACE_INVENTORY.md), [documentation inventory](DOCUMENTATION_INVENTORY.md), then [history index](HISTORY_INDEX.md) |
| Where do user correction and GT developer tooling belong? | [User correction boundary](USER_CORRECTION_BOUNDARY.md) |

The minimum selection has one prose explanation and one machine-readable list. The repository
and documentation inventories are broader historical audits. They must not be used as a second
runtime file list. `docs/**` and `tests/**` remain available to developers but are absent from
the current proposed executable subset.

## More specific contracts

- [Engine lifecycle](ENGINE_JOB_LIFECYCLE.md), [input safety](ENGINE_INPUT_SAFETY.md),
  and [telemetry](ENGINE_TELEMETRY.md) refine the one-job contract.
- [Final output](corrected_final_output.md), [numbering geometry](NUMBERING_GEOMETRY_CONTRACT.md),
  [GT preparation](GT_PREPARATION_POLICY.md), and [barline matching](BARLINE_MATCHER.md)
  describe narrower output or validation behavior.
- [Makefile surface](MAKEFILE_SURFACE.md), [regression workflow](REGRESSION_TEST_WORKFLOW.md),
  and [script management](SCRIPT_MANAGEMENT.md) guide repository development.
- [Future service architecture](FUTURE_SERVICE_ARCHITECTURE.md) is a roadmap, not current
  runtime behavior. [Two-HOMR milestone](TWO_HOMR_MILESTONE.md) is a frozen comparison,
  not the current production configuration.

For a historical investigation, use the [history index](HISTORY_INDEX.md) to locate its
Issue or accepted result. Current behavior is defined by source, tests, the active config,
and the current architecture document. Update the relevant current contract when behavior
changes; do not copy historical notes into another general guide.
