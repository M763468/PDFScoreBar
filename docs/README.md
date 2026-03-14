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

### Documentation by Time Scale

| Time Scale | Document | Purpose |
|----------|----------|---------|
| **Very Long Term** | `README.md` (repo root) | Ultimate project vision and scope |
| **Mid/Long Term** | `docs/DOCUMENT_INVENTORY.md` | Document classification (Current vs Analysis vs Legacy) |
| **Short/Mid Term** | `docs/MANIFEST.md` | Asset registry (Models, Datasets, Configs) |
| **Historical Facts** | `docs/DEVELOPMENT_LOG.md` | Append-only authoritative record |

---

## Current Project Status (2026-03-15)

**Current focus**: **Evaluation Speedup** and **Batch Optimization**.
See `docs/notes/ROADMAP_20260313.md` for the active roadmap.

**Key Documents**:
- `src/pipeline/main.py` is the primary entry point.
- `docs/E2E_VERIFICATION_REPORT.md` contains the latest performance metrics.
- `docs/DOCUMENT_INVENTORY.md` tracks all documentation status.

---

## Documentation Modules

### Core Documentation (Current)

- **`docs/DOCUMENT_INVENTORY.md`**  
  Categorized list of all documents in `docs/`. Always check this first.

- **`docs/MANIFEST.md`**  
  Single source of truth for model paths, datasets, and configurations.

- **`docs/E2E_VERIFICATION_REPORT.md`**  
  Latest end-to-end pipeline verification results.

- **`docs/ENVIRONMENTS.md`**  
  Runtime containers, dependencies, and execution instructions.

- **`docs/LOG_MANAGEMENT.md`**  
  Guidelines for log structure, artifacts, and worktree usage.

- **`docs/BARLINE_MATCHER.md`**  
  Detailed specification of the barline matching and deduplication logic.

---

### Inventories (Centralized)

Specialized inventories are located in `docs/inventory/`:

- **`docs/inventory/TOOLS.md`**  
  Comprehensive registry of scripts and tools in `tools/`.
- **`docs/inventory/EXPERIMENTS.md`**  
  Inventory and classification of scripts in `experiments/`.
- **`docs/inventory/OUTPUT_LOGS.md`**  
  Detailed audit and purpose of each `logs/` and `artifacts/` subdirectory.

---

### AI Workflow & Skills

- **`docs/ai-workflow/`**  
  Guidelines and templates for AI agent collaboration and long-horizon tasks.
- **`docs/agent-skills/`**  
  Definitions and documentation for specialized agent skills.

---

## Archive and Historical Data

Historical projects and obsolete documentation are stored in `docs/archive/`.
Refer to these only for historical context or to understand the derivation of current heuristics.

- **`docs/archive/fp_reduction/`**  
  Records of the initial False Positive reduction effort (Dec 2025).
- **`docs/archive/DEVLOG_CNN_TRAINING.md`**  
  Provenance and development history of the CNN classifier.
- **`docs/archive/model_experiments/`**  
  Early evaluations of various ML backends (YOLO, etc.).

---

## Logs and Experimental Outputs

Experimental outputs are stored under `logs/` as defined in `docs/LOG_MANAGEMENT.md`.
Qualitative overlays (images) and quantitative summaries are stored together per run.
