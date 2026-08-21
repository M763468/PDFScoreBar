# Issue #274 — full68 verifier contract and false-negative gate history

This note records why several post-hoc full68 topology checks returned a failing gate even though the fresh two-HOMR production run itself completed successfully. It is intentionally separate from the detector/HOMR implementation so that a later verifier change cannot be mistaken for changing the acceptance criterion merely to obtain a passing result.

## Detector FN=6: what it means

The fresh two-HOMR run reproduces the retained current-x4/B raw-slot signature against the current authoritative evaluation2 GT:

- control: greedy TP=3579, FP=1, FN=1
- fresh/current-x4: greedy TP=3574, FP=1, FN=6

This is **not** a result of changing GT during Issue #274. The authoritative GT remains unchanged by these gates.

The full68 GT audit separated the raw one-to-one annotation slots into physical-event classes:

- P1 `ordinary_same_ink_high_overlap`: 12 pairs on 10 pages; these are near-duplicate ordinary boxes on the same physical ink and all originate from the provisional seed;
- P3 declared multi-line events: genuine double/final/repeat physical lines, kept separate.

Four of the five additional raw FN relative to the control are P1 duplicate slots. The remaining apparent delta is on `Va_Prokofiev_Symphony1/page_004`, where the physical double-barline evidence exists in both variants and the legacy greedy matcher assignment is order-sensitive.

Under the audited physical-event interpretation, control and fresh are identical:

- physical events: TP=3567, FN=1 out of 3568;
- singleton events: TP=3555, FN=1 out of 3556;
- P1 events: TP=12, FN=0;
- P3 physical lines: TP=101, FN=1 out of 102;
- changed physical-coverage pages: 0.

Therefore Issue #274 does not treat raw `FN=6` as a new physical detector regression. This is an **evaluation-contract clarification**, not a GT rewrite. Historical GT corrections that changed the older 3584-box set to the current 3580-box set are separate prior work and are not the mechanism by which this gate passes.

## Why the original full68 verifier was wrong

`verify_two_homr_full68_fresh.py` correctly checks the fresh architecture, detector coverage, and downstream support reuse. Its first topology check made an invalid artifact-layout assumption:

1. `DEFAULT_CONTROL_ROOT` points to the retained Issue #255 **detector full68** run.
2. That root is suitable for reading accepted detector barlines used as the control.
3. It is **not** a completed numbering-pipeline run and does not provide the score-level `outputs/numbering_final.json` + numbering manifest contract assumed by the verifier.
4. The verifier interpreted missing control numbering artifacts as missing/changed topology, so all 68 pages failed the topology subgate.

This failure did not show a production topology regression; it showed that the verifier asked a detector-only baseline for artifacts outside that baseline's contract.

## Why the first post-hoc repair was also wrong

`verify_two_homr_full68_numbering_posthoc.py` first corrected only the fresh-side path assumption by reading the actual per-page Phase-C files:

`runs/<score>/outputs/<page_id>/numbering_final.json`

That change correctly established that the fresh run contains 68/68 per-page final-numbering outputs. However, it retained the same invalid assumption on the control side and looked for:

`<detector-control-root>/<score>/outputs/<page_id>/numbering_final.json`

The resulting report therefore showed:

- fresh numbering pages: 68
- control numbering pages: 0
- topology comparison: unavailable on all 68 pages

This second failure is useful evidence about the control artifact contract; it is not evidence for or against the two-HOMR architecture.

## Why the v4 retained semantic audit was not a current-production baseline

The next repair used `analyze_b_downstream_semantic_equivalence.py` as a two-link reference. That audit was useful for proving that the B/current-x4 detector multiplicity differences did not change the downstream result under the retained artifacts available at that time. It is **not**, however, a valid post-PR #265 current-production numbering baseline.

The reason is visible in the production code.

`connector_mask_paths_for_numbering()` resolves the current-support `symbols` / `brace_dot` pair from the nearest `current_support` subtree. `MeasureNumberingPipeline._connector_evidence_staves()` then derives a sibling `*_staff_mask.png` path from the resolved symbols path. That sibling current-HOMR staff mask is used for connector-evidence ROIs only when its extracted staff count equals the authoritative A/Proxy numbering staff count. If the counts differ, production deliberately falls back to the A/Proxy staff geometry before evaluating the connector masks.

The old Issue #255 current-support artifacts predate PR #265's coordinate fix. The residual audit showed:

- `Va_Prokofiev_Symphony1/page_004`: old semantic staff extracts 235 components, fresh post-#265 semantic staff extracts 13;
- `Va__Prokofiev_Symphony5/page_022`: old semantic staff extracts 173 components, fresh post-#265 semantic staff extracts 11;
- connector `symbols` and `brace_dot` mask bytes are identical between retained and fresh for both pages.

Therefore the old retained semantic audit and the fresh run execute different production branches:

```text
old Issue255 current-support
  -> sibling semantic staff is stale x4/SR-space
  -> semantic staff count != A/Proxy staff count
  -> _connector_evidence_staves() returns A/Proxy geometry
  -> connector masks are measured with A/Proxy ROIs

fresh post-PR265 current-support
  -> sibling semantic staff is restored to source-page coordinates
  -> semantic staff count == A/Proxy staff count on the focused residual pages
  -> _connector_evidence_staves() returns current-HOMR semantic geometry
  -> connector masks are measured with current-HOMR semantic ROIs
```

This fully explains why switching only the connector artifact **path** changed the earlier reconstruction despite identical connector-mask hashes. The path selects the sibling semantic staff geometry, and the staff-count guard decides whether production uses it or falls back.

PR #265 explicitly fixed this contract by restoring current-HOMR staff/notehead masks from x4 SR-space to source-page coordinates before persistence and by using the matching current-HOMR staff geometry only for connector-evidence ROIs. Its accepted focused `Va_Prokofiev_Symphony1/page_004` result is the same as the fresh two-HOMR run: membership `[1,1,1,1,1,1,2,1,1,1,1,1]` and 101 physical measures. The earlier v4 comparison's 13-system / 111-measure reference is stale-artifact fallback behavior, not the accepted current-production Phase-A result.

Issue #274 had already declared the merged Issue #264 Phase-C state as the regression baseline. The v4 verifier violated that requirement by substituting the older retained semantic audit.

## Limitation of the first semantic-geometry diagnostic

`diagnose_two_homr_connector_semantic_geometry.py` was useful for exposing the stale-versus-fresh sibling staff masks, but its original cross matrix directly passed extracted semantic staves to `extract_from_mask_maps()`. That bypasses the production `_connector_evidence_staves()` staff-count fallback described above.

Consequently:

- the reported staff-mask hashes/counts are valid forensic observations;
- the reported connector-mask byte identity is valid;
- the raw cross-matrix evidence/topology values must **not** be treated as production replay evidence for the stale retained path.

No additional inference is needed to resolve this point; the production fallback is explicit in code and the stale coordinate-space defect is already the root cause fixed by PR #265.

## Final topology acceptance contract

The final causal gate does not compare two independent production runs. For every canonical page it freezes the actual fresh #274 A/original staff geometry, current-HOMR connector semantic support, and page image, then varies only the accepted detector barline set:

- control: retained C/pinned-x4 accepted barlines;
- candidate: actual fresh two-HOMR B/current-x4 accepted barlines.

Two links are mandatory:

1. the candidate CPU reconstruction must reproduce the actual fresh serialized `numbering_base.json` exactly, excluding only page ordinal;
2. control and candidate must have identical serialized staff grouping, measure-number topology, and empty-system grouping under those same frozen inputs.

Measure-boundary bbox deltas are reported separately and do not replace the topology gate. No HOMR, SR, detector, CNN, MMR, or OCR inference is rerun.

If the candidate reconstruction cannot reproduce the preserved fresh production artifact, the comparison is **unverified** until the replay contract mismatch is understood. The expected answer must not be changed merely to make the gate pass.

## Historical v4/v5 residual accounting

For completeness, v4 initially reported 25 differences because it also compared pre-serialization `page.systems` against serialized production `systems`. Production `score_to_dict()` moves zero-measure systems to `empty_systems`. Canonicalizing that representation reduced the 25 to 23 representation-only differences plus the two stale-semantic-reference differences above.

Those two pages should no longer be described as demonstrated two-HOMR regressions. They demonstrated that v4 chose the wrong retained contract.

v5 then selected an accepted post-PR #265 Phase-C run but compared two independently rerun A/original HOMR segmentations pixel-exactly. Its 68/68 changed result decomposed into 60 pages with only bbox differences, five more with only `empty_systems` segmentation differences, and three pages with active structural differences caused while A geometry also changed. v5 therefore was not a controlled Issue #274 comparison.

## What the first v6 run exposed

The first same-input v6 run is itself retained as verifier evidence. It processed 45 pages successfully and stopped only page-locally on 23 `Connector semantic staff count mismatch` errors. Among the 45 processed pages:

- candidate reconstruction exact: 45/45;
- control/candidate topology exact: 45/45;
- measure geometry within 10 px: 45/45.

There was no observed topology residual. All 23 failures came from the same replay-time exception.

This exception was introduced **after** the preserved fresh full68 production run. At the full68 runner checkpoint `90bb6d24cb6040ef64f495350edbbf38b6f7403c`, `_connector_evidence_staves()` explicitly treated a semantic/current-HOMR staff-count mismatch as a supported producer disagreement: it logged a warning and returned the authoritative A/Proxy numbering geometry for connector-evidence ROIs. That is how the preserved run could legitimately serialize all 68 `numbering_base.json` files.

A later Issue #274 diagnostic hardening changed the mismatch branch to `RuntimeError`. The first v6 run therefore detected a **post-run production-contract drift in the replay code**, not 23 two-HOMR regressions. Restoring the staff-count fallback is not a relaxation of the topology gate; it restores the exact semantic branch under which the candidate artifacts being verified were produced.

The corrected contract distinguishes two cases:

- sibling semantic staff artifact exists but its extracted count differs from A/numbering geometry -> warn and use authoritative A/numbering geometry for connector ROIs;
- sibling semantic staff artifact is missing -> incomplete declared support bundle, hard error.

The 23 mismatch pages remain recorded as evidence of this fallback branch. They must not be described as 23 semantic-geometry matches, but neither are they candidate regressions.

## Cleanup rule

Before Issue #274 is merged, temporary verifier code must be consolidated so that:

- detector-only baselines are never treated as numbering-pipeline baselines;
- pre-PR #265 stale current-support artifacts are never treated as the current Phase-A semantic baseline;
- missing comparison artifacts are reported as an artifact-contract/precondition error rather than a functional regression;
- serialized `systems` are never compared directly with pre-serialization `page.systems` without normalizing the `empty_systems` contract;
- connector semantic provenance records both connector-mask artifacts and the semantic staff geometry/fallback used to define their ROIs;
- legitimate staff-count fallback is recorded separately from a missing/incomplete support bundle;
- a gate cannot silently switch from raw GT slot cardinality to audited physical-event coverage without recording both values and the audit provenance;
- obsolete v2/v3/v4/v5 interpretations remain documented as superseded rather than being silently rewritten.
