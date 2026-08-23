# write_json

> 33 nodes · cohesion 0.13

## Key Concepts

- **write_json()** (30 connections) — `src/pipeline/utils/io.py`
- **io.py** (29 connections) — `src/pipeline/utils/io.py`
- **run_representative_mmr_reuse.py** (21 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **mmr_support_reuse.py** (20 connections) — `src/pipeline/mmr_support_reuse.py`
- **build_mmr_support_data()** (17 connections) — `src/pipeline/mmr_support_reuse.py`
- **providers_include_cuda()** (15 connections) — `src/measure_numbering/rapidocr_provider.py`
- **build_mmr_support()** (13 connections) — `src/pipeline/mmr_support_reuse.py`
- **main()** (13 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **validate_mmr_support_mapping.py** (11 connections) — `tools/issue274/validate_mmr_support_mapping.py`
- **_visible_path()** (10 connections) — `tools/issue274/validate_mmr_support_mapping.py`
- **Any** (7 connections)
- **main()** (6 connections) — `tools/issue274/validate_mmr_support_mapping.py`
- **_is_implicit_start()** (5 connections) — `src/pipeline/mmr_support_reuse.py`
- **_bbox()** (4 connections) — `src/pipeline/mmr_support_reuse.py`
- **_candidate_record()** (4 connections) — `src/pipeline/mmr_support_reuse.py`
- **_matches()** (4 connections) — `src/pipeline/mmr_support_reuse.py`
- **Path** (4 connections)
- **write_manifest()** (4 connections) — `src/pipeline/utils/io.py`
- **_raw_mapped_bbox()** (3 connections) — `src/pipeline/mmr_support_reuse.py`
- **Any** (3 connections)
- **_compact()** (3 connections) — `tools/issue274/run_representative_mmr_reuse.py`
- **_overlap_ratio()** (2 connections) — `src/pipeline/mmr_support_reuse.py`
- **Path** (2 connections)
- **Path** (2 connections)
- **Build MMR-only views by reusing current-x4 HOMR support artifacts. The Phase-A…** (1 connections) — `src/pipeline/mmr_support_reuse.py`
- *... and 8 more nodes in this community*

## Relationships

- [load_json](load_json.md) (31 shared connections)
- [run_original_geometry_graft.py](run_original_geometry_graft.py.md) (11 shared connections)
- [phase_b_page001_acceptance.py](phase_b_page001_acceptance.py.md) (9 shared connections)
- [run_mmr_batch](run_mmr_batch.md) (8 shared connections)
- [run_probe_scan_batch](run_probe_scan_batch.md) (5 shared connections)
- [Staff](Staff.md) (4 shared connections)
- [audit_positive_geometry_disagreements.py](audit_positive_geometry_disagreements.py.md) (3 shared connections)
- [test_issue274_mmr_support_reuse.py](test_issue274_mmr_support_reuse.py.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [.run](run.md) (3 shared connections)
- [MMRProcessor](MMRProcessor.md) (3 shared connections)
- [diagnose_ocr_frame_changed_pages.py](diagnose_ocr_frame_changed_pages.py.md) (2 shared connections)

## Source Files

- `src/measure_numbering/rapidocr_provider.py`
- `src/pipeline/mmr_support_reuse.py`
- `src/pipeline/utils/io.py`
- `tools/issue274/run_representative_mmr_reuse.py`
- `tools/issue274/validate_mmr_support_mapping.py`

## Audit Trail

- EXTRACTED: 172 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*