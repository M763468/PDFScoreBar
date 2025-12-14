# Project Documentation Index

> [!NOTE]
> **Repo Restructure (Dec 2025)**: Scripts have moved to `experiments/` and `tools/`. External repos are in `external/`. If documentation references old paths (`src/tools`, `homr/`), please adjust accordingly.

## Current Project Status (2025-12-15)

**Phase 3: Geometric FP Reduction** ✅ **COMPLETE**

- **Best Results** (page_3, hybrid pipeline): TP=152, FP=2, FN=0 (Precision=98.7%, Recall=100%)
- **Method**: Row-based consistency filter with ratio-based tolerance
- **Status**: Production-ready configuration identified
- **Next**: Phase 4 (context-based filters) and generalization testing

See [`NEXT_SESSION_NOTES.md`](NEXT_SESSION_NOTES.md) for detailed current status and next steps.

## Documentation Modules

### Core Documentation
- **[NEXT_SESSION_NOTES.md](NEXT_SESSION_NOTES.md)**: Current status, completed work, and immediate next steps
- **[DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md)**: Chronological history of all phases (append-only, authoritative)
- **[ENVIRONMENTS.md](ENVIRONMENTS.md)**: Runtime containers, dependencies, data layout
- **[AGENTS.md](AGENTS.md)**: AI assistant guidelines and automation policies
- **[BARLINE_MATCHER.md](BARLINE_MATCHER.md)**: Barline matching algorithm specification

### Phase-Specific Documentation
- **FP Reduction (Phase 1-3)**:
  - [Final Summary](fp_reduction/FINAL_SUMMARY.md): Executive summary (may be outdated, see Phase 3 reports)
  - [Development Log](fp_reduction/development_log.md): Detailed Phase 1-2 history
  - [Walkthrough](fp_reduction/walkthrough.md): Phase-by-phase results
  
- **Phase 3 Reports** (Latest):
  - Baseline sweep: `logs/phase3_staff_consistency/20251215_tolerance_sweep_page3/`
  - **Hybrid final**: `logs/phase3_staff_consistency/20251215_hybrid_ratio_sweep_page3/hybrid_filter_summary.md`

### Future Work
- [Roadmap](future/roadmap.md): Proposals for GUI, model retraining, etc.

## Quick Navigation

| Need | Document | Location |
|------|----------|----------|
| **Start new session** | NEXT_SESSION_NOTES.md | Current status + next tasks |
| **Understand history** | DEVELOPMENT_LOG.md | Chronological record |
| **Check environment** | ENVIRONMENTS.md | Container setup |
| **Phase 3 results** | hybrid_filter_summary.md | `logs/phase3_staff_consistency/20251215_hybrid_ratio_sweep_page3/` |
| **Scripts** | analyze_staff_consistency.py | `experiments/fp_reduction/` |

## Documentation Operations Policy

### NEXT_SESSION_NOTES.md
**Purpose**: Concise "current state + what to do next" document

**Update Policy**:
- **During active work**: Append new findings and results
- **At major milestones**: Migrate confirmed results to DEVELOPMENT_LOG.md
- **At session boundaries**: Rewrite/refresh entire file to remove clutter and contradictions
- **Goal**: Always readable in <5 minutes, shows current status clearly

**Structure**:
1. Current Status (what phase, what's working)
2. What Was Completed (high-level bullets)
3. Remaining Work / Next Tasks (ordered priority)
4. Key Artifacts (where to find things)

### DEVELOPMENT_LOG.md
**Purpose**: Authoritative chronological history

**Update Policy**:
- **Append-only**: Never delete or rewrite history
- **When to update**: At phase completion, major milestones, or significant findings
- **What to include**: Decisions, results, metrics, artifact locations
- **Format**: Dated sections in reverse-chronological order

### temp_next_step_plan.md
**Purpose**: Task checklist only

**Update Policy**:
- Tracks progress of tasks listed in NEXT_SESSION_NOTES.md
- Uses `[ ]`, `[/]`, `[x]` for uncompleted/in-progress/completed
- **No detailed results** - those go in DEVELOPMENT_LOG.md
- Update as tasks progress

## When to Update What

| Document | Primary Purpose | Update Trigger |
| --- | --- | --- |
| `docs/NEXT_SESSION_NOTES.md` | Current status + next steps | During work (append); at milestones (rewrite) |
| `docs/DEVELOPMENT_LOG.md` | Historical record (append-only) | Phase completion, major findings |
| `temp_next_step_plan.md` | Task checklist | As tasks progress |
| `docs/ENVIRONMENTS.md` | Runtime setup | Container/dependency changes |
| `docs/AGENTS.md` | AI assistant policies | Workflow/policy changes |

## Key Scripts & Tools

### Phase 3 (Geometric FP Reduction)
- **Main filter**: `experiments/fp_reduction/analyze_staff_consistency.py`
- **Tolerance sweep**: `experiments/fp_reduction/tolerance_sweep.py`
- **Unified metric**: `experiments/fp_reduction/unified_metric.py` (homr-equivalent evaluation)

### Evaluation
- **Baseline evaluator**: `external/homr/src/common/barline_evaluation.py`
- **Data locations**:
  - Hybrid detections: `logs/hybrid_results.json`
  - Baseline detections: `logs/homr_eval/baseline_for_hybrid/page_3/`
  - Ground truth: `data/evaluation/annotations/page_003/boxes_sorted.json`

## Notes for Contributors

- **Most recent info first**: Keep dated sections in reverse-chronological order
- **Link to artifacts**: Use repository-relative paths for logs, scripts, configs
- **Avoid duplication**: Update existing docs rather than creating new ones
- **Phase 3 success**: Geometric filtering achieved 98.7% precision with 100% recall
- **Next focus**: Generalization testing and optional context-based filters
