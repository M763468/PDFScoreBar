# Minimal Mainline Runtime Surface

Issue #100 is about extracting the smallest coherent PDFScoreBar **runtime/function surface**, not
about copying everything that is useful while developing this repository. The current repository may
continue to retain tests, CI, canonical validation evidence, reproduction tooling, training tools,
and historical evidence, while those assets stay outside the executable bundle.

The machine-readable contract is `docs/MINIMAL_MAINLINE_SURFACE.json`. The broader current-repository
classification remains in `docs/REPOSITORY_SURFACE_INVENTORY.md`.

## Three surfaces

### 1. Minimal runtime bundle

The runtime bundle contains only what is required to execute the canonical dense pipeline and the
versioned one-job engine boundary:

- runtime dependency/build inputs (`pyproject.toml`, `Dockerfile`, runtime Docker helpers);
- the dense algorithm base config and maintained HOMR profile;
- production model manifests/checkpoints under `models/**`;
- the runtime-owned `src/**` modules listed explicitly in the JSON contract;
- the engine/correction/final-output implementation needed to turn a PDF job into published
  artifacts.

The JSON lists each selected runtime file exactly. It also gives a separate reason for each
tracked `src/` file outside the canonical dense/engine execution path. The drift check fails
when a new source file has not been classified. No test module is part of the runtime bundle.

`PipelineJobExecutor` is the clean extraction-facing entrypoint: it accepts a PDF job, derives a
request-local config from the dense algorithm base, replaces evaluation-specific image input with the
actual PDF, enables rendering, and owns output/review materialization. The fact that
`configs/dense_full_pipeline.yaml` can still be used directly against `data/evaluation2/images` for
canonical development/evaluation does not make `data/evaluation2/**` a runtime dependency.

### 2. Development/validation surface

These assets remain important in this repository, but are explicitly **not shipped in the minimal
runtime bundle**:

- `tests/**`;
- `.github/**` CI;
- `data/evaluation2/**` GT/canonical validation evidence;
- smoke/service-readiness configs;
- repository validation scripts and most `tools/verification/**` files;
- agent/Graphify/developer tooling;
- training tools such as `tools/mmr_training/**`.

This distinction lets the current repository remain safely maintainable without confusing
maintainability evidence with runtime requirements.

### 3. Reproduction/history surface

Issue-specific reproduction and historical compatibility remain separately retained when useful, but
are not part of the extracted runtime. Examples include:

- `tools/issue120/**`;
- `Dockerfile.homr`;
- the Stage-E historical profile and route compatibility shim;
- `experiments/**` after the production OMR-DLN entrypoint was moved into `src/**`.

## Placement corrections performed by Issue #100

The detailed audit found several cases where directory placement did not reflect ownership.

### OMR-DLN production execution

Before #100, the canonical dense route launched `experiments/models/eval_omr_dln.py`. That script
mixed the production prediction path with evaluation-only options, visualization, optional internal
SR, legacy single-image handling, debug output, and experiment error logging.

#100 adds `src/pipeline/detection/omr_dln_worker.py` as a fail-fast production worker that accepts the
already-owned precomputed x4 SR artifact and writes the source-coordinate predictions required by
hybrid consensus. `current_support_worker.py` now invokes that module. `experiments/**` is therefore
no longer a canonical runtime requirement.

### Dense production orchestrator naming

The canonical route previously dispatched through modules named `restored_orchestrator.py` and
`restored_orchestrator_batch_sr.py`, even though those files implement the accepted production route.
The production names are now `dense_orchestrator.py` and `dense_orchestrator_batch_sr.py`.
Compatibility shims remain only for older imports and are excluded from the minimal runtime bundle.

### MMR production checkpoint

The canonical config previously loaded its runtime MMR checkpoint from
`tools/mmr_training/models/mmr_classifier_best.pth`. The checkpoint now lives at
`models/mmr/mmr_classifier_best.pth`; training tooling and runtime model ownership are no longer
conflated.

### Runtime package hygiene

Two unit-test modules under `src/measure_numbering/` were moved to `tests/`, and the visualization
helper was moved to `tools/`. `src/ml_detector/barline_detector.py` was removed: it depended directly
on the retired OEMER stack, which is not part of the current dependency set or canonical runtime.

The remaining source exclusions are recorded file by file in `source_excluded`: the older
standard/hybrid detector routes, Issue #120 candidate route, Stage-E route, compatibility shims,
HOMR evaluator CLI, and movement-boundary candidate producer. Their presence in the development
repository does not make them dependencies of the selected dense engine route.

The selected dense route still launches two scripts from `tools/verification/gt_preparation/`;
one of those imports a third helper there. The numbering step launches
`tools/add_measure_numbers.py`. They are **runtime
dependencies despite their directory names**. The exact files are included in the JSON
runtime set; the rest of `tools/verification/**` stays development-only. Relocating those
helpers into `src/` can be done later without widening the executable selection.

## Remaining mixed-runtime boundaries

The audit also found code that is genuinely runtime-owned but still mixed with historical/evaluation
responsibilities. These are not grounds for copying the containing directories wholesale.

### HOMR runtime under `homr_eval_scripts`

The current HOMR workers import `src/homr_eval_scripts/core/**` and `segnet_cache.py`; the large
`core/heuristics.py` is one of the explicit #115 refactor targets. In contrast,
`src/homr_eval_scripts/homr_evaluator.py` is evaluation tooling and is not part of the runtime
bundle.

For a clean physical extraction, #115 should move/split the runtime-owned HOMR implementation into a
production package while preserving behavior, and leave evaluation wrappers outside that package.
This is now a **concrete #100 -> #115 dependency**, rather than a blanket requirement to split every
large file before #100 can proceed.

### Mixed HOMR profile dispatch

`src/pipeline/detection/homr_profile.py` and `profile_hybrid.py` still contain both the maintained
production route and Stage-E-compatible reproduction behavior. The JSON contract records this as an
explicit mixed source. A physical minimal repository should split the maintained execution path from
the historical adapter rather than carry the Stage-E branch merely because it shares a file today.

## Target runtime structure

The extracted runtime should converge toward this ownership structure (illustrative package names;
the JSON contract is authoritative for current files):

```text
.
├── src/
│   ├── common/                  # shared runtime primitives
│   ├── homr_runtime/            # target location for runtime HOMR code (coordinated with #115)
│   ├── measure_numbering/       # runtime modules only; no tests/visualizers
│   ├── pipeline/
│   │   ├── core/
│   │   ├── detection/           # dense production route and workers
│   │   ├── detector_routes/     # canonical dense reconstruction only
│   │   ├── probe_detector/
│   │   ├── review/
│   │   ├── steps/
│   │   └── utils/
│   └── pdf_to_images.py
├── configs/
│   ├── dense_full_pipeline.yaml
│   └── detector_profiles/maintained_original_homr.json
├── models/
│   ├── barline_cnn/
│   ├── omr_dln/
│   └── mmr/
├── docker/
├── Dockerfile
└── pyproject.toml
```

Tests, validation datasets, CI, developer tooling, model-training code, Graphify output, Issue-specific
reproduction, and historical compatibility are deliberately outside this runtime tree.

## Relationship to Issue #115

#115 is still not a blanket blocker. The detailed #100 audit identified one concrete coordination
point: runtime-owned HOMR code lives under `src/homr_eval_scripts/core/**`, including the large
`heuristics.py` that #115 already plans to split. Moving that code twice would create unnecessary
churn, so the production-package extraction for that slice should be done as part of the #115
responsibility split.

Other large modules should only block #100 if their retained and non-retained responsibilities cannot
be represented or extracted safely without first splitting the module.

## Drift check

Run:

```bash
python3 tools/check_repository_surface.py
```

The checker validates these boundaries rather than treating every maintained repository file
as runtime:

1. each selected runtime file is tracked, and every tracked `src/` file is selected or excluded;
2. development/validation and reproduction groups stay outside the runtime bundle except for
   named runtime helper files;
3. retired or wrongly placed current-repository paths do not reappear; and
4. source references to direct `tools/*.py` helpers stay in the runtime set, and canonical callers
   no longer point at the experiment OMR-DLN path, old dense-orchestrator name, or training-tool
   MMR model path.

This check is a repository-structure gate only. Runtime behavior changes still require the validation
specified by `docs/dev/VALIDATION_POLICY.md`.
