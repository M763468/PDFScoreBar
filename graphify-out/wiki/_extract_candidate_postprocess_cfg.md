# _extract_candidate_postprocess_cfg

> 10 nodes · cohesion 0.24

## Key Concepts

- **_extract_candidate_postprocess_cfg()** (8 connections) — `src/pipeline/steps/probe_scan.py`
- **_resolve_scale_aware_probe_kwargs()** (7 connections) — `src/pipeline/steps/probe_scan.py`
- **_estimate_unit_size_from_existing_boxes()** (6 connections) — `src/pipeline/steps/probe_scan.py`
- **_augment_unit_normalized_boxes()** (5 connections) — `src/pipeline/steps/probe_scan.py`
- **Any** (5 connections)
- **_parse_bool_like()** (3 connections) — `src/pipeline/steps/probe_scan.py`
- **_clip_box()** (2 connections) — `src/pipeline/steps/probe_scan.py`
- **Extract batch-only candidate postprocess pseudo keys from kwargs.** (1 connections) — `src/pipeline/steps/probe_scan.py`
- **Emit additional normalized vertical boxes to reduce bbox shape mismatch. This…** (1 connections) — `src/pipeline/steps/probe_scan.py`
- **Translate batch-only ratio knobs into detect_probe_scan kwargs. Supported…** (1 connections) — `src/pipeline/steps/probe_scan.py`

## Relationships

- [probe_scan.py](probe_scan.py.md) (6 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (6 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (5 shared connections)

## Source Files

- `src/pipeline/steps/probe_scan.py`

## Audit Trail

- EXTRACTED: 28 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*