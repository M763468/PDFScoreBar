# 正規モデル資産の契約

<!-- translation: {"original":"MODEL_ARTIFACT_CONTRACT.md","source":{"sha256":"47fb00be61560b573543252932c0e7e23528b72dafe164ccfdd985fd46508167"},"state":"reviewed"} -->

[English / 原文](MODEL_ARTIFACT_CONTRACT.md)

本文書は、保守対象のDockerおよびproduction runtimeが使用するモデル・重みの識別情報を記録する。[環境文書](../dev/ENVIRONMENTS.md)を補完するものであり、モデルの選定や検証を行ったIssueから責任を移すものではない。処理の概要は[アーキテクチャ概要](../architecture/PIPELINE_ARCHITECTURE.ja.md)、詳細は[実装リファレンス](../architecture/PIPELINE_ARCHITECTURE_REFERENCE.ja.md)を参照。

共通ルールは次のとおり。

```text
論理モデルID -> 選択されたバージョン -> 来歴 -> 期待される完全性の識別情報
```

ダイジェストはモデル系列に永続的に属するのではなく、選択されたバージョンに属する。同じバージョンと来歴のままバイト列を置き換えることは完全性違反である。意図したモデル更新では新しいバージョン・来歴・ダイジェストを登録し、キャッシュ内で過去のバージョンと共存できる。

## パスと所有権の規約

- リポジトリ管理のダウンロード可能な資産には `src.common.model_artifacts` を使う。既定は `$XDG_CACHE_HOME/pdfscorebar/models/<model-id>/<version>/<asset>`、`XDG_CACHE_HOME` 未設定時は `~/.cache/pdfscorebar/models/<model-id>/<version>/<asset>`。`PDFSCOREBAR_MODEL_CACHE` でキャッシュルートを明示的に上書きできる。
- イメージが所有する資産は `/workspace` の外、通常は `/opt/pdfscore-assets` 以下に置く。これにより、作業中のチェックアウトのbind mountで隠れない。
- 外部・運用者提供の資産は可能な限り同じホスト側のバージョン名前空間に登録し、`/opt/pdfscore-external/<model-id>/<version>/...` 以下に読み取り専用でマウントする。
- パスを明示する環境変数は互換性維持・上書き用である。manifestが選択バージョンの完全性の識別情報を管理する場合、環境変数で指定したパスでもその検証を迂回してはならない。

## 資産一覧

### 小節線CNN

- 論理モデルID: `barline-cnn`
- 選択バージョン: `issue296-d27-v1`
- 来歴: `models/barline_cnn/manifest.json`。採用された #296 D27 checkpointを #315 のproduction資産移行で公開
- 期待SHA-256: `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`
- 所有: リポジトリ管理のrelease資産。正規smoke用コピーはイメージが所有
- ホスト上の配置: `$XDG_CACHE_HOME/pdfscorebar/models/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth`（または `~/.cache/pdfscorebar/models` へのフォールバック／`PDFSCOREBAR_MODEL_CACHE` による上書き）
- コンテナruntime: `/opt/pdfscore-assets/model-cache/...` 以下に配置され、smoke検証には `/opt/pdfscore-assets/barline_cnn_smoke.pth` で公開
- 解決・配置: `src.common.model_artifacts`
- 明示的上書き: `PDFSCOREBAR_MODEL_CACHE` はキャッシュルートを変更する。production CNNのモデル選択はこのDocker契約ではなく #315／設定が管理する
- 更新手順: 意図して選んだ置換バイト列を公開し、新しいモデルバージョンとrelease来歴を割り当て、manifestにダイジェストを記録してから配置・検証する。`issue296-d27-v1` のバイト列を差し替えない。

### OMR-DLN小節検出器（#522で廃止）

- 論理モデルID: `omr-dln-measures` — **選択対象から外した**。バージョン `phase1-validated-v1`（SHA-256 `00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212`）は、#416／#519 までの受入結果の来歴としてのみ残す。
- `models/omr_dln/manifest.json`、OMR-DLN worker と job 経路、`OMR_DLN_MODEL_PATH`、Docker のマウントを削除した。hybrid の支持には x4 HOMR の五線片支持（`src/pipeline/steps/hybrid_consensus.py`）を使う。OMR-DLN を指定したままの設定は明示的にエラーになり、旧重みへの fallback はない。

### first-party x4 SR（`pdfscorebar-sr-x4`）

- 論理モデルID: `pdfscorebar-sr-x4`
- 選択バージョン・識別情報: `models/sr_x4/manifest.json`（`version`、`sha256`、`size_bytes`、RRDBNet の `num_feat`／`num_block`／`num_grow_ch`）
- 来歴: PDFScoreBar がランダム初期化から学習（#533）。`tools/issue533/train_sr.py` と、`tools/issue533/synth_score.py` が生成する手続き的な合成楽譜だけを使う。事前学習重み、教師モデル、楽譜PDF、評価画像、GT は使わない。manifest に学習コマンド、seed、スクリプトのハッシュ、実行環境を記録する
- ネットワーク: vendoring した Apache-2.0 の RRDBNet（`src/third_party/realesrgan_sr`）
- 所有: リポジトリで追跡（MMR checkpoint と同様）。配布物に含まれる
- コンテナruntime: バインドマウントされた `/workspace/models/sr_x4/...`
- 解決: `src.common.model_artifacts.resolve_first_party_sr`。読み込みのたびに SHA-256 を照合する。runtime preflight と Docker ビルドでも照合する
- 明示的上書き: なし
- 更新手順: 追跡しているスクリプトで新しい版を学習し、新しい manifest の `version`／`sha256` で追加し、現行モデルに対する #533 の Full68 ゲートに合格してから切り替える。manifest と一致しないバイト列は fail closed

x2 SR はサポートしない。本番の dense ルートは `sr_scale=4` を必須とする。

Real-ESRGAN の release 重み（`RealESRGAN_x4plus` SHA-256 `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`、`RealESRGAN_x2plus` `49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb`）は #533 まで使っていた。現在は取得・選択しない。現行 manifest が使用する重みを指定する。

### 保守対象HOMR runtime資産

- 論理モデルID: 保守対象HOMRのsegmentation（およびHOMRのOCR資産）。#533 以降、transformer encoder/decoder は runtime に含まない。PDFScoreBar は SegNet の小節線とマスクだけを使い、`HomrPredictor` は HOMR の譜表転写をスキップする。イメージに transformer checkpoint（Run 426）は入らない
- 選択runtimeバージョン: HOMRソースcommit `457e7c6518a10ba755db2e60883419e56c4d7369`
- そのcommitで選択されるGPUモデルの識別情報:
  - segmentation: `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f_fp16`
- 来歴: 上流HOMRの `onnx_checkpoints` GitHub release。固定されたHOMRソースが選択し、`docker/init_homr_segnet.py` で配置する（SegNet と OCR の初期化だけ。`homr.main --init` は transformer も取得するため使わない）
- 完全性の識別情報:
  - segmentationパッケージ（上流release）: `8d05a37fe76829673bc9def0a7caf168e5860aa4d1a8f7ac1b6123aa69fe3d82`
  - 展開後のsegmentation ONNX（Dockerビルドで照合）: `60f495496cb41473c0521d0811d8f44b9d5cff892d287974a8aebb3eaee2fa83`
  - 履歴（同梱しない）: transformer encoderパッケージ `1390295d921a5e646a6405d23ca6a922a7dcefa97cb425317be84de5195fd49c`、decoderパッケージ `0d21e347661c147b073a35c880cfc52c1ae71d40a990e5964e3736a595657ce8`
- 所有: Dockerイメージ／固定された上流HOMR runtime
- ホスト上の配置: Dockerビルドキャッシュのみ
- コンテナruntime: `/opt/venv_pipeline` 内のHOMRパッケージディレクトリ。正規検証では `/workspace` に依存してはならない
- 解決・配置: Dockerビルド時の `docker/init_homr_segnet.py`。SegNet のハッシュ不一致、または transformer の ONNX checkpoint があればビルドを失敗させる
- 明示的上書き: 正規runtimeにはなし
- 更新手順: HOMRソースの固定値を意図的に更新し、そのcommitで選択される資産名とreleaseダイジェストを一覧化し、再ビルド、ONNX CUDA providerの確認、正規smokeを実行する。新しい上流releaseによって固定runtimeの識別情報が暗黙に変わってはならない。

上記releaseパッケージのハッシュは上流が配布するアーカイブの値である。選択した固定HOMR runtimeの来歴であり、runtimeの所有境界はDockerイメージにある。

### 固定されたStage-E HOMR資産

- 論理モデルID: `stage-e-homr-segnet`、`stage-e-homr-transformer-encoder`、`stage-e-homr-transformer-decoder`
- 選択バージョン・来歴: HOMR commit `864e2882f7a41afcf8f16654728a473ae56826d6` とPDFScoreBar evaluator commit `bd6ae56f8be6c87088143cfbf0ba09dee94fe0d7`
- 期待されるruntimeファイルのSHA-256:
  - segmentation ONNX: `e6a7c1e84f8d2f19f20a47e0889be2392cd487d27fa77984e4877b86534dee83`
  - transformer decoder ONNX: `381646983d14f17a11e4be671aaf6e4f81727b3a9edf0cf4890109a321ffce68`
  - transformer encoder ONNX: `22a443b2ea18da82128ae52e85436d6fb4728ab68aee24adb2ac9dfc2003a30c`
- 所有: 再現専用Dockerイメージ。意図的に過去の状態で固定
- ホスト上の配置: Dockerビルドキャッシュのみ
- コンテナruntime: `/opt/homr_stage_e_profile`、分離されたPython runtimeは `/opt/venv_stage_e_homr`
- 解決・配置: `docker/Dockerfile.stage-e` の固定ソースcommitにおける `download_weights()` の後、明示的にSHA-256を検証
- 明示的上書き: 正規Stage-E profileにはなし
- 更新手順: このprofileは過去の来歴である。置換は独自のソース・evaluator来歴とダイジェストを持つ新しいprofile／モデルバージョンとし、記録済みStage-Eの識別情報をその場で変更しない。

## モデルの更新

manifestが管理する資産では、次の手順に従う。

1. 置換モデルを意図して選択し、上流または学習の来歴を記録する。
2. 新しい論理バージョンを割り当てる（異なるバイト列に古いバージョンを再利用しない）。
3. そのバージョンに期待されるダイジェストを計算・記録する。
4. キャッシュ／runtimeの識別情報にバージョンが含まれる場合は更新する。
5. 選択したバイト列を配置・importして検証する。
6. `docs/dev/VALIDATION_POLICY.md` で要求される種類の検証を実行する。

テストでは契約の両面を引き続き証明する必要がある。宣言されたバージョンとダイジェストの更新は受け入れられ、選択された識別情報を変更せずにバイト列を変えた場合は完全性検査が失敗する。
