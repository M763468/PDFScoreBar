# Community 141

> 19 nodes · cohesion 0.15

## Key Concepts

- **test_issue447_profiling_tools.py** (18 connections) — `tests/test_issue447_profiling_tools.py`
- **timeline()** (9 connections) — `tools/issue447/deepening_analyze.py`
- **select_process_samples()** (7 connections) — `tools/issue447/analyze.py`
- **is_source_worker()** (5 connections) — `tools/issue447/deepening_analyze.py`
- **parametrize** (3 connections)
- **test_batched_tiles_preserve_edge_padding_channel_order_and_cpu_stitch()** (3 connections) — `tests/test_issue447_profiling_tools.py`
- **test_host_timeline_assigns_same_source_intervals_for_both_entrypoints()** (3 connections) — `tests/test_issue447_profiling_tools.py`
- **test_source_worker_entrypoint_distinguishes_reuse_parent_and_support()** (3 connections) — `tests/test_issue447_profiling_tools.py`
- **e2e_summarize.py** (3 connections) — `tools/issue447/e2e_summarize.py`
- **test_host_timeline_does_not_correlate_unaligned_gpu_or_epoch_clocks()** (2 connections) — `tests/test_issue447_profiling_tools.py`
- **test_legacy_process_samples_require_explicit_matching_run()** (2 connections) — `tests/test_issue447_profiling_tools.py`
- **test_process_sample_selection_prefers_run_local_over_legacy()** (2 connections) — `tests/test_issue447_profiling_tools.py`
- **test_process_summary_keeps_nested_residencies_and_cumulative_io_separate()** (2 connections) — `tests/test_issue447_profiling_tools.py`
- **Geometry guards for the isolated tile-batching experiment, without GPU/model…** (1 connections) — `tests/test_issue447_profiling_tools.py`
- **test_source_checks_accepts_alternate_score_folder()** (1 connections) — `tests/test_issue447_profiling_tools.py`
- **Keep observations attached to their run; legacy evidence requires opt-in.** (1 connections) — `tools/issue447/analyze.py`
- **Recognize sampled top-level source entrypoints, excluding nested support. The…** (1 connections) — `tools/issue447/deepening_analyze.py`
- **Correlate coarse utilization with CPU activity, without calling it causal wait.** (1 connections) — `tools/issue447/deepening_analyze.py`
- **Distill measured E2E results without adding independent component timings.** (1 connections) — `tools/issue447/e2e_summarize.py`

## Relationships

- [Community 66](Community_66.md) (11 shared connections)
- [Community 149](Community_149.md) (5 shared connections)

## Source Files

- `tests/test_issue447_profiling_tools.py`
- `tools/issue447/analyze.py`
- `tools/issue447/deepening_analyze.py`
- `tools/issue447/e2e_summarize.py`

## Audit Trail

- EXTRACTED: 42 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*