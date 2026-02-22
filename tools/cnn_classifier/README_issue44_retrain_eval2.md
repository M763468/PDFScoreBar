# CNN Barline Classifier Retrain (Issue #44) Workflow

## Purpose

`evaluation2` の再作成 GT（68ページ）を使って、小節線候補の真偽判定 CNN を再学習し、
スコアリング・評価までを再現可能に実行するための手順をまとめる。

本 workflow では「run ごとの外部設定ファイル (`--config`)」を使い、どの候補セット・どの閾値・どの出力先を使ったかを追跡しやすくする。

## Config Files (Issue #44 baseline)

- `configs/cnn_barline_runs/issue44_baseline_v1/dataset_build.yaml`
- `configs/cnn_barline_runs/issue44_baseline_v1/train.yaml`
- `configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch.yaml`
- `configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global.yaml`

## Scripts and Roles

### 1) `tools/cnn_classifier/build_cnn_dataset.py`

Role:
- CNN 学習用 crop dataset を作成する
- TP/FP crop 抽出（local / evaluation2 / DeepScores）を実行する
- train/val/test split と metadata を生成する

Issue #44 で重要な入力:
- `evaluation2` GT (`data/evaluation2/annotations`)
- `evaluation2` images (`data/evaluation2/images`)
- 候補 JSON 群（Issue #44 baseline では `logs/issue36_prep/probe_candidates_filtered_v12`）

Main outputs:
- `splits/train/{tp,fp}`
- `splits/val/{tp,fp}`
- `splits/test/{tp,fp}`
- `metadata/samples.csv`
- `metadata/stats.json`

Usage example:
```bash
.venv_cnn_classifier/bin/python tools/cnn_classifier/build_cnn_dataset.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/dataset_build.yaml
```

Useful overrides:
- `--output-root <path>`: runごとの出力先を変える
- `--skip-local`, `--skip-eval2`, `--skip-deepscores`: 部分実行
- `--only-split`: 既存 crop から split/metadata のみ再生成

### 2) `experiments/cnn_classifier/train.py`

Role:
- 生成済み dataset を使って CNN モデルを学習する
- TensorBoard logs, best model, checkpoints を保存する
- validation で閾値最適化（`--optimize-threshold`）を行える

Main outputs (work dir):
- `cnn_classifier_best.pth`（実際の保存名はスクリプト実装に従う）
- TensorBoard logs (`runs/`)
- 学習ログ / metrics

Usage example:
```bash
.venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/train.yaml
```

Useful overrides:
- `--work-dir logs/cnn_barline_classification/<run_id>`
- `--tp-dir`, `--fp-dir`: split を使わず明示ディレクトリ指定
- `--epochs`, `--batch-size`, `--num-workers`

Note:
- `--config` から boolean フラグ（`amp`, `compile`, `channels_last`, `optimize_threshold`）も読み込めるように調整済み。

### 3) `tools/cnn_classifier/score_candidates_batch.py`

Role:
- 候補 JSON（`pipeline2_no_peak_candidates.json`）に対して学習済み CNN を適用
- 各ページに `*_scored.json` / `*_filtered_cnn.json` を保存

Expected input layout:
- `<logs_root>/<score>/<page>/pipeline2_no_peak_candidates.json`
  - 例: `logs/issue36_prep/probe_candidates_filtered_v12/Shostakovich-Sym5-Va/page_010/pipeline2_no_peak_candidates.json`

Main outputs:
- `pipeline2_no_peak_scored.json`
- `pipeline2_no_peak_filtered_cnn.json`

Usage example:
```bash
.venv_cnn_classifier/bin/python tools/cnn_classifier/score_candidates_batch.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch.yaml
```

Useful overrides:
- `--model <path/to/cnn_classifier_best.pth>`
- `--threshold 0.1`（保存する filtered JSON の閾値）

### 4) `tools/re_evaluate_global.py`

Role:
- `*_scored.json` を読み込み、GT と greedy matching で global evaluation を集計
- TP/FP/FN / Recall / Precision を score別・全体で集計
- CSV に保存

Main outputs:
- per-page summary CSV（`output_csv`）
- 標準出力の集計サマリ

Usage example:
```bash
python tools/re_evaluate_global.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global.yaml
```

Useful overrides:
- `--threshold 0.5`（採用判定閾値）
- `--output-csv logs/.../global_summary.csv`

## Recommended Execution Order (Issue #44)

1. Dataset build
```bash
.venv_cnn_classifier/bin/python tools/cnn_classifier/build_cnn_dataset.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/dataset_build.yaml
```

2. Training
```bash
.venv_cnn_classifier/bin/python experiments/cnn_classifier/train.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/train.yaml
```

3. Update scoring config with trained model path
- `configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch.yaml` の `model` を実際の保存モデルに合わせる

4. Batch scoring
```bash
.venv_cnn_classifier/bin/python tools/cnn_classifier/score_candidates_batch.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/score_candidates_batch.yaml
```

5. Global evaluation
```bash
python tools/re_evaluate_global.py \
  --config configs/cnn_barline_runs/issue44_baseline_v1/evaluate_global.yaml
```

## Reproducibility Notes

- run ごとに使用した config を `logs/cnn_barline_classification/<run_id>/` にコピーして保存することを推奨
  - 例: `run_config_dataset_build.yaml`, `run_config_train.yaml`, `run_config_score.yaml`, `run_config_eval.yaml`
- 併せて保存推奨:
  - `git rev-parse HEAD`
  - 実行日時
  - 実行環境（host / container, Python version）

