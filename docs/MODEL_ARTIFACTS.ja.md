# Productionモデル資産

<!-- translation: {"original":"MODEL_ARTIFACTS.md","source":{"sha256":"3fc1eb9bbb00fc656dd53796a176ee4411521a3d29c6b94e9eb4e3f429750b13"},"state":"reviewed"} -->

[English / 原文](MODEL_ARTIFACTS.md)

productionで使用する学習済みcheckpointの永続的な正本に `logs/` を使ってはならない。`logs/` は実験・生成出力の置き場のままとする。productionモデルの識別情報は、追跡対象の小さなmanifestとバージョン付きGitHub Release資産で定義する。

## 契約

各productionモデルmanifestはスキーマ `pdfscorebar.model_artifact.v1` を使用し、次を記録する。

- 論理的な `model_id` と `version`
- 期待されるモデル `architecture`
- GitHub Releaseのリポジトリ、タグ、資産名
- 採用された正確なバイト列のSHA-256ダイジェストとバイトサイズ
- ローカルモデルキャッシュ以下の相対 `cache_path`
- 採用された学習・評価の決定とproductionのスコアリング契約を特定するための来歴

release資産は永続的なバイナリのソースである。manifestはリポジトリで追跡する識別・完全性の契約である。プロジェクト方針上、release資産は不変として扱う。既存のproduction資産を編集、削除して再アップロード、またはその場で置換してはならない。新しいバージョン／タグを公開し、レビューされた変更でmanifestを更新する。ホスティングサービスが技術的には置換を許す場合でも、SHA-256検証を正とする。

## 現行production小節線CNN

現行のdense production経路は、次に記録されたIssue #296 D27 checkpointを使用する。

```text
models/barline_cnn/manifest.json
```

このバージョンの不変な識別情報・来歴:

- モデル: `barline-cnn@issue296-d27-v1`
- アーキテクチャ: `efficientnet_b0`
- 採用実験: D27 current-producer candidate-aligned EfficientNet-B0
- 採用Issue／PR: `#296` / `#310`
- 採用されたmerge commit: `49a9da6a5f352e48cffd79306d75acdc8da3d9e7`
- 採用された正確なバイト列の過去のソースパス: `logs/cnn_barline_classification/issue296_efficientnet_b0_current_candidate_aligned_v1/cnn_classifier_epoch_9.pth`
- releaseタグ: `model-barline-cnn-issue296-d27-v1`
- release資産: `cnn_classifier_epoch_9.pth`
- SHA-256: `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`
- サイズ: `16339553` bytes
- キャッシュ相対パス: 解決されたホストキャッシュルート（後述）以下の `barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth`
- production閾値: `0.4965248107910156`
- `cnn_apply_nms: false`
- #296の学習・評価matcherの来歴: `center_anchor`、`vov_threshold=0.5`、`xdist_threshold=12.0`

Issue #315の公開検証では、ローカルの採用checkpoint、新たにダウンロードしたRelease資産、空のキャッシュに配置された資産のSHA-256とサイズが同じであることを証明した。続いて過去のverified Stage-E resolverで配置済みcheckpointを正常に読み込んだ。これは資産の移動のみであり、採用された #296 checkpointのバイト列、アーキテクチャ、閾値、crop／スコアリング経路、モデル品質の判断を変更しない。

## ローカルキャッシュ

キャッシュルートは次の順に解決する。

1. 明示的な `cache_root`（CLIでは `--cache-root`）。
2. `PDFSCOREBAR_MODEL_CACHE`。
3. `$XDG_CACHE_HOME/pdfscorebar/models`。
4. XDGが未設定の場合は `~/.cache/pdfscorebar/models`。

通常の既定値はworktree間で共有される。production CNNのフォールバックパスは `~/.cache/pdfscorebar/models/barline_cnn/issue296-d27-v1/cnn_classifier_epoch_9.pth`。実際に選択される場所は以下の `path` コマンドで確認する。既存のチェックアウト内 `.model_cache/` ディレクトリは自動的に検索・移行されない。移行時に必要なら `PDFSCOREBAR_MODEL_CACHE="$PWD/.model_cache"` で明示的に選択する。

releaseを元にするキャッシュ資産はrelease資産と追跡対象manifestから復元できる。共有キャッシュには運用者提供の資産も含まれ得るため、キャッシュルート全体を破棄可能として扱ってはならない。[正規資産契約](MODEL_ARTIFACT_CONTRACT.ja.md)を参照。

## 配置と検証

配置は明示的に行う。production実行時に不足モデルを暗黙にダウンロードしたり、別のcheckpointにフォールバックしたりしてはならない。

現行production小節線CNNの場合:

```bash
python -m src.common.model_artifacts materialize models/barline_cnn/manifest.json
```

キャッシュ済みモデルはダウンロードせずに検証できる。

```bash
python -m src.common.model_artifacts verify models/barline_cnn/manifest.json
```

期待されるキャッシュパスの表示:

```bash
python -m src.common.model_artifacts path models/barline_cnn/manifest.json
```

配置処理は一時ファイルにダウンロードし、SHA-256を検証してからキャッシュにアトミックに公開する。キャッシュ資産の欠落・破損、不正なmanifest、ダイジェストの異なるreleaseダウンロードは明示的に失敗する。`--force` は、同じmanifest／release契約から既知の不正なキャッシュコピーを意図的に修復する場合だけ使う。

非公開GitHub資産にはmaterializerに `GITHUB_TOKEN` を渡せる。トークンをmanifestや設定に保存してはならない。

## 置換モデルの公開

1. 資産を公開する前にモデル選択と評価を完了する。
2. 採用された正確なcheckpointのバイト列のSHA-256とバイトサイズを計算する。
3. その正確なバイト列を新しいGitHub Releaseタグで公開する。既存のproduction資産は上書きしない。
4. 資産を新たにダウンロードし、採用ソースのバイト列とのSHA-256／サイズの一致を証明する。
5. releaseの位置、ダイジェスト、サイズ、スコアリング契約、採用Issue／PRの来歴を追跡対象manifestに追加・更新する。
6. 空のキャッシュから配置し、ダイジェストが元のcheckpointと一致することを検証する。
7. 影響を受けるproduction経路を通じて配置済みcheckpointを読み込む。
8. 変更に見合った検証を実行する。バイト列とスコアリング契約が変わらない場合、資産の移動だけを理由にモデル品質の再調整や新たな全件評価を行うべきではない。

release資産のアップロード、再ダウンロード、追跡対象ダイジェストとの照合が済むまで、唯一のローカルコピーを削除してはならない。

## クリーンアップ

`logs/` 以下の実験checkpointは、採用されたproductionのバイト列が公開され、独立に配置・検証された後にのみ削除できる。releaseを元にするキャッシュファイルを削除する前に、`python -m src.common.model_artifacts path <manifest>` で正確な場所を解決し（検証時と同じキャッシュ上書き指定を使う）、別のworktreeが必要としていないか確認する。共有キャッシュルート全体ではなく対象資産のみを削除する。運用者提供の資産には再import用の別途保持されたソースが必要である。チェックアウト内の `.model_cache/` は明示的に指定する旧来の上書き先であり、既定のクリーンアップ場所ではない。
