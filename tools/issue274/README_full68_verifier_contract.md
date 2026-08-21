# Issue #274 — full68 verifier contract and false-negative gate history

This note records why the first two post-hoc full68 topology checks returned a failing gate even though the fresh two-HOMR production run itself completed successfully. It is intentionally separate from the detector/HOMR implementation so that a later verifier change cannot be mistaken for changing the acceptance criterion merely to obtain a passing result.

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

`verify_two_homr_full68_numbering_posthoc.py` corrected only the fresh-side path assumption by reading the actual per-page Phase-C files:

`runs/<score>/outputs/<page_id>/numbering_final.json`

That change correctly established that the fresh run contains 68/68 per-page final-numbering outputs. However, it retained the same invalid assumption on the control side and looked for:

`<detector-control-root>/<score>/outputs/<page_id>/numbering_final.json`

The resulting report therefore showed:

- fresh numbering pages: 68
- control numbering pages: 0
- topology comparison: unavailable on all 68 pages

This second failure is useful evidence about the control artifact contract; it is not evidence for or against the two-HOMR architecture.

## Correct topology evidence chain

Do not create a new comparator that simply weakens the topology requirement.

Issue #274 already has an independent retained-artifact CPU-only audit, `analyze_b_downstream_semantic_equivalence.py`, created before the fresh full68 run. It reconstructs both the retained control and the current-x4/B accepted barline sets through the same production `MeasureNumberingPipeline`, with the same authoritative A/original staff-mask contract and connector evidence. Its full68 result is:

- base-numbering topology unchanged: 68/68 pages;
- focused detector multiplicity differences collapse to the same downstream x identity.

The fresh full68 run should therefore be checked as a two-link chain rather than by assuming nonexistent control numbering files:

1. **Independent retained audit:** control topology == retained B/current-x4 topology on 68/68 pages.
2. **Fresh production audit:** actual fresh per-page `numbering_base.json` topology == the retained B/current-x4 topology signature on 68/68 pages.

Only if both links pass may the fresh run claim downstream topology equivalence. The second link must compare actual fresh production outputs, not recompute a convenient replacement output.

If the retained semantic audit artifact is unavailable or its provenance/page set does not match the expected 68 pages, the topology status is **unverified**, not passed.

## Cleanup rule

Before Issue #274 is merged, temporary verifier code must be consolidated so that:

- detector-only baselines are never treated as numbering-pipeline baselines;
- missing comparison artifacts are reported as an artifact-contract/precondition error rather than a functional regression;
- a gate cannot silently switch from raw GT slot cardinality to audited physical-event coverage without recording both values and the audit provenance;
- obsolete v2/v3 post-hoc paths are removed or clearly deprecated after the final verifier is established.
