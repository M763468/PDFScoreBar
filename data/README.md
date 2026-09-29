# Data directory policy

Tracked repository data is limited to evaluation/reference assets that are intentionally part of
current validation or reproducibility.

## Canonical barline evaluation data

`data/evaluation2/**` is the maintained barline GT/evaluation surface.

Structure:

```text
data/evaluation2/
  images/<work>/page_xxx.png
  annotations/<work>/page_xxx/
    raw_boxes.json
    boxes_sorted.json
  staff_units.json
  golden_baseline_eval2_bc23deb/
```

The canonical GT contains five works / 68 retained pages. `boxes_sorted.json` is the primary
barline GT consumed by current evaluation/validation workflows; `raw_boxes.json` remains the
editable/manual-label source where retained.

Use `tools/gt_relabel_gui/evaluation2_config.json` and the workflow documented under
`tools/verification/gt_preparation/README.md` when maintaining this GT.

## Generated and operator-owned data

Operator PDFs, rendered page images, temporary crops, workbench material, and local datasets are not
tracked repository surface. Keep them outside Git or under the ignored/generated locations defined
by repository tooling.

The old tracked `data/training/**`, `data/evaluation/**`, and `data/workbench/**` layouts were
retired by Issue #381 after the evaluation2 workflow became canonical. Their historical bytes remain
recoverable from Git history; do not recreate those directories as current GT locations.

For ad-hoc scratch work, follow `docs/SCRIPT_MANAGEMENT.md` and use ignored `tmp/` rather than a
tracked workbench tree.

## Retention rule

Do not add new tracked datasets merely because a tool can read them. Track data only when a current
validation/reproduction contract explicitly requires the bytes to remain in the repository, and
document that role at the same time.
