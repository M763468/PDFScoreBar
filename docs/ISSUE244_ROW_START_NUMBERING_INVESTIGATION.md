# Issue #244 Row-Start Numbering Investigation

## Status

Investigation completed on 2026-07-11.

The investigation branch `fix/issue244-row-start-numbering-investigation` is an evidence branch only. It contains rejected production-default changes and temporary investigation tools and must not be merged into `develop`.

The durable follow-up is Issue #245: restore a fresh upstream detector route without relying on retained historical artifacts.

## Original symptom

PR #243 successfully materialized a clean corrected final PDF, but the displayed row-start measure numbers were wrong.

Observed row starts:

```text
1, 6, 11, 14, 20, 27, 35, 40, 51, 69, 77, 81
```

Expected row starts:

```text
1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89
```

## Confirmed boundaries

### Final materialization is not the cause

The final materializer consumes `numbering_final.json` and renders the recorded row-start labels. It does not recompute measure counts or numbering.

The incorrect values were already present in upstream numbering artifacts.

### The error begins in physical barline/measure construction

For the page-001 smoke case, the ordinary route produced physical measure counts:

```text
5, 5, 3, 6, 7, 8, 5, 6, 10, 8, 4, 6
```

The expected counts were:

```text
5, 5, 5, 7, 7, 8, 5, 7, 10, 8, 5, 6
```

The route therefore missed five physical measures before final numbering propagation. One MMR span was also missing.

### Historical-artifact replay can reproduce the page-001 result

Using retained historical upstream artifacts with dense candidate reconstruction, current CNN scoring, and current MMR logic reproduced the expected page-001 sequence exactly.

This showed that:

- final materialization was correct;
- measure numbering and MMR could produce the expected result when supplied with the historical detector geometry;
- dense reconstruction parameters alone were not sufficient evidence for a production default.

## Rejected production-default experiment

The investigation temporarily implemented a default dense route and a 360 DPI PDF input profile. The page-001 smoke passed, but the required full-68 regression failed substantially.

### Current fresh upstream run

```text
GT=3580
Pred=3713
TP=3533
FP=73
FN=47
FN_det=32
FN_cnn=15
```

### Retained historical Stage E artifact, re-evaluated against current GT

```text
GT=3580
Pred=3600
TP=3579
FP=1
FN=1
FN_det=0
FN_cnn=1
```

The proposed route therefore cannot be adopted as a production default.

## Hybrid prediction and staff-mask cross experiment

The investigation exchanged historical/current hybrid predictions and historical/current staff masks while keeping the remaining dense reconstruction and CNN contract fixed.

```text
A: historical predictions + historical mask
   TP=3579 FP=1  FN=1

B: current predictions + current mask
   TP=3533 FP=73 FN=47

C: historical predictions + current mask
   TP=3577 FP=1  FN=3

D: current predictions + historical mask
   TP=3538 FP=67 FN=42
```

Interpretation:

- Current hybrid predictions are the primary regression source.
- Current staff-mask selection is a smaller secondary contributor.
- Restoring only the historical staff mask does not recover the detector contract.

## Source-layer comparison

The historical and current runs used identical input images for all 68 pages. The first semantic divergence occurred at baseline HOMR on all 68 pages.

| Layer | Historical boxes | Current boxes | Tolerant matches | Historical only | Current only |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline HOMR | 4,381 | 10,229 | 3,912 | 469 | 6,317 |
| SR-side HOMR | 3,356 | 4,635 | 3,238 | 118 | 1,397 |
| OMR-DLN | 5,820 | 5,984 | 5,385 | 435 | 599 |
| hybrid | 3,312 | 4,064 | 3,183 | 129 | 881 |

Reapplying the current consensus implementation reproduced both the retained historical hybrid outputs and the current hybrid outputs on 68/68 pages.

Therefore:

- hybrid consensus is not the primary source of drift;
- the baseline/SR/OMR source artifacts already differ;
- the largest upstream difference is baseline HOMR;
- a high-accuracy production contract must include reproducible upstream model, runtime, preprocessing, provider, and mask provenance, not only dense-route thresholds and PDF DPI.

## Relationship to the Issue #120 reconstruction work

This result is consistent with the earlier Issue #120 boundary:

- #147 established that fresh upstream regeneration did not preserve the historical detector target.
- #149 recovered a reproducible dense candidate validation route from an inventory and retained source artifacts.
- #141 validated a full-pipeline checkpoint (see [Stage E Full Pipeline Report](ISSUE141_STAGE_E_FULL_PIPELINE_REPORT.md)), but this did not prove that arbitrary fresh inputs regenerate the same upstream artifacts without retained historical inputs.

The Issue #244 investigation exposed the same unresolved boundary through the current corrected-final user workflow.

## Durable decisions

1. Do not merge the Issue #244 investigation branch.
2. Do not adopt `production_dense_v1` or the temporary default dense-route implementation.
3. Do not describe dense parameters plus 360 DPI as a complete production accuracy contract.
4. Keep the current production defaults unchanged until a fresh full-68 route passes detector, physical-measure, MMR, and corrected-final gates.
5. Track fresh upstream detector reproduction in #245.
6. Keep generated comparison reports and full-run artifacts under ignored `logs/` paths; this document records only the durable conclusions.

## Follow-up acceptance boundary

Issue #245 must start from canonical PDFs/images and regenerate all upstream artifacts without retained historical detector inputs. Before any production-default change, it must demonstrate:

- full-68 detector comparison against current GT;
- page-level detector and physical-measure comparison;
- post-#221 MMR regression;
- preservation of known guard cases;
- expected page-001 corrected-final row starts:

```text
1, 6, 11, 16, 23, 30, 38, 43, 58, 76, 84, 89
```
