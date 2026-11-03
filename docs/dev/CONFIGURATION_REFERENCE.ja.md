# パイプラインの設定と実行入口のリファレンス

<!-- translation: {"original":"CONFIGURATION_REFERENCE.md","source":{"sha256":"54e4b2675e261b6063e8c44e524a57c781e75791b1b8d30f58f1beeb1d65e472"},"state":"reviewed"} -->

[English / 原文](CONFIGURATION_REFERENCE.md)（英語正本）

翻訳元: same PR / SHA-256 `54e4b2675e261b6063e8c44e524a57c781e75791b1b8d30f58f1beeb1d65e472`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

このリファレンスは、開発用パイプラインの起動方法と、正規の本番設定 `configs/dense_full_pipeline.yaml` の各キーが何を制御するかをまとめたものです。現在のソースの挙動を説明するもので、既定値を変えたり新しい設定を定めたりはしません。PR検証ワークフローで実行する `tests/test_configuration_reference.py` は、正規の設定のキーが本書または英語の原文のキーの表にない場合、複数回記載されている場合、記載した値が正規の値と異なる場合に失敗します。意味の列は検査しません。

配布パッケージの利用者は、このファイルを直接編集しません。[利用者ガイド](../USER_GUIDE.ja.md)に従って `docker/distribution.py` を使います。

## 実行入口

| 入口 | 対象 | 補足 |
| --- | --- | --- |
| `python3 docker/distribution.py build / preflight / run / review` | 配布パッケージの利用者 | [利用者ガイド](../USER_GUIDE.ja.md)を参照してください。 |
| `bash scripts/docker_runtime_validation.sh [--config PATH] [--preflight-only] [--service-readiness-smoke] [--pipeline-only]` | 開発者 | Docker ランタイムの契約を検証し、指定した config（既定は `configs/smoke_test.yaml`）を実行します。環境変数: `DOCKER_IMAGE`、`DOCKER_EXTRA_ARGS`、`PDFSCORE_SR_COMPILER_CACHE`、`PDFSCOREBAR_MODEL_CACHE`、`OMR_DLN_MODEL_PATH`。 |
| `python -m src.pipeline.main --config PATH [options]` | 開発者（準備済みの環境内） | パイプラインを直接実行します。マウントとイメージの来歴は呼び出し側の責任です。 |
| `make <target>` | 開発者 | [Makefile サーフェス](../MAKEFILE_SURFACE.ja.md)を参照してください。 |

### `src.pipeline.main` のオプション

| オプション | 効果 |
| --- | --- |
| `--config PATH` | 必須の YAML 設定。 |
| `--run-id ID` | `run.run_id` を上書きします。 |
| `--output-root PATH` | `run.output_root` を上書きします。 |
| `--dry-run` | コマンドを実行せずにログに出します。 |
| `--validate-only` | 入力の解決とページのフィルタの後で停止します。 |
| `--skip-existing` | 出力ファイルがすでにあるステップをスキップします。 |
| `--page-limit N` | 解決したページのうち先頭の `N` ページだけを処理します。 |
| `--debug` | 中間のデバッグ用ファイルを書き出します。 |
| `--progress-jsonl PATH` | 構造化された進捗イベントを JSON Lines で書き出します。 |
| `--telemetry-summary PATH` | 簡潔なステージ・リソースの概要を書き出します。 |
| `--sample-resources` | 軽量なプロセスツリー・GPU のサンプリングを有効にします。 |
| `--resource-sample-interval-seconds S` | サンプリングを有効にしたときの間隔（既定 `1.0`）。 |

### 実行ディレクトリの優先順位

実行ディレクトリは `<output_root>/<run_id>` です。`--run-id` は `run.run_id` より優先されます。どちらも設定されていない場合は、`YYYYMMDD_HHMMSS` 形式のタイムスタンプを使います。`--output-root` は `run.output_root` より優先され、`run.output_root` の既定値は `logs/full_pipeline_runs` です。Issue に紐づく作業では、`AGENTS.md` に従い `logs/issue<N>/` の下の出力ルートを選んでください。

## 正規の設定のキー

正規の設定にある検出器、CNN、フィルタ、番号付けの値は、受け入れ済みの本番のパラメータです。これらのいずれか、またはモデルを変更することは、`AGENTS.md` の評価の規則と[検証方針](VALIDATION_POLICY.ja.md)のもとで新しい実験になり、以前の受入結果を引き継ぎません。

### `run`

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `run.run_id` | `dense_full_pipeline` | 実行ディレクトリの名前。上の優先順位を参照してください。 |
| `run.output_root` | `logs/full_pipeline_runs` | 実行ディレクトリの親ディレクトリ。 |

### `inputs`

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `inputs.pdf_to_images.output_dir` | `data/evaluation2/images` | PDFのレンダリングを無効にしたときに使うページ画像のディレクトリ。隔離したPDFジョブの実行器はこれを取り除き、ジョブの作業領域にレンダリングします。 |
| `inputs.pdf_to_images.image_glob` | `page_*.png` | ページ画像を見つけるためのパターン。 |

### `steps`

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `steps.pdf_to_images` | `false` | 検出の前に `inputs.pdf_path` をページ画像にレンダリングします。 |
| `steps.detection` | `true` | 小節線の検出を実行します。 |
| `steps.filter_pages` | `true` | **現在のソースでは読まれていません。** ページのフィルタ（`filters`）は常に判定されます。このキーには効果がありません。 |
| `steps.apply_barline_overrides` | `false` | 番号付けのときに `inputs.barline_overrides` を適用します。 |
| `steps.numbering_base` | `true` | 基本の小節番号付けのフェーズを実行します。 |
| `steps.mmr_overrides` | `true` | 複小節休符の認識とその上書きを実行します。 |
| `steps.apply_measure_overrides` | `true` | 最終的な番号付けに小節の上書きを適用します。 |
| `steps.overlay` | `false` | 番号付けのオーバーレイ画像を描画します（開発専用。配布物からは除外）。 |

### `detection`

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `detection.source_concurrency.workers` | `1` | SR の終了後に並行して動かすページソースの worker 数。2 worker は検証済みの環境でだけ選ぶ任意の設定です。[source の並行処理](../performance/issue458-source-concurrency.md)を参照してください。 |
| `detection.source_concurrency.timeout_sec` | `900` | ページソースの処理のタイムアウト。 |
| `detection.source_concurrency.on_unavailable` | `error` | 要求した並行数を使えない場合の挙動。同じ文書を参照してください。 |
| `detection.omr_job_reuse.mode` | `auto` | `auto` は下記の実測済み範囲で OMR-DLN をジョブ単位で1回だけ起動します（順序付き全ページでモデルを1回ロード）。`off` はページごとに OMR プロセスを起動します。経路はジョブ開始前に確定し、失敗時にもう一方の経路へフォールバックしません。[OMR job reuse](../performance/issue459-omr-job-reuse.md) を参照。 |
| `detection.omr_job_reuse.min_pages` | `2` | ジョブ経路を使う最小ページ数。1ページのジョブはページ単位の経路を使います。 |
| `detection.omr_job_reuse.allowed_uids` | `[0]` | ジョブ経路を使うプロセス UID。標準 deployment は root です。それ以外の UID はページ単位の経路を使います。 |
| `detection.omr_job_reuse.timeout_sec` | `900` | OMR job worker のタイムアウト。超過するとプロセスグループを kill し、ジョブは失敗します。 |
| `detection.enable_sr` | `true` | HOMR の推論の前に超解像を実行します。 |
| `detection.sr_scale` | `4` | 超解像の倍率。 |
| `detection.sr_compile_mode` | `reduce-overhead` | バッチ SR worker のモデルのコンパイルモード。 |
| `detection.homr_profile` | `maintained_original` | 保守対象の HOMR ランタイムのプロファイル。 |
| `detection.detector_route` | `dense_full_pipeline` | 検出器の経路。探索・比較のモデルモードはこの経路を必要とします。 |
| `detection.probe_use_original_images` | `true` | 探査検出は、SR の出力ではなく元のページ画像を読みます。 |
| `detection.crop_recenter_on_bbox_ink` | `true` | CNN の切り出しをボックス内のインクに合わせて中心を調整します。 |
| `detection.hybrid_output_root` | `logs/full_pipeline_runs/dense_full_pipeline/hybrid_output` | 検出器の中間成果物の出力ルート。 |
| `detection.band_source` | `row_stats` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.band_cluster_max_dist` | `25.0` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.ink_threshold` | `240` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.min_ratio` | `0.60` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.min_height_ratio` | `0.006` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.min_width_ratio` | `0.0` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.probe_width` | `4` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.max_per_band` | `80` | 受け入れ済みの探査検出器のパラメータ。 |
| `detection.enable_heuristic_filters` | `true` | 下の候補のヒューリスティックなフィルタを適用します。 |
| `detection.candidate_filter_kwargs.left_margin_ratio` | `0.12` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.clef_left_ratio` | `0.25` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.min_height_median_ratio` | `0.6` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.ink_threshold` | `180` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.min_ink_ratio` | `0.18` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.paper_threshold` | `200` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.min_paper_overlap_ratio` | `0.6` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.candidate_filter_kwargs.min_staff_overlap_ratio` | `0.02` | 受け入れ済みの候補フィルタのパラメータ。 |
| `detection.cnn_model_manifest` | `models/barline_cnn/manifest.json` | 選定済みの CNN モデルの manifest。[モデル資産の契約](../MODEL_ARTIFACT_CONTRACT.ja.md)を参照してください。 |
| `detection.cnn_threshold` | `0.4965248107910156` | CNN の採用閾値。本番モードでは manifest と一致する必要があります。 |
| `detection.cnn_apply_nms` | `false` | CNN のスコアリングでの NMS（受け入れ済みの既定は無効）。 |
| `detection.divisi_rescue` | `true` | 受け入れ済みの救済のスイッチ。 |
| `detection.scan_gap_rescue` | `true` | 受け入れ済みの救済のスイッチ。 |
| `detection.scan_gap_threshold_ratio` | `1.5` | 受け入れ済みの救済のパラメータ。 |
| `detection.scan_gap_rescue_min_ratio` | `0.3` | 受け入れ済みの救済のパラメータ。 |
| `detection.scan_x_peak_rescue` | `true` | 受け入れ済みの救済のスイッチ。 |
| `detection.scan_rightmost_rescue` | `true` | 受け入れ済みの救済のスイッチ。 |
| `detection.scan_center_on_peak` | `true` | 受け入れ済みの救済のスイッチ。 |

### `filters`

これらの設定のページ番号は 1 始まりです。

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `filters.blank_page` | `auto` | `auto` は各ページを測定します。真偽値はすべてのページの結果を固定します。リストは記載したページに印を付けます。 |
| `filters.blank_page_config.pixel_threshold` | `245` | 空白ページの測定のパラメータ。 |
| `filters.blank_page_config.max_ink_ratio` | `0.003` | 空白ページの測定のパラメータ。 |
| `filters.blank_page_config.max_stddev` | `12.0` | 空白ページの測定のパラメータ。 |
| `filters.staff_detect` | `auto` | 五線検出の失敗について、`blank_page` と同じ形の値を取ります。 |
| `filters.staff_detect_config.min_nonzero_ratio` | `0.001` | 五線検出の測定のパラメータ。 |
| `filters.user_exclude` | `[]` | 利用者が除外したページ。 |

### `mmr`

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `mmr.model_path` | `models/mmr/mmr_classifier_best.pth` | 追跡している本番の MMR 分類器。 |
| `mmr.ocr_lang` | `eng` | **現在のソースでは読まれていません。** このキーには効果がありません。 |
| `mmr.enable_rotation_tta` | `false` | MMR OCR での回転によるテスト時拡張。 |

### `numbering`

| キー | 正規の値 | 意味 |
| --- | --- | --- |
| `numbering.force_single_system` | `false` | 各五線をそれぞれ独立した段として扱います（1段に1五線）。 |

## 他の文書で定めている任意のキー

次のキーは正規の設定にはありません。その所有文書が定義しており、この一覧は参照先を示すだけです。

| キー | 所有文書 |
| --- | --- |
| `detection.model_validation`、`detection.cnn_model_path`、`detection.cnn_device`、`detection.omr_dln_model_path`、`detection.omr_dln_device`、`detection.model_sha256` | [開発用モデルの選定](EXPERIMENT_MODEL_SELECTION.md) |
| その他の `detection.source_concurrency` の設定 | [source の並行処理](../performance/issue458-source-concurrency.md) |
| `mmr.rapidocr_provider` | [MMR RapidOCR のプロバイダモード](MMR_RAPIDOCR_PROVIDER.ja.md) |
| `inputs.movement_boundaries` | [楽章境界の契約](../MOVEMENT_BOUNDARY_CONTRACT.ja.md) |
| `outputs.review` | [手動補正のレビューパッケージ](../manual_correction_review_package.ja.md) |

`inputs.pdf_path`、`inputs.barline_overrides`、`inputs.measure_overrides`、`mmr.debug_root` など、ソースが読むその他のキーは、個別の所有文書のない開発用の入力です。使う前に、それを読むソースを確認してください。
