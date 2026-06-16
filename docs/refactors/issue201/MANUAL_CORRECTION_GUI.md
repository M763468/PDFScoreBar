# Issue #201 manual correction GUI

This document records the manual-correction GUI implementation for the #201 workflow.

## Decision

The manual-correction editor is implemented as a sibling mode under `tools/gt_relabel_gui`, not as a replacement for the existing `gt` or `rest` modes.

The existing modes keep their current output contracts:

- `gt`: edits barline GT boxes and writes raw/sorted GT payloads.
- `rest`: edits the older page-local multi-rest GT payload.

The `manual` mode writes the durable #201 correction schema under `data/evaluation2/manual_corrections/`.

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
  data/evaluation2/images/<work>/page_015.png \
  logs/.../numbering_base.json \
  <work>_page_015 \
  15 \
  data/evaluation2/manual_correction_config.json \
  logs/.../mmr_measure_overrides.json \
  logs/.../pipeline2_no_peak_scored.json
```

The positional arguments are:

```text
IMAGE NUMBERING NAME PAGE OUTPUT [MMR] [BARLINES]
```

`MMR` is optional but recommended. It should point to a JSON payload containing `measure_overrides` or `overrides`. When present, the GUI shows each measure as:

```text
base=<span from MMR artifact> effective=<span after manual correction>
```

`BARLINES` is optional. It is used only to display selectable base barlines for `remove_barline`.

The generated config uses these page fields:

```json
{
  "pages": [
    {
      "name": "Va__Prokofiev_Symphony5_page_015",
      "page": 15,
      "image": "data/evaluation2/images/Va__Prokofiev_Symphony5/page_015.png",
      "numbering": "logs/.../numbering_base.json",
      "mmr": "logs/.../mmr_measure_overrides.json",
      "barlines": "logs/.../pipeline2_no_peak_scored.json"
    }
  ]
}
```

By default, `server.py --mode manual` uses these output paths:

```text
data/evaluation2/manual_corrections/mmr_measure_spans.json
data/evaluation2/manual_corrections/barline_construction_overrides.json
data/evaluation2/manual_corrections/measure_construction_overrides.json
```

A config may override those paths with a top-level `manual_outputs` object.

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

## Save semantics

Save writes only the relevant manual correction JSON file. It does not update the base MMR artifact, run evaluation, or rewrite pipeline outputs.

The GUI updates its effective display immediately after staging a correction, but persisted effects are visible to the evaluator only after the relevant pipeline/evaluation command is re-run.

## Supported operations

### `mmr_measure_span`

The reviewer selects an existing measure ROI from the numbering artifact. If an MMR artifact is configured, the list and overlay show both the base span and the effective span after manual corrections.

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

`group_staves_as_system` remains a future #197/divisi grouping extension. This GUI pass does not write that operation.
