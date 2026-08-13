# run_grouped_final_numbering_comparison.py

> 24 nodes · cohesion 0.20

## Key Concepts

- **run_grouped_final_numbering_comparison.py** (34 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **main()** (18 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **_number_route()** (14 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **MMRClassifier** (13 connections) — `src/measure_numbering/mmr.py`
- **Path** (10 connections)
- **_score_candidates()** (8 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **GPUNormalize** (7 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Any** (6 connections)
- **_config()** (5 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **_load()** (5 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **_validate_cnn_staff_mask_contract()** (5 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **_validate_image_contract()** (5 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **_write()** (5 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **_read_image_size()** (4 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **.predict()** (3 connections) — `src/measure_numbering/mmr.py`
- **_connector_mask_paths()** (3 connections) — `tools/issue252/run_grouped_final_numbering_comparison.py`
- **GPUNormalize** (2 connections)
- **.forward()** (2 connections) — `src/pipeline/steps/cnn_scoring.py`
- **device** (2 connections)
- **Handles CNN inference for Multi-Measure Rest (MMR) detection.** (1 connections) — `src/measure_numbering/mmr.py`
- **Returns probability of being a Rest (Label 1).** (1 connections) — `src/measure_numbering/mmr.py`
- **.__init__()** (1 connections) — `src/pipeline/steps/cnn_scoring.py`
- **Tensor** (1 connections)
- **Module** (1 connections)

## Relationships

- [cnn_scoring.py](cnn_scoring.py.md) (9 shared connections)
- [MMRProcessor](MMRProcessor.md) (5 shared connections)
- [Score](Score.md) (5 shared connections)
- [MMROCREngine](MMROCREngine.md) (4 shared connections)
- [test_issue252_grouped_semantic_impact.py](test_issue252_grouped_semantic_impact.py.md) (4 shared connections)
- [run_stage_e_full_pipeline.py](run_stage_e_full_pipeline.py.md) (3 shared connections)
- [steps/numbering.py](steps-numbering.py.md) (3 shared connections)
- [audit_grouped_semantic_impact.py](audit_grouped_semantic_impact.py.md) (3 shared connections)
- [render_overlay](render_overlay.md) (3 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (2 shared connections)
- [MeasureNumberingPipeline](MeasureNumberingPipeline.md) (2 shared connections)
- [Staff](Staff.md) (2 shared connections)

## Source Files

- `src/measure_numbering/mmr.py`
- `src/pipeline/steps/cnn_scoring.py`
- `tools/issue252/run_grouped_final_numbering_comparison.py`

## Audit Trail

- EXTRACTED: 100 (98%)
- INFERRED: 2 (2%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*