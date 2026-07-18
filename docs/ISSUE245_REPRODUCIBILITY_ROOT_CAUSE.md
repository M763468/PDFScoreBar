# Issue #245 detector reproducibility root cause

## Status

Issue #245 established that two different detector input contracts had repeatedly
been discussed under similar names. This made a retained checkpoint regression look
like proof that newly supplied PDFs could reproduce the same detector accuracy.

The large investigation history is preserved at:

```text
archive/issue245-investigation-20260719
```

The durable changes extracted from that branch are limited to an explicit detector
input contract, a per-run manifest, focused tests, and this record.

## The two contracts

### Checkpoint reconstruction

The accepted Issue #120 detector metrics were recovered through a route equivalent
to:

```text
benchmark inventory
  -> retained hybrid_predictions
  -> dense candidate reconstruction
  -> candidate filtering and probe rescue
  -> CNN scoring
```

The generated candidate files were new, but their authoritative existing boxes came
from retained `hybrid_predictions` referenced by the inventory.

The Stage E wrapper then configured:

```text
detection.precomputed_probe_candidates_root
detection.cnn_bands_from
```

This route remains useful for historical checkpoint regression, CNN comparison, and
downstream isolation. It does not demonstrate that current HOMR/SR/OMR output from
a newly supplied PDF reproduces the checkpoint.

### Fresh upstream regeneration

A fresh detector run starts from the input images and makes the current
HOMR/SR/OMR hybrid output authoritative for both:

- probe candidate generation;
- CNN band geometry.

For this contract, both candidate-source overrides must be unset:

```text
precomputed_probe_candidates_root is unset
cnn_bands_from is unset
```

## Why the distinction was repeatedly lost

### Similar route names

Terms such as “full pipeline”, “freshly reconstructed”, and “production-oriented”
described execution or wiring, but did not identify which artifact was authoritative
for detector candidates.

### Silent candidate-source overrides

The orchestrator can run HOMR/SR/OMR and then bypass the resulting hybrid geometry by
copying precomputed probe candidates. `cnn_bands_from` can separately replace the
current hybrid bands used during CNN scoring. Console logs alone therefore cannot
prove that a run is fresh.

### New output was confused with fresh input

Writing candidate JSON into a new run directory does not prove fresh provenance when
the seed geometry comes from a retained inventory record.

### Metrics omitted source identity

TP/FP/FN, page counts, thresholds, and NMS settings were recorded, but the
machine-readable result did not identify the authoritative candidate source. Runs
with different input contracts could therefore be compared under the same baseline
name.

### Focused success was promoted too early

The Issue #245 aligned-expansion experiment restored focused Shostakovich and
Sibelius targets. On fresh `Va_Prokofiev_Symphony1/page_004`, however, it selected
131 rescues for 155 existing boxes, introduced two false positives, and still did
not restore the remaining detector target.

That experiment is retained only on the archive branch. It is not included in the
clean remediation branch and must not be enabled in a canonical config without a
fresh full-68 and downstream regression.

## Historical boundary

The earlier Issue #244 investigation had already shown that:

- the first semantic divergence between retained and current source layers occurred
  at baseline HOMR;
- retained candidate replay reproduced the expected numbering;
- current fresh HOMR/SR/OMR did not preserve the accepted detector contract.

Issue #245 did not discover a new regression. It exposed that the unresolved fresh
boundary had been masked by the checkpoint reconstruction route.

## Enforced machine contract

`src/pipeline/detection/input_contract.py` classifies every detector configuration as
one of:

```text
fresh_upstream
precomputed_candidate_route
```

A run is classified as `precomputed_candidate_route` when either
`precomputed_probe_candidates_root` or `cnn_bands_from` is configured.

`DetectorOrchestrator` writes the classification before detector execution to:

```text
<run_dir>/intermediate/detector_input_contract.json
```

The manifest records:

- mode;
- whether fresh upstream is authoritative;
- whether current hybrid output is authoritative for probe generation;
- whether current hybrid output is authoritative for CNN bands;
- configured override paths and keys.

A result must not be described as a fresh detector validation unless the manifest
reports:

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
```

## Promotion rules

1. Experimental detector changes remain default OFF.
2. Focused pages establish a mechanism, not production safety.
3. A canonical detector config change requires a fresh upstream full-68 result.
4. Detector, physical-measure, MMR, guard-case, and corrected-final results remain
   separate gates.
5. Every claimed metric must state the detector input mode and override keys.
6. Checkpoint metrics and fresh metrics must not share an unlabeled baseline name.
7. Each fresh validation uses a new output root and records external model/runtime
   provenance.

## Scope after branch cleanup

The clean remediation branch intentionally excludes:

- aligned-expansion production changes;
- same-file staff/clef experiments;
- OMR/SR bootstrap work;
- the large `tools/issue245` investigation suite;
- fresh Prokofiev accuracy repair.

Those artifacts remain available on the archive branch. The remaining Prokofiev
miss should be handled by a new narrow issue that identifies the first fresh layer
where the target geometry or its containing row disappears before proposing a
source-general repair.
