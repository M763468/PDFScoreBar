# E2E Verification Report: Issue #13 (Batch Optimization & VRAM Management)

## 1. 概要
Issue #13 の目的であるパイプラインの統合検証、バッチ最適化の効果、および VRAM 管理（RTX 4060 8GB）の妥当性を、`evaluation2` サブセットを用いて検証した。

## 2. 検証環境
- **GPU**: NVIDIA GeForce RTX 4060 (8GB VRAM)
- **Container**: `sr_eval_gpu` (Ubuntu based, PyTorch + ONNX Runtime CUDA)
- **Dataset**: `evaluation2` subset (Va_Prokofiev_Symphony1.pdf, Pages 1-3)

## 3. 計測結果
### VRAM 使用量 (MiB)
- **Idle**: 42 MiB
- **Peak**: 821 MiB
- **Average (Active)**: ~650 MiB

### 処理時間 (3ページ合計)
- **Total**: 約 13 分 (746.259s)
- **内訳 (推計)**:
    - PDF変換: 数秒
    - Hybrid Detection (Homr baseline/SR): 各ページ 約 2 分 (CPU主導 + ONNX)
    - Probe Scan: 数秒 (CPU)
    - CNN Scoring: 数秒 (GPU)
    - Numbering & MMR: 各ページ 約 30 秒 (サブプロセス)

## 4. 考察
- **VRAM効率**: 8GB に対してピーク 1GB 未満であり、RTX 4060 環境において十分な余裕がある。複数の PDF を並列で処理するか、バッチサイズを拡大する余地がある。
- **ボトルネック**: 処理時間の大部分が Hybrid Detection (Homr) に費やされている。これは現状 CPU 主体の処理が多く含まれるためである。
- **安定性**: MMR モデルをサブプロセスで実行する戦略により、メインプロセスのメモリ蓄積を防ぎ、クリーンな終了とメモリ解放が実現されている。

## 5. 推奨される次のアクション
- **リジューム機能の実装**: `main.py` に、中間生成物（`numbering_base.json` 等）が既に存在する場合にステップをスキップするオプションを追加する。
- **CPU 並列化**: `probe_scan` や `PDF変換` などの CPU バウンドな処理を `multiprocessing` で並列化することを検討する。
- **VRAM 最適化**: 現状余裕があるため、より大規模なデータセット（全体評価）へ移行しても問題ない。

---
Created on 2026-03-03
