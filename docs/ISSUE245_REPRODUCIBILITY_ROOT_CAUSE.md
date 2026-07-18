# Issue #245 detector reproducibility root cause

## Status

This document records why accepted detector accuracy has repeatedly failed to
reproduce from newly supplied PDFs even though earlier Issue #120 work reported a
successful 68-page Stage E contract.

The central finding is that two different contracts were repeatedly discussed
under similar names:

1. **Checkpoint reconstruction**: rebuild probe candidates from an inventory that
   references retained `hybrid_predictions`, then inject those candidates into the
   detector/CNN route.
2. **Fresh upstream regeneration**: start from canonical PDF images and make the
   current HOMR/SR/OMR hybrid output authoritative for probe generation and CNN
   band geometry.

Only the first contract had reached the historical detector metrics. It does not
establish that the second contract is reproducible.

## Evidence from the Issue history

### #147: the fresh Stage D boundary was already unresolved

Issue #147 started because regenerated upstream artifacts did not preserve the
historical Stage D target. A historical worktree could reproduce raw probe
candidate generation byte-for-byte, but filtered output initially diverged. The
remaining filter difference was traced to historical execution details such as
clef-mask resolution.

This was an artifact-provenance recovery result. It was not evidence that current
HOMR/SR/OMR outputs matched the historical detector sources.

### #149: the accepted detector target came from an inventory route

Issue #149 recovered this chain:

```text
20260208 bench inventory
  -> generate_probe_candidates_from_inventory.py
  -> clef-mask-aware candidate filtering
  -> probe-rescue reconstruction
  -> CNN scoring
  -> TP=3580 / FP=0 / FN=1
```

The candidate generator reads these paths directly from each inventory record:

```text
record["image"]
record["staff_mask"]
record["hybrid_predictions"]
```

The `hybrid_predictions` value is the authoritative existing-box input to probe
candidate generation. Therefore the route reproduces a retained detector
checkpoint; it does not regenerate those hybrid predictions from a new PDF.

### #151: productionization preserved a partial route

Issue #151 explicitly described the formal dense route as a detector-level
partial route. It did not run the slow HOMR/SR/OMR upstream pipeline or prove
fresh source equivalence.

### #141/#156/#158: terminology obscured the remaining boundary

The first real HOMR/SR/OMR-inclusive Stage E run failed substantially:

```text
TP=3359 FP=145 FN=222
FN_det=222 FN_cnn=0
```

The later Stage E repair reached the accepted metrics by reconstructing candidates
from the inventory route and assigning:

```text
detection.precomputed_probe_candidates_root = reconstructed probe root
detection.cnn_bands_from = reconstructed filtered root
```

The orchestrator still ran hybrid detection, but the current hybrid output was no
longer authoritative for probe candidates or CNN band geometry. As a result,
phrases such as "full pipeline", "freshly reconstructed", and
"production-oriented route" were technically true only for execution/wiring,
not for detector input provenance.

Issue #158 generalized the route names but did not remove these candidate-source
overrides. This made the checkpoint route easier to mistake for the fresh user
route.

### #244: the unresolved boundary reappeared in the user workflow

Issue #244 compared retained and current source layers and found the first
semantic divergence at baseline HOMR on all 68 pages. Historical candidate
replay reproduced expected numbering, while current fresh HOMR/SR/OMR did not.

This was not a new regression. It exposed the same fresh/checkpoint distinction
that had remained unresolved after #147 and #141.

### #245: a focused rescue was promoted too early

The aligned-expansion rescue restored two focused CNN targets. It was then enabled
in canonical configs before a source-general safety gate passed.

On fresh `Va_Prokofiev_Symphony1/page_004`, it selected 131 rescues for 155
existing boxes, produced two focused false positives, and still did not restore
the remaining detector target. This demonstrates why focused-page success cannot
serve as a production promotion gate.

The rescue implementation remains available for controlled experiments, but the
canonical configs keep it disabled until a fresh full-68 and downstream gate
passes.

## Why the same failure kept recurring

### 1. Metrics did not identify the authoritative detector source

The machine-readable evaluation contract recorded page counts, TP/FP/FN, and CNN
settings, but did not state whether probe candidates came from current hybrid
outputs or a precomputed root. Two runs with fundamentally different source
contracts could therefore be compared as if they were equivalent.

### 2. Candidate-source overrides were silent

`precomputed_probe_candidates_root` bypasses probe generation from current hybrid
outputs. `cnn_bands_from` can separately replace current hybrid band geometry for
CNN scoring. The orchestrator still executes hybrid detection, so logs alone can
make the run appear fresh.

### 3. "Generated during this run" was confused with "generated from fresh sources"

The dense candidate files were newly written under the current run directory, but
their authoritative existing boxes came from inventory-referenced retained hybrid
predictions. New output timestamps do not establish fresh input provenance.

### 4. Durable records kept conclusions, not complete executable identity

Large artifacts and detailed manifests correctly remained under ignored `logs/`,
but later sessions often retained only metric summaries. Missing or weakly bound
items included input artifact hashes, model hashes, environment identity, source
mode, and the exact relationship between inventory records and generated roots.

### 5. Validation was split across issues without one clean-room owner

Different issues owned provenance recovery, detector-level reconstruction,
production naming, full-pipeline execution, and accuracy repair. Each issue could
satisfy its local acceptance criteria while the clean-checkout/new-PDF contract
remained unproven.

### 6. Tests primarily validated wiring

Mocked orchestrator tests and helper tests were valuable, but did not verify that
current HOMR/SR/OMR outputs were authoritative. The real GPU full-68 gate was
manual and expensive, so config promotion could occur before that gate.

### 7. External runtime inputs were not fully bootstrapped

The OMR-DLN measure model and some SR/CNN weights live outside Git. Missing model
weights, worktree-local paths, container mounts, and provider/runtime differences
made reruns environment-dependent even before accuracy was evaluated.

## Enforced contracts

### Fresh upstream contract

A run is fresh only when both conditions hold:

```text
precomputed_probe_candidates_root is unset
cnn_bands_from is unset
```

In this mode, the current hybrid output is authoritative for both probe generation
and CNN band geometry.

`src/pipeline/detection/input_contract.py` classifies this mode as:

```text
fresh_upstream
```

The Issue #245 fresh full-68 runner rejects candidate-source overrides before it
creates an output directory.

### Checkpoint/precomputed contract

A run with either candidate-source override is classified as:

```text
precomputed_candidate_route
```

Such runs remain useful for historical regression, CNN comparison, or downstream
isolation. They must not be cited as evidence that newly supplied PDFs reproduce
the historical detector contract.

## Promotion rules

1. Experimental detector changes remain default OFF.
2. Focused pages may establish mechanism, not production safety.
3. A canonical config change requires a fresh upstream full-68 result.
4. Detector, physical-measure, MMR, guard-case, and corrected-final gates remain
   separate and must all be reported.
5. Every claimed result must state the detector input mode and candidate-source
   override keys.
6. A new output directory is required for each fresh validation run.
7. Checkpoint metrics and fresh metrics must not share an unlabeled baseline name.

## Current technical direction

The broad aligned-expansion rescue is not the next default fix. The remaining
Prokofiev target is absent before CNN and is not recovered by the rescue. The next
investigation should trace that single target through fresh baseline HOMR, SR-side
HOMR, OMR-DLN, hybrid consensus, row-band construction, existing suppression,
and probe generation while keeping the canonical rescue disabled.

The objective is to identify the first layer where the target or its containing
row disappears. Only a source-general repair at that boundary should proceed to
focused and full-68 gates.
