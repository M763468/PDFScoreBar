# 正規モデル資産の契約

<!-- translation: {"original":"MODEL_ARTIFACT_CONTRACT.md","source":{"sha256":"fb015517ffb9fcf4e20d14412e84fbe6a783b5163c1eda0c224a7a3eb4561c9a"},"state":"reviewed"} -->

[English / 原文](MODEL_ARTIFACT_CONTRACT.md)

本文書は、保守対象のDockerおよびproduction runtimeが使用するモデル・重みの識別情報を記録する。[環境文書](ENVIRONMENTS.md)を補完するものであり、モデルの選定や検証を行ったIssueから責任を移すものではない。処理の概要は[アーキテクチャ概要](PIPELINE_ARCHITECTURE.ja.md)、詳細は[実装リファレンス](PIPELINE_ARCHITECTURE_REFERENCE.ja.md)を参照。

共通ルールは次のとおり。

```text
論理モデルID -> 選択されたバージョン -> 来歴 -> 期待される完全性の識別情報
```

ダイジェストはモデル系列に永続的に属するのではなく、選択されたバージョンに属する。同じバージョンと来歴のままバイト列を置き換えることは完全性違反である。意図したモデル更新では新しいバージョン・来歴・ダイジェストを登録し、キャッシュ内で過去のバージョンと共存できる。

## パスと所有権の規約

- リポジトリ管理のダウンロード可能な資産には `src.common.model_artifacts` を使う。既定は `$XDG_CACHE_HOME/pdfscorebar/models/<model-id>/<version>/<asset>`、`XDG_CACHE_HOME` 未設定時は `~/.cache/pdfscorebar/models/<model-id>/<version>/<asset>`。`PDFSCOREBAR_MODEL_CACHE` でキャッシュルートを明示的に上書きできる。
- イメージが所有する資産は `/workspace` の外、通常は `/opt/pdfscore-assets` 以下に置く。これにより、作業中のチェックアウトのbind mountで隠れない。
- 外部・運用者提供の資産は可能な限り同じホスト側のバージョン名前空間に登録し、`/opt/pdfscore-external/<model-id>/<version>/...` 以下に読み取り専用でマウントする。
- パスを明示する環境変数は互換性維持・上書き用である。manifestが選択バージョンの完全性を管理する場合、その識別情報を迂回してはならない。

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

### OMR-DLN小節検出器

- 論理モデルID: `omr-dln-measures`
- 選択バージョン: `phase1-validated-v1`
- 来歴: `models/omr_dln/manifest.json`。公式 `dmgonzalez8/OMR` モデル配布物と、PR #330のPhase 1最終検証で使用した正確なバイト列
- 期待SHA-256: `00d0bd8b399ae872f029eb38ed3985fcef33ca81cae414992b5cdb9062e91212`
- 所有: 外部・運用者提供
- ホスト上の配置: `$XDG_CACHE_HOME/pdfscorebar/models/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt`（または `~/.cache/pdfscorebar/models` へのフォールバック／`PDFSCOREBAR_MODEL_CACHE` による上書き）
- コンテナruntime: `/opt/pdfscore-external/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt`
- 解決・配置: `src.common.model_artifacts verify/import`。正規Docker検証は選択済みキャッシュ資産を解決して読み取り専用でマウントする
- 明示的上書き: 互換性のため `OMR_DLN_MODEL_PATH` を維持する。参照先は使用前に選択manifestのダイジェストと照合する
- 更新手順: 意図して選んだ公式の置換モデルを入手し、manifestに新しいバージョン・来歴・ダイジェスト・キャッシュパスを登録し、`python3 -m src.common.model_artifacts import ...` でimportして検証する。Phase 1のダイジェストは過去の来歴であり、系列に永続するハッシュではない。

上流はモデルをソースリポジトリと別に配布する。Issue #329 Phase 2では上流リポジトリに明示的なモデル再配布ライセンスが見つからなかったため、PDFScoreBarはモデルを暗黙に再配布したり自動的に代替したりしない。運用者によるimportでは、選択済みの既知のバイト列を検証してから共通キャッシュに公開する。

### Real-ESRGAN x4

- 論理モデルID: `realesrgan-x4plus`
- 選択バージョン: 上流release `v0.1.0`、資産 `RealESRGAN_x4plus.pth`
- 来歴: 公式 `xinntao/Real-ESRGAN` GitHub release。runtimeパッケージのソースはDockerfileで別途固定
- 完全性の識別情報: 選択release／資産とSHA-256 `4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1`
- 所有: Dockerイメージ
- ホスト上の配置: Dockerビルドキャッシュのみ。チェックアウト内の正規コピーは不要
- コンテナruntime: `/opt/pdfscore-assets/realesrgan/RealESRGAN_x4plus.pth`
- 解決: `src.common.realesrgan_assets`
- 明示的上書き: `PDFSCORE_REALESRGAN_WEIGHTS_DIR`（ホスト開発用に旧チェックアウトへのフォールバックも維持）
- 更新手順: 上流release／資産を意図的に変更し、新しいダイジェストを記録・検証し、イメージを再ビルドしてDocker/GPU契約ゲートを実行する。

### Real-ESRGAN x2

- 論理モデルID: `realesrgan-x2plus`
- 選択バージョン: 上流release `v0.2.1`、資産 `RealESRGAN_x2plus.pth`
- 来歴: 公式 `xinntao/Real-ESRGAN` GitHub release。runtimeパッケージのソースはDockerfileで別途固定
- 完全性の識別情報: 選択release／資産とSHA-256 `49fafd45f8fd7aa8d31ab2a22d14d91b536c34494a5cfe31eb5d89c2fa266abb`
- 所有: Dockerイメージ
- ホスト上の配置: Dockerビルドキャッシュのみ。チェックアウト内の正規コピーは不要
- コンテナruntime: `/opt/pdfscore-assets/realesrgan/RealESRGAN_x2plus.pth`
- 解決: `src.common.realesrgan_assets`
- 明示的上書き: `PDFSCORE_REALESRGAN_WEIGHTS_DIR`（ホスト開発用に旧チェックアウトへのフォールバックも維持）
- 更新手順: x4と同じバージョン・来歴・ダイジェストのルールに従い、意図的な更新後にイメージを再ビルドしてDocker/GPU検証を再実行する。

上記Real-ESRGANのハッシュは現在選択された上流releaseのバイト列を識別する。ダウンロードしたバイト列が一致しなくなった場合、Dockerは黙って置換を受け入れずビルドを失敗させなければならない。

### 保守対象HOMR runtime資産

- 論理モデルID: 保守対象HOMRのsegmentation、transformer encoder/decoder（およびHOMRのinitが管理するOCR資産）
- 選択runtimeバージョン: HOMRソースcommit `457e7c6518a10ba755db2e60883419e56c4d7369`
- そのcommitで選択されるGPUモデルの識別情報:
  - segmentation: `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f_fp16`
  - transformer encoder: `encoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644_fp16`
  - transformer decoder: `decoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644_fp16`
- 来歴: 上流HOMRの `onnx_checkpoints` GitHub release。固定されたHOMRソースが選択し、`python -m homr.main --init --gpu force` で配置する
- 上流releaseパッケージのSHA-256:
  - segmentationパッケージ: `8d05a37fe76829673bc9def0a7caf168e5860aa4d1a8f7ac1b6123aa69fe3d82`
  - transformer encoderパッケージ: `1390295d921a5e646a6405d23ca6a922a7dcefa97cb425317be84de5195fd49c`
  - transformer decoderパッケージ: `0d21e347661c147b073a35c880cfc52c1ae71d40a990e5964e3736a595657ce8`
- 所有: Dockerイメージ／固定された上流HOMR runtime
- ホスト上の配置: Dockerビルドキャッシュのみ
- コンテナruntime: `/opt/venv_pipeline` 内のHOMRパッケージディレクトリ。正規検証では `/workspace` に依存してはならない
- 解決・配置: Dockerビルド時の固定HOMRの `--init --gpu force` 経路
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

## OMR-DLN登録手順

公式 `YOLOv8m_Measures.pt` を上流の配布経路から入手し、選択されたmanifestバージョンに対して一度実行する。

```bash
python3 -m src.common.model_artifacts import \
  models/omr_dln/manifest.json /path/to/YOLOv8m_Measures.pt
```

importは選択バージョンのダイジェストに一致しないバイト列を拒否し、検証済みバイト列をアトミックに公開する。その後 `make verify-gpu-smoke` はキャッシュ項目を自ら解決する。通常のホスト既定値はXDG／ユーザーキャッシュを通じてworktree間で共有される。別のキャッシュルートを明示的に指定する必要がある場合だけ `PDFSCOREBAR_MODEL_CACHE` を使う。

## モデルの更新

manifestが管理する資産では、次の手順に従う。

1. 置換モデルを意図して選択し、上流または学習の来歴を記録する。
2. 新しい論理バージョンを割り当てる（異なるバイト列に古いバージョンを再利用しない）。
3. そのバージョンに期待されるダイジェストを計算・記録する。
4. キャッシュ／runtimeの識別情報にバージョンが含まれる場合は更新する。
5. 選択したバイト列を配置・importして検証する。
6. `docs/dev/VALIDATION_POLICY.md` で要求される種類の検証を実行する。

テストでは契約の両面を引き続き証明する必要がある。宣言されたバージョンとダイジェストの更新は受け入れられ、選択された識別情報を変更せずにバイト列を変えた場合は完全性検査が失敗する。
