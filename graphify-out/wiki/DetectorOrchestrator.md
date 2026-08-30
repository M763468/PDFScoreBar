# DetectorOrchestrator

> 24 nodes · cohesion 0.18

## Key Concepts

- **DetectorOrchestrator** (21 connections) — `src/pipeline/detection/orchestrator.py`
- **._run_probe_scan()** (13 connections) — `src/pipeline/detection/orchestrator.py`
- **Path** (11 connections)
- **._run_cnn_scoring()** (10 connections) — `src/pipeline/detection/orchestrator.py`
- **.run_detection()** (7 connections) — `src/pipeline/detection/orchestrator.py`
- **Any** (7 connections)
- **._copy_precomputed_probe_candidates()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **.__init__()** (6 connections) — `src/pipeline/detection/orchestrator.py`
- **._get_effective_images_for_probe()** (5 connections) — `src/pipeline/detection/orchestrator.py`
- **._record_input_contract()** (5 connections) — `src/pipeline/detection/orchestrator.py`
- **._run_hybrid_detection()** (5 connections) — `src/pipeline/detection/orchestrator.py`
- **._get_effective_score_name()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_clef_mask_dir()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_cnn_bands_from()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_precomputed_probe_candidates_root()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **._resolve_staff_mask_dir()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **_reject_removed_detector_route_keys()** (3 connections) — `src/pipeline/detection/orchestrator.py`
- **Executes the full detection pipeline.** (1 connections) — `src/pipeline/detection/orchestrator.py`
- **Step 2.1: Hybrid Detection (Subprocess or In-Process)** (1 connections) — `src/pipeline/detection/orchestrator.py`
- **Step 2.2: Probe Scan (Host)** (1 connections) — `src/pipeline/detection/orchestrator.py`
- **Step 2.3: CNN Scoring (Host)** (1 connections) — `src/pipeline/detection/orchestrator.py`
- **Returns images and scale to use for probe scan (SR or original).** (1 connections) — `src/pipeline/detection/orchestrator.py`
- **Orchestrates hybrid detection, probe scan, and CNN scoring.** (1 connections) — `src/pipeline/detection/orchestrator.py`
- **Persist which detector source is authoritative before executing stages.** (1 connections) — `src/pipeline/detection/orchestrator.py`

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (9 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (5 shared connections)
- [_orchestrator](_orchestrator.md) (2 shared connections)
- [hybrid.py](hybrid.py.md) (2 shared connections)
- [get_cnn_apply_nms](get_cnn_apply_nms.md) (2 shared connections)
- [get_nested](get_nested.md) (1 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (1 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/orchestrator.py`

## Audit Trail

- EXTRACTED: 70 (97%)
- INFERRED: 2 (3%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*