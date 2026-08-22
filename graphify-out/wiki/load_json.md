# load_json

> 27 nodes · cohesion 0.18

## Key Concepts

- **load_json()** (41 connections) — `src/pipeline/utils/io.py`
- **write_json()** (30 connections) — `src/pipeline/utils/io.py`
- **phase_b_page001_acceptance.py** (23 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **run()** (14 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **barlines.py** (11 connections) — `src/pipeline/steps/barlines.py`
- **build_numbering()** (10 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **normalize_barlines()** (9 connections) — `src/pipeline/steps/barlines.py`
- **run_phase_b_page001_acceptance.py** (9 connections) — `tools/issue264/run_phase_b_page001_acceptance.py`
- **test_issue264_phase_b_manifest.py** (6 connections) — `tests/test_issue264_phase_b_manifest.py`
- **target_manifest_entry()** (6 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **main()** (6 connections) — `tools/issue264/run_phase_b_page001_acceptance.py`
- **apply_barline_overrides()** (5 connections) — `src/pipeline/steps/barlines.py`
- **Path** (4 connections)
- **write_manifest()** (4 connections) — `src/pipeline/utils/io.py`
- **Any** (4 connections)
- **Path** (4 connections)
- **_matching_manifest()** (4 connections) — `tools/issue264/run_phase_b_page001_acceptance.py`
- **materialize_canonical_artifact_manifest()** (4 connections) — `tools/issue264/run_phase_b_page001_acceptance.py`
- **Path** (4 connections)
- **resolve_manifest()** (4 connections) — `tools/issue264/run_phase_b_page001_acceptance.py`
- **Any** (3 connections)
- **override_triples()** (3 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **physical_counts()** (3 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **sha256()** (3 connections) — `tools/issue264/phase_b_page001_acceptance.py`
- **Any** (2 connections)
- *... and 2 more nodes in this community*

## Relationships

- [run_phase_c_mmr_regression.py](run_phase_c_mmr_regression.py.md) (14 shared connections)
- [get_nested](get_nested.md) (10 shared connections)
- [mmr_support_reuse.py](mmr_support_reuse.py.md) (8 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (7 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (6 shared connections)
- [Staff](Staff.md) (6 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (6 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (5 shared connections)
- [diagnose_phase_b_layout_divergence.py](diagnose_phase_b_layout_divergence.py.md) (4 shared connections)
- [create_mmr_rapidocr](create_mmr_rapidocr.md) (4 shared connections)
- [manual_corrections.py](manual_corrections.py.md) (3 shared connections)
- [build_mmr_page_context](build_mmr_page_context.md) (3 shared connections)

## Source Files

- `src/pipeline/steps/barlines.py`
- `src/pipeline/utils/io.py`
- `tests/test_issue264_phase_b_manifest.py`
- `tools/issue264/phase_b_page001_acceptance.py`
- `tools/issue264/run_phase_b_page001_acceptance.py`

## Audit Trail

- EXTRACTED: 156 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*