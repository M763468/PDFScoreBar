# スクリプト管理とディレクトリ運用ルール

このドキュメントでは、本プロジェクトにおけるスクリプトの配置ルールと、2026年1月に行われた大規模なスクリプト整理について記述します。

## ディレクトリ運用ルール

スクリプトや一時ファイルの散逸を防ぐため、以下のルールに従ってファイルを配置してください。

### 1. `tools/` (汎用ツール)
- **用途**: プロジェクト全体で繰り返し使用される汎用的なCLIツールやユーティリティ。
- **基準**:
    - 特定のデバッグ局面だけでなく、将来も再利用が見込まれるもの。
    - 他のスクリプトからインポートされる共通ライブラリ的なコード。
- **アンチパターン**: `debug_page3_fix.py` のような「特定のバグ修正確認のためだけの捨てコード」はここに入れないでください。

### 2. `experiments/` (実験・調査)
- **用途**: 特定の仮説検証、パラメータ調整、新機能のプロトタイピング。
- **推奨構造**: `experiments/<トピック名>/` のサブディレクトリを作成して管理する。
    - 例: `experiments/cnn_classifier_tuning/`
    - 例: `experiments/issue53_probe_rescue/`: プローブ救済機能の全パイプライン評価用（2026年3月追加）。
- **完了後**: 実験が終了し、得られた知見がコード本体やドキュメントに反映されたら、実験コードはそのまま残すか、不要なら `legacy` へ移動または削除します。


### 3. `tmp/` (一時ファイル)
- **用途**: **Git管理しない**一時的なスクリプト、ログ、中間生成ファイル。
- **特徴**: `.gitignore` に登録されており、リポジトリにはコミットされません。
- **ルール**: 「とりあえず動かして確認したい」コードはまずここで作成してください。有用性が確認できたら `tools/` や `experiments/` へ昇格させてコミットします。

## 2026年1月の整理記録

開発初期に作成された大量の実験スクリプトや一時ファイルがルートディレクトリや `tools/` に混在していたため、大規模な整理を行いました。

### 実施内容
- **ルートディレクトリ**: `main.py` などのエントリポイント以外を移動・削除。
- **tmpディレクトリ**: Git管理されていたファイルを削除または適切な場所へ移動し、ディレクトリ自体を `.gitignore` 対象に変更。
- **toolsディレクトリ**: 再利用性の低いワンショットスクリプト（`debug_*.py`, `temp_*.py` 等）を削除またはアーカイブ。

### ファイルの処置一覧

#### アーカイブされたファイル (`experiments/legacy/` 配下)
ドキュメント等で言及があり、歴史的経緯として残す価値があると判断されたものは `experiments/legacy/` へ移動しました。

- **Root -> experiments/legacy/scripts/**
    - `run_omr_dln_sweep.sh`: OMR-DLN パラメータスイープ実験。
    - `run_parameter_sweep.sh`: 初期のパラメータスイープ。
- **tmp -> experiments/legacy/tmp_archive/**
    - `run_gt_rebuild_eval.sh`: GT再構築評価用。
- **tmp -> experiments/legacy/investigation_20260102/**
    - `investigation_20260102/`: 特定時期の調査ログ。
- **tools -> experiments/legacy/tools_archive/**
    - `debug_end_bar_removal.py`, `detect_hbar_test.py`
    - `experiment_gap_connection.py`, `experiment_rest_ocr.py`, `fn_crop_experiment.py`
    - `run_confirmed_union_eval.sh`, `run_gt_rebuild_hybrid_eval.sh`
    - `run_homr_tuning.py`, `run_phase5b_srcheck.sh`
    - `run_promiscuous_union_eval*.sh`, `run_regression_template.sh`
    - `test_morphological_closing.py`

#### 移動・昇格されたファイル
有用性が認められ、適切な場所へ配置し直されたファイルです。

- `extract_fn_barlines.py` (Root) -> `tools/extract_fn_barlines.py`
- `tmp/diagnose_fn.py` -> `tools/diagnose_false_negatives.py`

#### 削除されたファイル
ドキュメントでの言及がなく、再現性や再利用性がないと判断された一時ファイル群です。
これらはGitの履歴から復元可能ですが、現在のHEADからは削除されています。

- **Root**: `compare_gt_versions.py`, `debug_scale.py`, `run_batch_candidates.sh`
- **tmp**: `diagnose_fn_standalone.py`, `measure_numbering_issue_drafts.md`, `render_gt_pred_overlay.py`, `fn_attribution_preds/`
- **tools**:
    - `compare_batch_structure_v2.py`, `create_sr_test_crop.py`
    - `debug_divisi_page3.py`, `debug_gap_pixels.py`, `debug_p016_alignment.py`
    - `debug_phase4_fix.py`, `debug_probe.py`, `dummy_score_candidates.py`
    - `fix_gt_config_paths.py`
    - `run_eval2_batch.py`, `run_eval2_filter.py`, `run_eval2_no_peak.py`
    - `temp_analyze_overlap.py`, `test_aligned_connection.py`, `test_realesrgan.py`

## 今後の開発における注意点

新しいスクリプトを作成する際は、以下のフローを検討してください。

1. **既存ツールの確認**: 似た機能を持つツールが `tools/` にないか確認する。機能追加で対応できないか検討する。
2. **配置場所の決定**:
    - 一時的な確認 -> `tmp/`
    - 実験的な試行錯誤 -> `experiments/<topic>/`
    - 汎用ツール -> `tools/`
3. **命名**: ファイル名だけで目的がわかるようにする（`temp.py`, `test.py` は避ける）。
