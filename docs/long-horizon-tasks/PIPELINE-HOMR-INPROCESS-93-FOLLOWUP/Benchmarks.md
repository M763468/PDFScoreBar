# Benchmarks for Follow-up Refactoring

This document tracks the precision and recall during the in-process and in-memory refactoring to ensure no regressions occur compared to the established baselines from Issue #25.

## Baseline (Issue #25 Reference on 68 pages of eval2)

| 構成 (Configuration) | 全体 Recall | TP / **FN** | FP | VRAM |
| :--- | :---: | :---: | :---: | :---: |
| **SR x2 (実用・高精度モード)** | **100.0%** | 3580 / **1** | **0** | 中 |

*(※ x4は時間がかかりすぎ、Bypassは精度が出ないため、最高精度かつ時間効率のよいSR x2モードを基本構成として検証を行います。)*

## Current Execution Results

| Milestone | Configuration | Recall / F1 | TP / FN / FP | Latency per page | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M1 & M2: in-process & in-memory** | SR x2 | 99.61% / 0.9971 | 3567 / 14 / 7 | ~100s (SR phase) | Full 73-page run (68 scored). Slight regression vs #25. |
| **Final Verification** | SR x2 | 99.61% / 0.9971 | 3567 / 14 / 7 | ~100s | Verified in-process stability. |

## Verification Commands

**1. SR x2 Evaluation** (Expected: FN=~1, FP=0)
```bash
make run-pipeline CONFIG=configs/evaluation2_sr_x2.yaml
```

*(実行に失敗する場合や直接実行する場合は、必ず標準出力を `> artifacts/eval.log` 等にリダイレクトすること。)*
