# Development model exploration, fixed comparison, and production selection

<!-- translation: {"original":"EXPERIMENT_MODEL_SELECTION.md","source":{"sha256":"628226aee13b762e405fe475eb3630d76fb2273a748be4a6b140674687d792e1"},"state":"reviewed"} -->

[日本語 / Original](EXPERIMENT_MODEL_SELECTION.md) (Japanese original)

Translation source: same PR / SHA-256 `628226aee13b762e405fe475eb3630d76fb2273a748be4a6b140674687d792e1`. State: `reviewed`. Meaning, constraints and exceptions were checked against the original, and English readability was reviewed.

CNN and OMR-DLN candidates can be tried through explicit paths in an existing config.
You do not need to register a version/SHA/provenance or edit the production manifest for each exploration.

For the canonical current production contract, see the [model artifact contract](../contracts/MODEL_ARTIFACT_CONTRACT.md),
the [model registration procedure](MODEL_ARTIFACTS.md), and the [validation policy](VALIDATION_POLICY.md).

## Validation modes

Set `detection.model_validation`. It defaults to `production`; unknown values are errors.
`exploration` / `comparison` are supported only with `detection.detector_route: dense_full_pipeline`.
Combinations with an omitted route (standard), the standard route, or an unknown route are rejected at both the preflight and direct pipeline entry points.

| Setting | Model selection and validation | Pinning / recording |
| --- | --- | --- |
| `exploration` | Actually loads the current checkpoint at the explicit path. Checks supported architecture, tensor shapes, I/O, and the requested device. Does not require a match with adopted bytes | Records the current hash automatically at run time. No prior registration. Weights at the same path can be updated and rerun |
| `comparison` | Same selection/load path as exploration, plus a required match with `model_sha256.cnn` / `model_sha256.omr_dln` | Copy the hashes from the exploration result to pin them. Also fix the evaluation inputs, config, runtime, metric, seed and tolerance before the experiment |
| `production` | Validates the existing CNN manifest/architecture/threshold contract, the OMR-DLN selected manifest SHA, the maintained runtime, and the distribution inventory | Keeps the adopted version/provenance/integrity contract |

Preflight success, pipeline-run success, passing an accuracy comparison, and production adoption are separate decisions.
Docker runs in candidate modes do not automatically reuse the production-only accuracy smoke.
For a fixed comparison, run the pre-declared evaluation command and every regression gate separately.

## Scope and checks

| Item | Exploration / comparison | Production / distribution | Basis / purpose |
| --- | --- | --- | --- |
| CNN path | `cnn_model_path` takes precedence. The candidate path is used even if a manifest remains in the copied config. If unset, resolved from the manifest | Rejects raw paths and requires a manifest | `dense_orchestrator.py` / `model_selection.py`. Separates candidate replacement from adopted selection |
| CNN architecture | ResNet18 / EfficientNet-B0 as supported by the existing loader. Validates the binary head and state_dict shapes | Keeps EfficientNet-B0 | `steps/cnn_scoring.py`. The EfficientNet-B0-only check is excluded for exploration, and the actual load path is shared |
| CNN threshold | Explicit in config, finite, 0–1. Need not match the manifest `production_contract` | Keeps the match with the manifest threshold | `dense_orchestrator.py`. Threshold search is stated as a comparison condition |
| CNN NMS/crop/geometry | Existing I/O/scoring conditions such as NMS=false on the dense route are kept | Unchanged | Downstream semantic contract separate from model identity |
| OMR-DLN path | `omr_dln_model_path` first, then the environment variable. No fallback from an explicitly specified missing/corrupt candidate to another model | Production manifest SHA check is required even with the same override | `model_selection.py`. Resolution/check logic previously duplicated in the Docker launcher is shared |
| OMR-DLN compatibility | Validates native `.pt`, detection task and box I/O, explicit device, and prediction I/O. The candidate author guarantees that the model's meaning is "measure" | The existing selected model | `omr_dln_worker.py`. Exported ONNX/TensorRT candidates are not supported |
| Weight hash/version | Exploration records the actual hash automatically; only comparison checks a specified hash | Validates the SHA of the manifest-selected version | No obligation to pre-register SHA/version/provenance for every candidate |
| Reuse of old detection output | Detection skip-existing is disabled so old results are not used after a model swap | Unchanged | `dense_orchestrator.py`. Supports rerunning weights retrained at the same path |
| HOMR source pin/marker | Uses the current maintained runtime as-is. Candidate HOMR replacement is not supported | Required | `profile_contract.py` / `maintained_homr_worker.py`. An unsupported runtime is not treated as runnable by removing checks |
| SR / MMR / OCR | Validation of candidate replacement is out of scope | Keeps existing settings and assets | SR is image-owned. The MMR raw-path existence check is not a full weight SHA validation |
| Image/runtime compatibility | Keeps image existence, immutable ID, and runtime fingerprint checks | Required | `scripts/docker_image_resolver.py` / `docker/runtime_contract.py` |
| Source provenance | Records the source fingerprint and the executed source. A source mismatch with image build time is not itself a rejection condition | Frozen distributions add inventory/hash/dirty checks | Runtime compatibility and source identity are separate concepts |
| Provider/device | CNN/OMR candidates explicitly use `cpu` or `cuda`; default `cuda`. No fallback from a CUDA request to CPU | Keeps the current CUDA/ONNX/maintained contract | A GPU listing alone is not treated as a successful load. MMR OCR fallback after a warning is outside the candidate guarantee |
| Input/weight existence and mounts | Checks visibility from the container and mounts candidates read-only | Unchanged | An absolute symlink target on the host is not necessarily visible in the container |
| Distribution identity | Rejects candidate modes from a frozen distribution; use a development checkout | Strictly validates schema/inventory/path/hash/release provenance | `distribution.py:source_identity` / `runtime_contract.py:validate_distribution_provenance` |

The shared artifact cache precedence (explicit root → `PDFSCOREBAR_MODEL_CACHE` → XDG → user cache) is unchanged.
Raw exploration checkpoints need no cache registration. Manifest-specified artifacts are still validated against that manifest's SHA.

## Exploration example

Copy `configs/dense_full_pipeline.yaml` or similar to a working config and change the following.
Match the data/input/output settings to the original config's purpose. The example below shows only added or changed fields.
Replace `issueNNN` with the number of the Issue you are working on.

```yaml
run:
  run_id: candidate_01
  output_root: logs/issueNNN/experiments

detection:
  model_validation: exploration
  cnn_model_path: /absolute/path/to/candidate.pth
  cnn_threshold: 0.5
  cnn_device: cuda
  omr_dln_model_path: /absolute/path/to/measure_candidate.pt
  omr_dln_device: cuda
```

The original CNN manifest may remain. Removing `cnn_model_path` returns to manifest selection.
When trying only one model, the other can use the existing manifest/cache or the adopted path.
After saving new weights to the same path, you can rerun without editing the config or the preflight itself.
Even during exploration, avoid rewriting a checkpoint while a run is in progress. If a change is detected between the start and end of a run, the results are invalid and the run stops.

```bash
bash scripts/docker_runtime_validation.sh --config experiments/my_candidate.yaml --preflight-only
bash scripts/docker_runtime_validation.sh --config experiments/my_candidate.yaml
```

The existing launcher resolves the candidate paths, mounts the CNN/OMR read-only, and runs preflight and the pipeline with the same config.
Mount external PDFs and similar inputs with `DOCKER_EXTRA_ARGS` as before.
If HOMR/SR runtime compatibility does not change, no image rebuild is needed to update a checkpoint.
There is no new selection manifest or dedicated runner for candidates.
Running `src/pipeline/main.py --config ...` directly uses the same selection policy,
but mounting external paths and recording image provenance are the caller's responsibility. The Docker preflight's actual load/I/O check must be done separately.

## Fixed comparison and reproduction

A candidate run's `<run-dir>/model_selection.json` records the selected CNN/OMR paths and actual SHAs,
the config, input image SHAs, source/runtime fingerprints, and the source commit/image ID passed from the launcher.
`status: selected` is an observation record, not a declaration that the pipeline or accuracy evaluation succeeded.
Keep the detection source manifest/result, pipeline log, and evaluation result in the same Issue root.

```python
import json
import yaml

config = yaml.safe_load(open("experiments/my_candidate.yaml"))
observed = json.load(open("logs/issueNNN/experiments/candidate_01/model_selection.json"))
config["detection"]["model_validation"] = "comparison"
config["detection"]["model_sha256"] = {
    role: model["sha256"] for role, model in observed["models"].items()
}
with open("experiments/fixed_comparison.yaml", "w") as output:
    yaml.safe_dump(config, output)
```

At run time, set the immutable image ID in `DOCKER_IMAGE`, and fix and save the source commit plus dirty diff, input set,
config, baseline, metric, semantic gates, tolerance and seed before evaluation.
`model_sha256` is a byte check of the two models; it alone does not make all experiment conditions reproducible.
Comparison mode stops on a missing hash or a changed checkpoint. Results after a threshold search are a separate experiment.

## Production promotion and failure handling

1. Evaluate the candidate on the same inputs and confirm every accuracy and downstream semantic regression gate.
2. Only when accepted results and review are in place, update the production version/provenance/digest in a separate adoption change.
   Publish publishable artifacts to a new Release and perform a fresh download, empty-cache materialization, and SHA check.
   For operator-supplied models, keep the acquisition/import contract and license boundary.
3. If image-owned assets/runtime are affected, build the image. Run the canonical preflight/GPU smoke,
   the required accuracy/semantic evaluation, and engine and distribution provenance validation.
4. Release promotion to main follows the [branch policy](BRANCH_POLICY.md). Old cache/rollback assets are not deleted automatically.

For a missing/corrupt candidate, fix the path/checkpoint. For a shape/task/device mismatch, recreate it in a supported format.
A comparison hash mismatch means the model or comparison target changed; do not overwrite an existing comparison result and treat it as passed.
For a runtime mismatch, compare base/image provenance to choose a compatible image, and build only when needed.

## Design rationale and related documents

#329 / PR #331 defined per-version SHAs and operator import, #352 / PR #353 separated the shared cache from runtime/source fingerprints,
and #398 / PR #401 separated production from historical Stage-E components. The exploration and comparison modes in this document keep these production contracts.
Past GPU/accuracy results are treated separately from the validation results of a new candidate.
The current Dockerfile/profile pins HOMR commit `457e7c6518a10ba755db2e60883419e56c4d7369`.
For selected assets and archive hashes, see the [model artifact contract](../contracts/MODEL_ARTIFACT_CONTRACT.md).

The exploration and comparison modes in this document were introduced in #448 / [PR #451](https://github.com/M763468/PDFScoreBar/pull/451).
The initial proposal of a separate selection manifest/dedicated runner and the standalone implementation Issue #450 were
replaced by the [review decision](https://github.com/M763468/PDFScoreBar/pull/451#issuecomment-6400645077).
This history records design decisions; current operating procedures follow the sections of this document and the current source/tests.

The Japanese version of this document is the original, and this English version is placed beside it.
Japanese/English synchronization and placement follow the [documentation language policy](../DOCUMENTATION_LANGUAGE_POLICY.md).
