# Project Goals

## Ultimate / Very Long-Term Goal

Automatically add correct measure numbers to PDF sheet music with minimal human intervention.

---

## Long-Term Technical Direction

- Robust barline detection across diverse layouts
- Hybrid pipelines combining ML-based OMR and classical filtering
- Emphasis on explainability and debuggability
- 検出した小節線と楽譜情報（複数小節休みの記述や楽章の分割）などを用いた小節番号を数えるプログラムの作成
- pdfから一気貫通で（ある程度実用的な処理時間で）処理できるアプリケーションとしての整備

---

## Mid-Term Focus (Current Direction)

- Validate generalization on unseen PDFs
- Resolve remaining False Negatives (FN)
- Decide whether to pursue further heuristics, model retraining, or human-in-the-loop verification

---

## Explicit Non-Goals (Current)

- Further micro-optimization of purely local visual heuristics
- Large-scale dataset curation unless FN investigation requires it
