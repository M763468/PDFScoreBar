# StaffExtractor

> 18 nodes · cohesion 0.15

## Key Concepts

- **StaffExtractor** (21 connections) — `src/measure_numbering/pipeline.py`
- **ConnectorAwareSystemBuilder** (13 connections) — `src/measure_numbering/connector_aware_builder.py`
- **verify_divisi_batch.py** (9 connections) — `tools/verify_divisi_batch.py`
- **main()** (6 connections) — `tools/verify_divisi_batch.py`
- **process_page()** (6 connections) — `tools/verify_divisi_batch.py`
- **._group_by_geometry()** (5 connections) — `src/measure_numbering/connector_aware_builder.py`
- **.__init__()** (5 connections) — `src/measure_numbering/pipeline.py`
- **experiment_gap_connection.py** (3 connections) — `experiments/legacy/tools_archive/experiment_gap_connection.py`
- **main()** (2 connections) — `experiments/legacy/tools_archive/experiment_gap_connection.py`
- **Barline** (2 connections)
- **Path** (2 connections)
- **BaseSystemBuilder** (1 connections)
- **Any** (1 connections)
- **ndarray** (1 connections)
- **Staff** (1 connections)
- **SystemBuilder variant that treats generated connector absence as a split signal.** (1 connections) — `src/measure_numbering/connector_aware_builder.py`
- **Extracts staff regions (BBoxes) from a binary staff mask image.** (1 connections) — `src/measure_numbering/pipeline.py`
- **.__init__()** (1 connections) — `src/measure_numbering/pipeline.py`

## Relationships

- [Staff](Staff.md) (19 shared connections)
- [SystemBuilder](SystemBuilder.md) (4 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (3 shared connections)
- [BBox](BBox.md) (3 shared connections)
- [SystemConnectorEvidenceExtractor](SystemConnectorEvidenceExtractor.md) (2 shared connections)
- [write_json](write_json.md) (2 shared connections)
- [run_grouped_final_numbering_comparison.py](run_grouped_final_numbering_comparison.py.md) (2 shared connections)

## Source Files

- `experiments/legacy/tools_archive/experiment_gap_connection.py`
- `src/measure_numbering/connector_aware_builder.py`
- `src/measure_numbering/pipeline.py`
- `tools/verify_divisi_batch.py`

## Audit Trail

- EXTRACTED: 45 (78%)
- INFERRED: 13 (22%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*