# Issue #201 manual correction GUI

This document records the first GUI implementation for the #201 manual-correction workflow.

## Decision

The manual-correction editor is implemented as a sibling mode under `tools/gt_relabel_gui`, not as a replacement for the existing `gt` or `rest` modes.

The existing modes keep their current output contracts:

- `gt`: edits barline GT boxes and writes raw/sorted GT payloads.
- `rest`: edits the older page-local multi-rest GT payload.

The new `manual` mode writes the durable #201 correction schema under `data/evaluation2/manual_corrections/`.

## Files

```text
tools/gt_relabel_gui/server.py
tools/gt_relabel_gui/index_manual.html
tools/gt_relabel_gui/app_manual.js
tools/gt_relabel_gui/manual_config_builder.py
```

## Config

Build a one-page config:

```bash
PYTHONPATH=. python3 tools/gt_relabel_gui/manual_config_builder.py \
  --image data/evaluation2/images/<work>/page_015.png \
  --numbering logs/.../numbering_base.json \
  --name <work>_page_015 \
  --page 15 \
  --output data/evaluation2/manual_correction_config.json
```

For `remove_barline`, add a `barlines` field to the generated config page if a detected-barline artifact is available:

```json
{
  "pages": [
    {
      "name": "Va__Prokofiev_Symphony5_page_015",
      "page": 15,
      "image": "data/evaluation2/images/Va__Prokofiev_Symphony5/page_015.png",
      "numbering": "logs/.../numbering_base.json",
      "barlines": "logs/.../pipeline2_no_peak_scored.json"
    }
  ]
}
```

## Run

```bash
PYTHONPATH=. python3 tools/gt_relabel_gui/server.py \
  --mode manual \
  --config data/evaluation2/manual_correction_config.json \
  --root . \
  --port 8010
```

Then open:

```text
http://localhost:8010
```

## Supported operations

### `mmr_measure_span`

The reviewer selects an existing measure ROI from the numbering artifact.

Supported operations:

- `set_measure_span`
- `suppress`

Output file:

```text
data/evaluation2/manual_corrections/mmr_measure_spans.json
```

### `barline_construction`

The reviewer draws a bbox for `add_barline` or selects/draws a bbox for `remove_barline`.

Output file:

```text
data/evaluation2/manual_corrections/barline_construction_overrides.json
```

### `measure_construction`

The reviewer selects a measure interval from the numbering artifact.

Supported operation:

- `force_measure`

Output file:

```text
data/evaluation2/manual_corrections/measure_construction_overrides.json
```

## Future grouping

`group_staves_as_system` remains a future #197/divisi grouping extension. The first GUI pass does not write that operation.
