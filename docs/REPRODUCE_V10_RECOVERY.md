# 再現手順ガイド: Issue #117 100% Recall/Precision 回復

## 1. 動作環境
- **Docker Image**: `pdfscore_pipeline_gpu`
- **Resource**: NVIDIA GPU (CUDA対応) 推奨

## 2. 再現用設定 (Golden Settings)
ソースコードのデフォルト値が既にこれらの設定に更新されていますが、明示的に指定する場合は `configs/verify_fixed_v10.yaml` を使用します。

主要パラメータ:
- `ink_threshold: 180`
- `min_ratio: 0.50`
- `vertical_closing: 4`
- `enable_heuristic_filters: true`
- `candidate_filter_kwargs`:
    - `left_margin_ratio: 0.25`
    - `min_ink_ratio: 0.70`
    - `min_staff_overlap_ratio: 0.15`

## 3. 実行手順
以下のコマンドでパイプラインを実行します。

```bash
docker run --rm --gpus all -v $(pwd):/workspace -w /workspace -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu /opt/venv_pipeline/bin/python src/pipeline/main.py \
  --config configs/verify_fixed_v10.yaml
```

## 4. 評価手順
実行完了後、生成された `logs/full_pipeline_runs/YYYYMMDD_HHMMSS` ディレクトリを対象に以下のスクリプトを実行します。

```bash
source .venv_pdf/bin/activate
python tools/repro_accuracy/verify_pipeline_accuracy.py --run-dir logs/full_pipeline_runs/20260329_114731
```

## 5. 現在の達成精度 (Run 15基準)
| Dataset | Recall | Precision | TP | FP | FN |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Festival Overture** | **100.0%** | **100.0%** | 351 | 0 | 0 |
| **Symphony No. 5** | **99.6%** | **99.9%** | 950 | 1 | 4 |
| **Prokofiev Sym No. 1** | **99.5%** | **99.6%** | 544 | 2 | 3 |
| **Prokofiev Sym No. 5** | **99.8%** | **100.0%** | 498 | 0 | 1 |
| **Sibelius Violin Conc.** | **98.1%** | **99.3%** | 670 | 5 | 13 |

## 6. 今後の課題 (残存エラーの分析)
現在残っている FN の多くは以下の理由によるものです：
1. **CNNの過学習/汎化不足**: SR画像特有のアーティファクトに対し、CNNが低いスコア（< 0.4）を出し、フィルタリングされているケース。
2. **インク密度閾値**: `min_ink_ratio: 0.70` は非常に強力ですが、極端にかすれた正解小節線まで弾いてしまうケースが数件確認されています（Sibelius等）。
