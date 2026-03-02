# GEMINI.md - Project Specific Context

## Current Status (2026-03-02)
- **Issue #44 (CNN Classifier Baseline)**: Completed.
- **Issue #13 (Full Pipeline Phase 2)**: In progress / Next target.
    - Goal: Batch optimization, Model persistence, VRAM management (RTX 4060 8GB).
- **Previous Fixes**: Sibelius and Shostakovich recall issues have been resolved.

## Strategic Priorities
1. **Collaborative Reasoning (AGENTS.md Section 8.9)**:
   - Use `Codex` as a "Deep Auditor" for VRAM optimization and architectural changes.
   - Actively seek second opinions on high-complexity logic.

## Project Memories
- MMR classifier (best_textnoise) achieves 98.7% Precision and 87.5% Recall on the evaluation dataset.
- Focus on VRAM efficiency (limit: 8GB) for batch processing.
