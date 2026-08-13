# VerifiedProfileHybridDetector

> 32 nodes · cohesion 0.12

## Key Concepts

- **VerifiedProfileHybridDetector** (14 connections) — `src/pipeline/detection/profile_hybrid.py`
- **hybrid_consensus.py** (13 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **profile_hybrid.py** (12 connections) — `src/pipeline/detection/profile_hybrid.py`
- **apply_hybrid_consensus_filter()** (9 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **.run()** (7 connections) — `src/pipeline/detection/profile_hybrid.py`
- **verified_source_page_worker.py** (7 connections) — `src/pipeline/detection/verified_source_page_worker.py`
- **Path** (6 connections)
- **._generate_one_page_sources_in_process()** (6 connections) — `src/pipeline/detection/profile_hybrid.py`
- **run()** (6 connections) — `src/pipeline/detection/verified_source_page_worker.py`
- **test_issue255_page_local_source_generation.py** (6 connections) — `tests/test_issue255_page_local_source_generation.py`
- **_detector()** (6 connections) — `tests/test_issue255_page_local_source_generation.py`
- **Any** (5 connections)
- **._generate_page_sources()** (5 connections) — `src/pipeline/detection/profile_hybrid.py`
- **._source_page_worker()** (4 connections) — `src/pipeline/detection/profile_hybrid.py`
- **._support_worker()** (4 connections) — `src/pipeline/detection/profile_hybrid.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/verified_source_page_worker.py`
- **Path** (4 connections)
- **test_verified_source_page_worker_records_process_boundary()** (4 connections) — `tests/test_issue255_page_local_source_generation.py`
- **.__init__()** (3 connections) — `src/pipeline/detection/profile_hybrid.py`
- **_has_match()** (3 connections) — `src/pipeline/steps/hybrid_consensus.py`
- **test_one_page_source_worker_runs_all_heavy_phases_in_order()** (3 connections) — `tests/test_issue255_page_local_source_generation.py`
- **test_verified_sources_launch_one_top_level_worker_per_page()** (3 connections) — `tests/test_issue255_page_local_source_generation.py`
- **main()** (2 connections) — `src/pipeline/detection/verified_source_page_worker.py`
- **Path** (2 connections)
- **Hybrid source generation backed by the verified Stage E HOMR profile.** (1 connections) — `src/pipeline/detection/profile_hybrid.py`
- *... and 7 more nodes in this community*

## Relationships

- [run_probe_scan_batch](run_probe_scan_batch.md) (6 shared connections)
- [trace_prokofiev_probe_boundary.py](trace_prokofiev_probe_boundary.py.md) (5 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (4 shared connections)
- [score_candidates_batch.py](score_candidates_batch.py.md) (3 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (3 shared connections)
- [hybrid.py](hybrid.py.md) (3 shared connections)
- [barline_iou](barline_iou.md) (2 shared connections)

## Source Files

- `src/pipeline/detection/profile_hybrid.py`
- `src/pipeline/detection/verified_source_page_worker.py`
- `src/pipeline/steps/hybrid_consensus.py`
- `tests/test_issue255_page_local_source_generation.py`

## Audit Trail

- EXTRACTED: 85 (99%)
- INFERRED: 1 (1%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*