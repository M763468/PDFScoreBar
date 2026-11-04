# Community 122

> 22 nodes · cohesion 0.14

## Key Concepts

- **OrderedJobs** (14 connections) — `tools/issue447/pipeline_poc.py`
- **install_source_prefetch()** (8 connections) — `tools/issue447/pipeline_poc.py`
- **SourceSchedulingTests** (6 connections) — `tests/test_issue447_source_scheduling.py`
- **e2e_fault_integration.py** (6 connections) — `tools/issue447/e2e_fault_integration.py`
- **test_issue447_source_scheduling.py** (5 connections) — `tests/test_issue447_source_scheduling.py`
- **child()** (5 connections) — `tools/issue447/e2e_fault_integration.py`
- **source_main()** (3 connections) — `tools/issue447/omr_reuse_poc.py`
- **component_main()** (3 connections) — `tools/issue447/pipeline_poc.py`
- **._write()** (3 connections) — `tools/issue447/pipeline_poc.py`
- **Path** (3 connections)
- **test_source_failure_cancels_queued_work_and_joins_running_children()** (2 connections) — `tests/test_issue447_omr_reuse.py`
- **.test_completed_sr_boundary_is_required()** (2 connections) — `tests/test_issue447_source_scheduling.py`
- **.test_parallel_completion_is_consumed_in_input_order()** (2 connections) — `tests/test_issue447_source_scheduling.py`
- **.test_worker_bound_and_same_input_contract_in_both_modes()** (2 connections) — `tests/test_issue447_source_scheduling.py`
- **.test_worker_failure_propagates_without_serial_fallback()** (2 connections) — `tests/test_issue447_source_scheduling.py`
- **main()** (2 connections) — `tools/issue447/e2e_fault_integration.py`
- **._execute()** (2 connections) — `tools/issue447/pipeline_poc.py`
- **.__init__()** (2 connections) — `tools/issue447/pipeline_poc.py`
- **.result()** (2 connections) — `tools/issue447/pipeline_poc.py`
- **GPU-free ordering/lifetime guards for the investigation-only source shim.** (1 connections) — `tests/test_issue447_source_scheduling.py`
- **CPU-only fault propagation through actual pipeline; retained SR, no performance…** (1 connections) — `tools/issue447/e2e_fault_integration.py`
- **.close()** (1 connections) — `tools/issue447/pipeline_poc.py`

## Relationships

- [Community 202](Community_202.md) (4 shared connections)
- [Community 187](Community_187.md) (3 shared connections)
- [Community 117](Community_117.md) (2 shared connections)
- [Community 154](Community_154.md) (1 shared connections)
- [Community 35](Community_35.md) (1 shared connections)
- [Community 1](Community_1.md) (1 shared connections)
- [Community 16](Community_16.md) (1 shared connections)

## Source Files

- `tests/test_issue447_omr_reuse.py`
- `tests/test_issue447_source_scheduling.py`
- `tools/issue447/e2e_fault_integration.py`
- `tools/issue447/omr_reuse_poc.py`
- `tools/issue447/pipeline_poc.py`

## Audit Trail

- EXTRACTED: 41 (91%)
- INFERRED: 4 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*