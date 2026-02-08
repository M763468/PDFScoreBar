# Project Documentation Index

> [!NOTE]
> This document is the entry point for understanding the current state,
> history, and structure of the project.
>
> If you are new to this repository, start here.

---

## How to Read This Repository (Important)

This repository contains multiple layers of documentation, each serving
a different time scale and purpose.

Understanding which document to read (or update) is essential to avoid
confusion and duplication.

### Documentation by Time Scale

| Time Scale | Document | Purpose |
|----------|----------|---------|
| **Very Long Term** | `README.md` (repo root) | Ultimate project vision and scope |
| **Long Term** | `docs/README.md` (this file) | Project map and documentation index |
| **Mid Term** | `docs/NEXT_SESSION_NOTES.md` | Current confirmed state and allowed work areas |
| **Short Term** | `docs/SESSION_LOG.md` | Per-session working notes (messy is OK) |
| **Historical Facts** | `docs/DEVELOPMENT_LOG.md` | Append-only authoritative record |

---

## Current Project Status (2025-12-30)

**Update (2025-12-30)**: GT rebuild + recheck is complete. The current focus is **detector-side FN analysis** for the remaining 10 true detector-miss cases.
See `docs/NEXT_SESSION_NOTES.md` for the confirmed baseline, logs, and next actions.

**Recent confirmed state (high-level)**:
- GT cleanup completed for 35 detector-miss candidates; 10 remain after recheck.
- Baseline `var88` keeps FN=0 on the rebuilt evaluation set.
- Next work targets FP-source cleanup without reintroducing FN.

---

## Where to Find Results and Artifacts

This project produces a large number of intermediate and final artifacts.
Use the table below to quickly locate what you need.

| What you want to see | Location |
|---------------------|----------|
| Latest confirmed results | `docs/NEXT_SESSION_NOTES.md` |
| Historical decisions and outcomes | `docs/DEVELOPMENT_LOG.md` |
| Phase 3 final report (historical, likely stale) | `docs/fp_reduction/FINAL_SUMMARY.md` |
| Detailed Phase 1–2 history (historical, likely stale) | `docs/fp_reduction/development_log.md` |
| Phase-by-phase walkthrough (historical, likely stale) | `docs/fp_reduction/walkthrough.md` |
| Latest qualitative overlays | `logs/phase3_staff_consistency/` |
| Hybrid filter summary | `logs/phase3_staff_consistency/**/hybrid_filter_summary.md` |

---

## Documentation Modules

### Core Documentation

- **`docs/NEXT_SESSION_NOTES.md`**  
  **Purpose**: Mid-term, human-readable summary of the current confirmed state.  
  This file answers:
  - What phase are we in?
  - What is already confirmed and stable?
  - What problem areas are we allowed to work on next?

- **`docs/SESSION_LOG.md`**  
  **Purpose**: Short-term working log for each session.  
  - Free-form
  - Chronological
  - May contain mistakes, speculation, or dead ends  
  Nothing here is considered final.

- **`docs/DEVELOPMENT_LOG.md`**  
  **Purpose**: Authoritative historical record.  
  - Append-only
  - Records confirmed facts, decisions, and outcomes
  - Always links to concrete artifacts (logs, scripts, configs)
  - Never rewritten

- **`docs/ENVIRONMENTS.md`**  
  Runtime containers, dependencies, and execution instructions.

- **`docs/REGRESSION_TEST_WORKFLOW.md`**  
  Pre-commit / pre-PR verification workflow (lint/tests + real-data smoke + parity checks).

- **`docs/AGENTS.md`**  
  Rules and expectations for AI assistants (Gemini / Codex / CLI usage).

---

## Phase-Specific Documentation

### FP Reduction (Phase 1–3, Historical)

- **Final Summary**  
  `docs/fp_reduction/FINAL_SUMMARY.md`  
  Executive summary of the FP reduction effort. Note: this subtree is ~3 weeks behind current work.

- **Development Log (Phase 1–2)**  
  `docs/fp_reduction/development_log.md`  
  Detailed early-phase experimentation history.

- **Walkthrough**  
  `docs/fp_reduction/walkthrough.md`  
  Phase-by-phase explanation of methodology and results.

---

## Logs and Experimental Outputs

Experimental outputs are stored under `logs/` using timestamped directories.

General rules:
- Each run produces its own directory
- Scripts and configurations used for the run should be traceable from the log
- Qualitative overlays (images) live next to quantitative summaries

Examples:
- `logs/phase3_staff_consistency/20251215_hybrid_ratio_sweep_page3/`
- `logs/phase3_staff_consistency/20251216_page10_hybrid_filter_FIXED/`

---

## Repository Structure (Summary)
