# BatchSRVerifiedProfileHybridDetector

> 12 nodes · cohesion 0.35

## Key Concepts

- **BatchSRVerifiedProfileHybridDetector** (17 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **._batch_sr_worker()** (6 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **._generate_one_page_sources_in_process()** (6 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **Any** (6 connections)
- **Path** (5 connections)
- **._generate_page_sources()** (4 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **._source_page_worker()** (4 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **._support_worker()** (4 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **.__init__()** (2 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **.run()** (2 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **Generate baseline/current support after the optional SR phase has exited.** (1 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`
- **Verified profile detector with a dedicated reusable current-SR phase.** (1 connections) — `src/pipeline/detection/profile_hybrid_batch_sr.py`

## Relationships

- [restored_orchestrator.py](restored_orchestrator.py.md) (3 shared connections)
- [verified_source_page_worker.py](verified_source_page_worker.py.md) (2 shared connections)
- [test_issue284_sr_batch_contract.py](test_issue284_sr_batch_contract.py.md) (2 shared connections)
- [span](span.md) (2 shared connections)
- [VerifiedProfileHybridDetector](VerifiedProfileHybridDetector.md) (1 shared connections)
- [current_support_worker.py](current_support_worker.py.md) (1 shared connections)
- [homr_profile.py](homr_profile.py.md) (1 shared connections)

## Source Files

- `src/pipeline/detection/profile_hybrid_batch_sr.py`

## Audit Trail

- EXTRACTED: 32 (91%)
- INFERRED: 3 (9%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [index](index.md) to navigate.*