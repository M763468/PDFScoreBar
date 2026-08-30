# span

> 26 nodes · cohesion 0.14

## Key Concepts

- **span()** (17 connections) — `src/pipeline/perf_trace.py`
- **current_sr_worker.py** (13 connections) — `src/pipeline/detection/current_sr_worker.py`
- **perf_trace.py** (13 connections) — `src/pipeline/perf_trace.py`
- **set_context()** (13 connections) — `src/pipeline/perf_trace.py`
- **profile_hybrid_batch_sr.py** (11 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **run()** (10 connections) — `src/pipeline/detection/current_sr_worker.py`
- **record()** (5 connections) — `src/pipeline/perf_trace.py`
- **_load_request()** (4 connections) — `src/pipeline/detection/current_sr_worker.py`
- **Any** (4 connections)
- **main()** (3 connections) — `src/pipeline/detection/current_sr_worker.py`
- **Path** (3 connections)
- **_sha256()** (3 connections) — `src/pipeline/detection/current_sr_worker.py`
- **_cpu_seconds()** (3 connections) — `src/pipeline/perf_trace.py`
- **enabled()** (3 connections) — `src/pipeline/perf_trace.py`
- **reset_context()** (3 connections) — `src/pipeline/perf_trace.py`
- **_sync_cuda()** (3 connections) — `src/pipeline/perf_trace.py`
- **_trace_path()** (3 connections) — `src/pipeline/perf_trace.py`
- **Token** (2 connections)
- **Any** (1 connections)
- **Generate one current x4 SR image without loading HOMR or CNN models.** (1 connections) — `src/pipeline/detection/current_sr_worker.py`
- **Verified hybrid detector with all-pages current-x4 SR phase batching. The…** (1 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **Path** (1 connections)
- **Opt-in, process-safe performance spans for dense pipeline attribution. The…** (1 connections) — `src/pipeline/perf_trace.py`
- **Record a span and close it correctly on exceptions. CUDA spans synchronize…** (1 connections) — `src/pipeline/perf_trace.py`
- **Synchronize CUDA when available and report whether it was used.** (1 connections) — `src/pipeline/perf_trace.py`
- *... and 1 more nodes in this community*

## Relationships

- [current_support_worker.py](current_support_worker.py.md) (8 shared connections)
- [test_issue284_sr_batch_contract.py](test_issue284_sr_batch_contract.py.md) (6 shared connections)
- [apply_advanced_sr](apply_advanced_sr.md) (5 shared connections)
- [pipeline/orchestrator.py](pipeline-orchestrator.py.md) (3 shared connections)
- [build_detector_input_contract](build_detector_input_contract.md) (2 shared connections)
- [BatchSRVerifiedProfileHybridDetector](BatchSRVerifiedProfileHybridDetector.md) (2 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (1 shared connections)
- [load_json_boxes](load_json_boxes.md) (1 shared connections)
- [restored_orchestrator.py](restored_orchestrator.py.md) (1 shared connections)
- [verified_source_page_worker.py](verified_source_page_worker.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/current_sr_worker.py`
- `src/pipeline/detection/profile_hybrid_batch_sr.py`
- `src/pipeline/perf_trace.py`

## Audit Trail

- EXTRACTED: 77 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*