# Data ディレクトリ運用ガイド

## Canonical retained evaluation data

Current tracked barline evaluation/GT lives under `data/evaluation2/**`.

Typical layout:

```text
data/evaluation2/
  images/<work>/page_xxx.png
  annotations/<work>/page_xxx/raw_boxes.json
  annotations/<work>/page_xxx/boxes_sorted.json
  staff_units.json
  golden_baseline_eval2_bc23deb/...
```

`data/evaluation2/**` is retained repository evidence used by validation, regression analysis, and
historical reproduction. Do not treat it as disposable generated output.

### evaluation2 GT workflow

- `raw_boxes.json`: GUI save/restart source for editable GT.
- `boxes_sorted.json`: sorted canonical barline GT used by evaluation/training/validation.
- Non-score pages may intentionally be absent.
- Current GT rebuild/editing guidance is documented under
  `tools/verification/gt_preparation/README.md` and the GT relabel GUI workflow.

The retained 2026-02-22 snapshot covers 5 works / 68 pages and 3584 sorted barline boxes.

## Operator and scratch data

Large operator PDFs, rendered pages, temporary captures, draft GT, caches, and generated experiment
material are local data and should not be committed unless an explicit retention decision says
otherwise.

- Pass PDF/image paths explicitly through config or CLI arguments.
- Use ignored `tmp/` for throwaway local work.
- Use Issue-scoped `logs/issue<N>/...` for retained generated evidence according to `AGENTS.md`
  and `logs/README.md`.
- Do not recreate the retired tracked `data/training/**`, `data/evaluation/**`, or
  `data/workbench/**` scaffolding solely to preserve old defaults.

> Note: `tools/coordinate_annotator.py` is LEGACY. Current GT editing uses
> `tools/gt_relabel_gui`.
