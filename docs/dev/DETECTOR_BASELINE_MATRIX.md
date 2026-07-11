# Detector Baseline Matrix

This document separates verified historical detector evidence from proposed
production runtime routes. It must not describe a route as production-ready
until the full regression gates have passed.

> [!CAUTION]
> The Issue #244 `production_dense_v1` implementation is **not an accepted
> production default**. A one-page replay passed, but the current-run full-68
> regression failed materially. Do not merge, deploy, or copy this route as a
> user-facing default until the upstream hybrid-artifact discrepancy is resolved
> and the complete regression is rerun.

## Current status

Issue #244 established three separate facts:

1. The ordinary smoke route produced incorrect row-start numbering on
   `Va_Prokofiev_Symphony1/page_001`.
2. Replaying that page from the canonical Issue #120 inventory, with the dense
   reconstruction route and the retained 3600 x 4680 evaluation image, exactly
   reproduced the expected physical measures, MMR overrides, and row starts.
3. Reconstructing dense candidates from **newly generated current-run hybrid
   artifacts** did not reproduce the historical 68-page detector or MMR
   baselines.

The third result invalidates the assumption that dense numeric parameters and
360 dpi alone define the historical high-accuracy route.

## Full-68 rejection evidence

The proposed default route was evaluated on the canonical 68-page set against
the retained Stage E artifact re-evaluated with current GT.

| Metric | Current-GT historical baseline | Proposed current-run dense route |
|---|---:|---:|
| TP | 3579 | 3533 |
| FP | 1 | 73 |
| FN | 1 | 47 |
| Precision | 0.999721 | 0.979756 |
| Recall | 0.999721 | 0.986872 |
| Candidate count | 29772 | 28919 |

The MMR regression also failed:

| Metric | Expected post-#221 baseline | Proposed current-run dense route |
|---|---:|---:|
| Base measures | 3325 | 3310 |
| Matched TP | 173 | 96 |
| Missed FN | 3 | 78 |
| Skip mismatch | 6 | 8 |
| Unexpected FP | 0 | 68 |

The page-033 one-bar veto remained present, but that isolated success does not
make the route acceptable.

## Verified and unverified route roles

| Surface | Status | Production default? | Notes |
|---|---|---:|---|
| Retained Stage E artifact | Verified historical evidence | No | Reproduces the historical detector route when re-evaluated under the applicable GT contract |
| Canonical-inventory dense replay | Verified detector/page replay | No | Depends on inventory-recorded upstream hybrid predictions and masks |
| Current-run `production_dense_v1` reconstruction | Rejected by full-68 regression | No | Fresh hybrid predictions/masks diverge before dense candidate and CNN stages |
| `configs/dense_full_pipeline.yaml` | Investigation/reference config | No | Parameter reference only; not proof of full runtime reproduction |
| `configs/evaluation2_e2e_verification_full.yaml` | Evaluation smoke input | No | Must not silently imply an accepted production route |
| `detection.route: precomputed` | Historical/reproduction injection | No | Requires explicit external artifacts |
| Ordinary route | Existing runtime baseline | Not a high-accuracy target | Known to fail the Issue #244 page-001 numbering case |

## Missing production contract

A valid high-accuracy default must reproduce the complete upstream-to-downstream
contract, including at least:

- PDF/image resolution and image bytes;
- hybrid prediction generation;
- staff and clef/key mask generation;
- dense candidate generation and filtering;
- probe-rescue candidate generation;
- CNN model, threshold, crop behavior, and NMS policy;
- system/measure construction;
- MMR model and OCR behavior.

The retained audit already warned that regeneration of slow upstream
HOMR/OMR/SR-derived artifacts had not been proven. Issue #244 must resolve that
boundary instead of treating retained inventory artifacts as equivalent to
fresh production output.

## Corrected reruns

Corrected reruns must eventually inherit the same verified high-accuracy
runtime contract as initial runs. They must not reuse stale run-local generated
paths. However, this propagation must not be enabled as the default until the
full route itself passes regression.

## Required regression before approval

Approval requires all of the following on the same implementation:

- focused route/default, input-profile, and corrected-rerun tests;
- the Issue #244 page-001 PDF replay;
- full-68 detector evaluation against the current-GT historical baseline;
- page-level detector metric comparison;
- Issue #206 guard cases;
- downstream physical measure-count comparison;
- Issue #221 MMR baseline;
- page-033 one-bar veto;
- manual-correction and corrected-final focused tests.

A one-page success or a historical retained artifact alone is insufficient.
