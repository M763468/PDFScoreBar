# Issue #255 focused detector trace

`trace_focused_detector_boundaries.py` builds the first machine-readable inventory
for the authoritative fresh detector route. It reads the canonical
`configs/dense_full_pipeline.yaml`, validates the saved detector input contract,
replays the production-default row-band/probe/filter stages, and joins them with
saved CNN and final detector outputs.

Accepted/checkpoint barlines are analysis references only. They are used to find
missing targets and are never passed into the detector runtime.

The output directory contains:

- `focused_detector_inventory.json`
- `focused_detector_inventory.csv`
- `production_default/` replay artifacts and probe debug output

Use a distinct output directory for each page/run. Supply `--target-metadata` when
system numbers and downstream effects are known; otherwise every accepted bbox
missing from the current final set is traced automatically.
