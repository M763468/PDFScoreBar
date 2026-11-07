# Issue #519 OMR-DLN 支持 ablation（評価専用ツール）

production の経路・モデル・閾値は変更しない。保持済みの #409 producer 出力から、
`control`（保持 OMR-DLN）と `no_omr`（OMR-DLN を使う両 consumer に空の箱リストを渡す）を
同一コード・同一 runtime で再生し、検出・最終番号・PDF・補正を比較する。

- 前提: manager checkout を `/workspace`、この worktree を `/workspace/.worktrees/issue519` にマウントすること。
  image は `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`（#409/#416 と同一）。
  入力は git 管理外の `logs/issue409/full68-numbering-20261009/`、比較基準は
  `logs/issue416/review-422-round3-20261016/` と `logs/issue416/verification-20261015/downstream-gpu_v1/`。
- 出力は git 管理外の `logs/issue519/`。このディレクトリ（`evidence/`）には軽量の要約と代表画像だけを置く。

| ツール | 役割 | 実行 commit |
| --- | --- | --- |
| `support_attribution.py` | hybrid consensus を再計算し、baseline HOMR 箱の支持元を分離 | `526ad6db` |
| `replay_omr_ablation.py` | dense route → staff-stroke → CUDA CNN → Phase-A。control が #416 出力と68/68一致することが前提条件 | `526ad6db` |
| `replay_mmr.py` | CUDA MMR を再生し、#415 reviewed GT で採点 | `a743be01` |
| `compare_variants.py` | 予測・Phase-A の差分 | `a743be01` |
| `replay_downstream.py` | 本番 Phase-C（`PipelineOrchestrator`）と補正 GUI の適用経路、PDF、GT 監査 | `f842c5e6` |
| `compare_downstream.py` | 段・小節を幾何で1対1照合し、最終番号・増分・行ラベル・描画画素を比較 | `aae0cfb2` |
| `render_pdf_pinned.py` | 固定した renderer（#416 で受入済みの `b51c9f6f`）で PDF を生成 | `aae0cfb2` |
| `visualize.py` | 原画像に GT・各 producer・最終予測・小節番号を重ねて描画 | `e1f2e3b3` |
| `correction_roundtrip.py` | レビューパッケージ → 同一補正の保存 → 適用 → 再開後の再適用 | `b4c135ef` |

## 結果の要約（`evidence/summary.json`）

- 検出（#416 ゲート）: control 3560/0/7 → no_omr TP3559 / FP0 / FN8。**旧ゲートでは FAIL**
  - 新規 FN は Prokofiev Sym5 p005 の1件。既存境界（小節#238|#239）の下側五線上の片である（`evidence/prokofiev5_p005_new_fn.jpg`）
- 段637 / 物理小節3287 は幾何で1対1に対応した。Phase-C の最終番号・増分・ページ間の伝播の差は0。
  MMR は 171/3/3/0 で、override の差は0ページ。reviewed GT の誤りと row samples の不一致は両者で同一の既知誤り
- PDF:
  - #416 で受入済みの renderer では 68/68 ページ画素一致（両 variant とも #416 受入 PDF とも一致）
  - 現行 develop の renderer は control でも4ページで配置失敗する（OMR とは独立の既存問題）
- 補正: 保存・適用・再開とも差分0。補正後 PDF は21/21ページ画素一致
- 未検証: ブラウザでの GUI 操作、性能、Full68 以外のデータ

## 再現手順（manager checkout から）

```bash
bash logs/issue519/ablation/run_variant.sh control      # 続けて no_omr
bash logs/issue519/ablation/run_mmr.sh control          # 続けて no_omr
bash logs/issue519/downstream-20261108/run_downstream.sh control   # 続けて no_omr
```

ラッパースクリプト（`wrappers/` に同一内容の写し）はどれも、上記 image と同じマウント構成の使い捨てコンテナで、各ツールを起動する。
