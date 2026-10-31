# Documentation guide

Start with the document that answers your question. The development repository retains
historical evidence and validation guidance; those documents are not part of the proposed
executable package.

| Question | Read first |
| --- | --- |
| What is the minimum executable subset, and is it ready to extract? | [Minimal mainline surface](MINIMAL_MAINLINE_SURFACE.md) and its [exact file list](MINIMAL_MAINLINE_SURFACE.json) |
| How does the current pipeline work? | [Pipeline architecture (English)](PIPELINE_ARCHITECTURE.md) / [日本語（reviewed）](PIPELINE_ARCHITECTURE.ja.md) |
| Where are exact detection/numbering implementation contracts? | [Implementation reference (English)](PIPELINE_ARCHITECTURE_REFERENCE.md) / [日本語（reviewed）](PIPELINE_ARCHITECTURE_REFERENCE.ja.md) |
| How do I run the current repository? | [Environments](ENVIRONMENTS.md) ([日本語](ENVIRONMENTS.ja.md)), then [manual correction workflow](manual_correction_review_package.md) if needed |
| How are user corrections separated from GT/developer tools? | [User correction boundary](USER_CORRECTION_BOUNDARY.md) |
| What does an engine caller send and receive? | [Engine job contract (English)](ENGINE_JOB_CONTRACT.md) / [日本語（reviewed）](ENGINE_JOB_CONTRACT.ja.md) |
| How do I change and verify this repository? | [Branch policy](BRANCH_POLICY.md) ([日本語](BRANCH_POLICY.ja.md)) and [validation policy](dev/VALIDATION_POLICY.md) ([日本語](dev/VALIDATION_POLICY.ja.md)); [local validation](dev/LOCAL_VALIDATION.md) ([日本語](dev/LOCAL_VALIDATION.ja.md)) |
| Why was older code or evidence retained? | [Repository surface inventory](REPOSITORY_SURFACE_INVENTORY.md), [documentation inventory](DOCUMENTATION_INVENTORY.md), then [history index](HISTORY_INDEX.md) |

The minimum selection has one prose explanation and one machine-readable list. The repository
and documentation inventories are broader historical audits. They must not be used as a second
runtime file list. `docs/**` and `tests/**` remain available to developers but are absent from
the current proposed executable subset.

## Documentation languages

The [coverage inventory](DOCUMENTATION_INVENTORY.md#bilingual-coverage-and-translation-scope)
records original languages, missing counterparts and translation priorities. Follow the
[language and maintenance policy](DOCUMENTATION_LANGUAGE_POLICY.md)
([日本語](DOCUMENTATION_LANGUAGE_POLICY.ja.md)) when adding or updating a translation.
Most existing guides currently have no complete Japanese counterpart; Japanese UI examples
do not indicate full translation.

## More specific contracts

- [Engine lifecycle](ENGINE_JOB_LIFECYCLE.md) ([日本語](ENGINE_JOB_LIFECYCLE.ja.md)),
  [input safety](ENGINE_INPUT_SAFETY.md) ([日本語](ENGINE_INPUT_SAFETY.ja.md)),
  and [telemetry](ENGINE_TELEMETRY.md) ([日本語](ENGINE_TELEMETRY.ja.md)) refine the one-job contract.
  [Service-readiness gates](ENGINE_SERVICE_READINESS.md) ([日本語](ENGINE_SERVICE_READINESS.ja.md))
  describe supported executor behavior and compatibility checks; future worker isolation remains separate.
- [Final output](corrected_final_output.md), [numbering geometry](NUMBERING_GEOMETRY_CONTRACT.md),
  [GT preparation](GT_PREPARATION_POLICY.md), and [barline matching](BARLINE_MATCHER.md)
  describe narrower output or validation behavior.
- [Model artifact contract](MODEL_ARTIFACT_CONTRACT.md) ([日本語](MODEL_ARTIFACT_CONTRACT.ja.md)) defines current model identities;
  [production model artifacts](MODEL_ARTIFACTS.md) ([日本語](MODEL_ARTIFACTS.ja.md)) covers publication and cache workflows;
  [exploration and comparison model selection](dev/EXPERIMENT_MODEL_SELECTION.md) is the
  Japanese developer guide to explicit candidate paths, fixed comparisons, and production
  validation (#448 / PR #451).
- [Makefile surface](MAKEFILE_SURFACE.md) ([日本語](MAKEFILE_SURFACE.ja.md)), [regression workflow](REGRESSION_TEST_WORKFLOW.md) ([日本語](REGRESSION_TEST_WORKFLOW.ja.md)),
  and [script management](SCRIPT_MANAGEMENT.md) guide repository development.
- [Future service architecture](FUTURE_SERVICE_ARCHITECTURE.md) is a roadmap, not current
  runtime behavior. [Two-HOMR milestone](TWO_HOMR_MILESTONE.md) is a frozen comparison,
  not the current production configuration.

For a historical investigation, use the [history index](HISTORY_INDEX.md) to locate its
Issue or accepted result. Current behavior is defined by source, tests, the active config,
and the current architecture document. Update the relevant current contract when behavior
changes; do not copy historical notes into another general guide.
