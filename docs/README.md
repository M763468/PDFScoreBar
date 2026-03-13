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
| **Mid/Long Term** | `docs/DOCUMENT_INVENTORY.md` | **[NEW]** Document classification (Current vs Analysis vs Legacy) |
| **Short/Mid Term** | `docs/MANIFEST.md` | Asset registry (Models, Datasets, Configs) |
| **Historical Facts** | `docs/DEVELOPMENT_LOG.md` | Append-only authoritative record |

---

## Current Project Status (2026-03-14)

**Update (2026-03-14)**: Issue #13 (Full Pipeline Optimization) is complete. 
The current focus is **Evaluation Speedup** and **In-Process Refactoring**.
See `docs/notes/ROADMAP_20260313.md` for the active roadmap.

**Recent confirmed state**:
- `src/pipeline/main.py` is the primary entry point.
- MMR classifier and model persistence are verified for batch processing.
- Repository documentation has been re-organized into a classification inventory.

---

## Where to Find Results and Artifacts

This project produces a large number of intermediate and final artifacts.
Use `docs/DOCUMENT_INVENTORY.md` to find the correct documentation for each phase.

| What you want to see | Location |
|---------------------|----------|
| Latest asset registry | `docs/MANIFEST.md` |
| Active Roadmap | `docs/notes/ROADMAP_20260313.md` |
| Latest E2E Results | `docs/ISSUE13_E2E_VERIFICATION_REPORT.md` |
| Historical decisions | `docs/DEVELOPMENT_LOG.md` |

---

## Documentation Modules

### Core Documentation (Current)

- **`docs/DOCUMENT_INVENTORY.md`**  
  **Purpose**: Categorized list of all documents in `docs/` (Current/Analysis/Legacy).  
  Always check this if you are unsure which document is up-to-date.

- **`docs/MANIFEST.md`**  
  **Purpose**: Single source of truth for model paths, datasets, and configurations.

- **`docs/DEVELOPMENT_LOG.md`**  
  **Purpose**: Authoritative historical record.  
  - Append-only
  - Records confirmed facts, decisions, and outcomes
  - Never rewritten

- **`docs/ENVIRONMENTS.md`**  
  Runtime containers, dependencies, and execution instructions.

- **`docs/REGRESSION_TEST_WORKFLOW.md`**  
  Pre-commit / pre-PR verification workflow (lint/tests + real-data smoke + parity checks).

- **`docs/AGENTS.md` (root)**  
  Rules and expectations for AI assistants (Gemini / Codex / CLI usage).

- **`docs/GT_PREPARATION_POLICY.md`**  
  **Mandatory Policy** for creating barline Ground Truth.

- **`docs/BARLINE_MATCHER.md`**  
  Detailed specification of the barline matching and deduplication logic.

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
