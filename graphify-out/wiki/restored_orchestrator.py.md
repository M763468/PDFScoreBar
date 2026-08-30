# restored_orchestrator.py

> 27 nodes · cohesion 0.15

## Key Concepts

- **restored_orchestrator.py** (19 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **DetectorOrchestrator** (16 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **restored_orchestrator_batch_sr.py** (9 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **DetectorOrchestrator** (9 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **Path** (8 connections)
- **run_detection_step()** (7 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **.run_detection()** (7 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._run_cnn_scoring()** (6 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._write_dense_inventory()** (6 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **Any** (6 connections)
- **._run_dense_route()** (5 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **run_detection_step()** (5 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._run_hybrid_detection()** (4 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **.__init__()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._record_input_contract()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **._run_hybrid_detection()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **_score_page()** (4 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **_first_existing()** (3 connections) — `src/pipeline/detection/restored_orchestrator.py`
- **Any** (2 connections)
- **Path** (2 connections)
- **BaseDetectorOrchestrator** (1 connections)
- **Verified dense-route orchestrator using the Issue #284 batch-SR profile.** (1 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **Keep the accepted dense route unchanged except for current-x4 SR scheduling.** (1 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **Run the verified Stage E detector with a dedicated all-pages SR phase.** (1 connections) — `src/pipeline/detection/restored_orchestrator_batch_sr.py`
- **Production orchestration for the verified Stage E detector route.** (1 connections) — `src/pipeline/detection/restored_orchestrator.py`
- *... and 2 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (7 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (7 shared connections)
- [run_full_pipeline.py](run_full_pipeline.py.md) (5 shared connections)
- [get_cnn_apply_nms](get_cnn_apply_nms.md) (3 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (3 shared connections)
- [BatchSRVerifiedProfileHybridDetector](BatchSRVerifiedProfileHybridDetector.md) (3 shared connections)
- [dense_full_pipeline.py](dense_full_pipeline.py.md) (2 shared connections)
- [cnn_scoring.py](cnn_scoring.py.md) (2 shared connections)
- [filter_probe_candidates](filter_probe_candidates.md) (1 shared connections)
- [test_issue255_detector_dispatch_contract.py](test_issue255_detector_dispatch_contract.py.md) (1 shared connections)
- [span](span.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/restored_orchestrator.py`
- `src/pipeline/detection/restored_orchestrator_batch_sr.py`

## Audit Trail

- EXTRACTED: 82 (95%)
- INFERRED: 4 (5%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*