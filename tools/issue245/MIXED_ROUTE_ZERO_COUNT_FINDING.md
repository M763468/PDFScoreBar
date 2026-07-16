# Mixed-route zero-count comparison finding

The initial `accuracy_first_mixed_route_report.json` was not valid evidence even though it reported `status=completed`.

The source inventories were validated correctly:

```text
current:    baseline=10229 sr=4635 omr=5984 hybrid=4064
historical: baseline=4381  sr=3356 omr=5820 hybrid=3312
```

However, historical and mixed hybrid files are top-level box arrays. The evaluator-probe `load_records()` helper only accepts `{"predictions": ...}` payloads, so every hybrid file was parsed as zero records. This produced a false 68/68 equality result from 0-versus-0 comparisons.

The report must be revalidated with `validate_accuracy_first_mixed_route.py`, which uses the production `load_json_boxes()` parser, requires 68 pages and exactly 3,312 retained historical hybrid boxes, and rejects empty mixed output.
