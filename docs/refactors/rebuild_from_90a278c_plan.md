# 90a278c Baseline Reconstruction Plan (Master Strategy)

## 1. Baseline Verification (Audit Result)

Audit performed on 2026-04-12.

- **Target Commit**: `90a278c668e148a68d5a8c3c19c067bb5ff29649`
- **Status**: **Engineering Baseline**
- **Verification Findings**:
    - **Docs vs Code**: `ISSUE44_ITER7_FINAL_REPORT.md` (99.9% recall) は研究用スクリプトの成果。
    - **Root Cause**: 統合パイプライン (`orchestrator.py`) では環境不整合や過剰フィルタにより再現不可（~80 TP/page1）。
- **Baseline Accuracy**: ~99.9% Recall / 100% Precision (研究用スクリプト時)。

---

## 2. Re-implementation Targets (Functional Groups)

`90a278c` 以降の変更を以下のグループに分け、各フェーズで再実装する。

| グループ | 内容 | 参照コミット |
| :--- | :--- | :--- |
| **A. Infra/Perf** | In-process 実行化, Batch Orchestrator | `ecec76c`, `4177e7a`, PR #91 |
| **B. Func BugFix** | PDFページ範囲, Type Error, CPU Fallback | `dad6801`, `14e9819`, `2a28600` |
| **C. Env/Build** | Dockerfile 統合, Makefile 強化 | PR #116, `f2de576` |
| **D. Logic Fix** | Tall Band 対策, 丸め誤差修正 | `c12c600`, `29b090b` |
| **E. Precision** | 100% Recall 核心ロジック, 閾値一貫性 | `f0e923f`, `64d9a37`, `7108a78` |

---

## 3. Phased Roadmap & Gates

### Phase 1: Foundation (A, C + Tools)
- **Goal**: 計測ツールの整備と In-process 高速化基盤の復元。
- **Gate**: **Stability**. 68ページの評価が完走すること。

### Phase 2: Functional Integrity (B, D)
- **Goal**: 機能不具合の解消とサイレントバグ（精度低下要因）の排除。
- **Gate**: **Precision 100.0%**. FP ゼロを絶対維持。

### Phase 3: Accuracy Alignment (E)
- **Goal**: 100% Recall ロジックの再導入。
- **Gate**: **TP=3580 / FN=1 / FP=0**. (Historical Ceiling `bc23deb` 相当)

### Phase 4: Finalization
- **Goal**: 文書化と `develop` への合流。

---

## 4. Operational Rules

1.  **No Cherry-pick**: `d76d32a` からの直接マージは禁止。コードを読み取り、`90a278c` の構造に合わせて再実装する。
2.  **Zero Tolerance**: Precision < 100% の場合は、そのフェーズを却下し、前の stable 状態に戻す。
3.  **Traceability**: すべてのロジック変更は `docs/refactors/` に履歴を残す。
