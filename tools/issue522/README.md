# Issue #522 OMR-DLN を使わない hybrid 支持の検証ツール

production の変更（OMR-DLN の除去と x4 HOMR 五線片支持）を、#416 の受入契約のまま評価するためのツール。
harness は #519 / PR #520 のツールを引数で一般化したもの。

- 前提: manager checkout を `/workspace`、この worktree を `/workspace/.worktrees/issue522` にマウントすること。
  Full68 の再生には、#409/#416 と同じ image `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc` を使う。
  入力は git 管理外の `logs/issue409/full68-numbering-20261009/`（保持済みの producer 出力）、
  control 側の比較対象は `logs/issue519/ablation/control`（#416 受入出力と68/68一致を確認済み）。
- 出力は git 管理外の `logs/issue522/`。

| ツール | 用途 |
| --- | --- |
| `replay_support_variant.py --variant x4_staff_piece` | 保持 producer から、本番の `apply_x4_staff_piece_consensus_filter` と staff-stroke（x4 のみ）を使って dense route → CUDA CNN → Phase-A を再生する |
| `replay_mmr.py` / `replay_downstream.py` / `compare_downstream.py` | CUDA MMR、Phase-C（`PipelineOrchestrator`）と補正 GUI の適用経路、PDF、reviewed GT の監査。control と幾何で照合して比較する |
| `render_pdf_pinned.py` | #416 で受入済みの renderer（`b51c9f6f`）で PDF を生成する（現行 develop の renderer は control でも4ページで配置失敗するため） |
| `correction_roundtrip.py --reference control --candidate x4_staff_piece` | 同一の補正を保存・適用し、再開後に再適用する |
| `compare_variants.py`、`support_attribution.py`、`visualize.py` | 予測・Phase-A の差分、支持元の分離、重ね描き |

## 実行例（manager checkout から）

```bash
bash logs/issue522/full68/run.sh replay_support_variant.py --variant x4_staff_piece \
  --out /workspace/logs/issue522/full68/x4_staff_piece
python3 .worktrees/issue522/tools/issue522/compare_variants.py \
  --control logs/issue519/ablation/control --no-omr logs/issue522/full68/x4_staff_piece \
  --output logs/issue522/full68/compare_control_vs_x4.json
```

fresh E2E は、OMR-DLN の重みと Ultralytics を含まない image で、`scripts/docker_runtime_validation.sh` を実行する
（`configs/smoke_test.yaml` の 85/85 ゲート）。
