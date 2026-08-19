# Issue #274 — evaluation2 GT near-duplicate audit

This audit exists because the current-x4 B route loses four one-to-one detector matches
relative to the pinned-x4 C control, while full68 downstream measure topology is unchanged.
Before adding detector rules to recreate extra hypotheses, verify whether those GT pairs are
valid under the repository's current GT policy.

## Policy boundary

`docs/GT_PREPARATION_POLICY.md` is the normative labeling policy used by this audit:

- one **physical vertical line** is the minimum bbox unit;
- a normal single line is `barline`;
- double/final/repeat events use semantic labels;
- multiple physical lines in a double/final event are represented by independent bboxes.

Therefore two ordinary `barline` bboxes that substantially overlap in **both x and y** are
review candidates. They are not automatically valid merely because a later detector issue
called them "Divisi" or because one-to-one evaluation counts both.

A genuine double bar is expected to show distinct physical x-columns, e.g. two adjacent
vertical strokes, and should carry the relevant semantic type where the GT was curated under
the current policy.

## Provenance already established

The focused Issue #274 pairs:

- exist in `raw_boxes.json`, so sorting did not create them;
- also exist in `boxes_provisional.json`, so they came from the v13 candidate seed and were
  retained during manual GUI curation rather than being newly drawn by hand;
- were saved as ordinary `barline` records.

The GT rebuild history is Issue #16 / commit `5911a6c`: 68 evaluation2 pages were rebuilt
from v13 candidate seeds and manually curated in `tools/gt_relabel_gui`.

The browser GT editor already had an **Auto Dedup** button at that time. Its current and
historical rule is:

- x-center difference <= 3 px;
- vertical overlap / shorter bbox height >= 0.7;
- keep the taller bbox.

This button is optional; save does not run it automatically. Consequently near-duplicate
seed hypotheses can remain in final GT if Auto Dedup is not invoked for that page/pair.

## Automated audit

Run:

```bash
python3 tools/issue274/audit_evaluation2_gt_near_duplicates.py
```

The tool is audit-only and never modifies authoritative annotations.

Default outputs:

```text
logs/issue274_homr_unification_analysis/evaluation2_gt_near_duplicate_audit_01/
  issue274_evaluation2_gt_near_duplicate_audit.json
  issue274_evaluation2_gt_near_duplicate_review.csv
  evaluation2_gt_near_duplicate_review_config.json
  crops/...
  gui_review/...                 # only created if the review GUI saves changes
```

Classification:

- **P0 exact_duplicate** — identical bbox repeated; strongest correction candidate.
- **P1 ordinary_same_ink_high_overlap** — two plain `barline` boxes substantially overlap in
  x and overlap >=70% of the shorter box in y; strong policy-conflict candidate.
- **P2 ordinary_close_parallel_high_overlap** — close x, high y overlap, but not enough bbox x
  overlap to call same ink automatically; may be an unlabeled double/final event or duplicate.
- **P2 ordinary_same_x_partial_overlap** — bbox x regions overlap but y overlap is only partial;
  inspect for actual split-staff/divisi structure versus seed duplication.
- **P3 declared_multiline_event_pair** — semantic multi-line event; informational check that
  the boxes really cover distinct physical strokes.

No class is automatically deleted by the audit.

## Browser review GUI

Use the generated config with the existing GT editor:

```bash
python3 tools/gt_relabel_gui/server.py \
  --mode gt \
  --root . \
  --config logs/issue274_homr_unification_analysis/evaluation2_gt_near_duplicate_audit_01/evaluation2_gt_near_duplicate_review_config.json \
  --host 127.0.0.1 \
  --port 8010
```

Open `http://127.0.0.1:8010`.

The review config deliberately uses the authoritative `raw_boxes.json` only as the editable
**input**. Saving writes review copies under `logs/.../gui_review/`; it does not overwrite
`data/evaluation2/annotations`.

The provisional seed is shown as a reference layer. This helps distinguish:

- seed duplicates that survived curation;
- manually moved/resized boxes;
- genuinely independent physical lines.

Do **not** run Auto Dedup blindly across all review pages. Review P0/P1 first. P2 pairs need
visual classification, especially where true double/final barlines are possible.

## Decision after review

If a pair violates the GT policy, fix the GT in a separate correction commit and rerun the
existing detector evaluation against the corrected annotations **without changing detector
logic first**.

If a pair is a valid distinct musical event, document why it is distinct and only then decide
whether Issue #274 needs a detector/support change.

GT correction and the HOMR architecture change must stay causally separate: do not add a
PDFScoreBar detector filter merely to reproduce an annotation artifact.
