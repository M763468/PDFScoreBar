# 環境およびツールガイド

<!-- translation: {"original":"ENVIRONMENTS.md","source":{"sha256":"500d6a51a75cc5fc631071830026dd20bc9826bd73f87da64f4afedda67e583b"},"state":"reviewed"} -->

[English / 原文](ENVIRONMENTS.md)（英語正本）

翻訳元: same PR / SHA-256 `500d6a51a75cc5fc631071830026dd20bc9826bd73f87da64f4afedda67e583b`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

本ドキュメントには、保守対象となっている開発環境および評価環境を記録しています。過去の単発コンテナやブランチ固有の worktree は、進行中の Issue で明示的に復活させない限り、現在の運用手順ではありません。

## 標準のフルパイプラインランタイム

### `pdfscore_pipeline_gpu`

これは、保守対象となっている本番専用のフルパイプライン Docker イメージです。このイメージの `/opt` ペイロードには過去の Stage-E ランタイムは含まれていません。保持されている互換性ツールでは、別イメージである `pdfscore_stage_e_reproduction` を使用します。

- Dockerfile: `Dockerfile`
- ビルドターゲット: `make docker-build`
- 標準の GPU 検証エントリポイント: `make verify-gpu-smoke`
- 本番環境を代表する検出器精度スモークテスト: `make run-smoke`
- パイプラインエントリポイント: `make run-pipeline CONFIG=<config.yaml>`
- コンテナ内インタプリタ: `/opt/venv_pipeline/bin/python`
- 通常のマウント先リポジトリルート: `/workspace`

このイメージには、プロジェクトおよびランタイムの依存関係と、`docker/patch_homr_onnx_provider.py` による保守対象の HOMR ONNX プロバイダパッチがインストールされます。検証済みの dense 本番ルート、および Docker/GPU 実行を必要とするフルパイプライン検証には、このイメージを使用してください。過去の Stage-E の再現には別のイメージを使用します（後述）。

`make verify-gpu-smoke` は正式な環境ゲートです。パイプライン実行前に `scripts/docker_runtime_validation.sh` を実行し、バインドマウントされたソースをイメージビルド時に記録されたソースフィンガープリントと照合し、必須アセットを検証し、コンテナ内で CUDA のプローブを行います。その後、標準の `configs/smoke_test.yaml` により、新規に 360 DPI で PDF レンダリングした `Va_Prokofiev_Symphony1/page_001` に対して現在の dense 本番検出器コントラクトを実行し、明示的な GT 精度ゲートを適用します。レンダリングされた入力が承認済みの評価画像アイデンティティと一致しなくなった場合、検出器設定が `configs/dense_full_pipeline.yaml` から乖離している場合、またはページで hard FP/FN や soft residual が発生した場合、スモークテストは失敗します。ホスト側の `nvidia-smi` 出力はメタデータにすぎず、コンテナ内の CUDA プローブが正式な判定基準となります。

`make run-smoke` は、外側の `gpu_smoke.sh` メタデータ／タイムアウトラッパーを介さずに、同じ標準ランタイム検証および精度ゲートを使用します。スモーク実行には一意の実行 ID が付与されるため、チェックを再実行する際に root 所有の Docker アーティファクトを事前に削除する必要はありません。

現在の 2 系統 HOMR（two-HOMR）のプロセス境界については、`PIPELINE_ARCHITECTURE.md` を参照してください。コンテナ名や古いフェーズ図はアーキテクチャ上のコントラクトではありません。

## Docker のソース、マウント、およびアセット所有権のコントラクト

標準ランタイムは、アクティブなチェックアウトを意図的に `/workspace` にバインドマウントします。つまり、`docker build` 中に `/workspace` にコピーされたソースファイルは実行時には隠蔽されます。したがって、このマウント後も維持されなければならないファイルは、イメージ内の `/workspace` 配下の内容に依存してはなりません。

所有権のルールは以下のとおりです。

| ランタイム依存関係 | 所有者 | 標準の場所／メカニズム |
|---|---|---|
| メインの Python／ランタイム依存関係 | Docker イメージ | `/opt/venv_pipeline` |
| 保守対象の現行 HOMR パッケージ／ランタイム | Docker イメージ | Dockerfile のピン留めに基づき `/opt/venv_pipeline` にインストール |
| 検証済みの過去 Stage-E HOMR スタック | 再現用イメージのみ | `/opt/venv_stage_e_homr`, `/opt/homr_stage_e_profile`, `/opt/pdfscore_stage_e_profile` |
| Real-ESRGAN x2/x4 重み | Docker イメージ | `/opt/pdfscore-assets/realesrgan` |
| 標準スモーク CNN バイトデータ | Docker イメージ（追跡対象の #315 マニフェストから派生） | `/opt/pdfscore-assets/barline_cnn_smoke.pth` |
| OMR-DLN `YOLOv8m_Measures.pt` | オペレータ／外部アセット | ホスト共通モデルキャッシュ内の選択されたマニフェストバージョン（`/opt/pdfscore-external/omr-dln-measures/<version>/` 配下に読み取り専用でマウント） |
| リポジトリのソース／設定／入力データ | アクティブなチェックアウト | `/workspace` にバインドマウント |
| 生成された実行アーティファクト | アクティブなチェックアウト／オペレータ | Git 管理外の `logs/`、`artifacts/`、および設定された出力パス |

モデル横断でのバージョン、プロビナンス（来歴）、整合性、および更新ルールは `docs/MODEL_ARTIFACT_CONTRACT.md` に整理されています。ホスト側のモデルアーティファクトは、デフォルトでユーザー単位の共有キャッシュである `$XDG_CACHE_HOME/pdfscorebar/models`（`XDG_CACHE_HOME` が未設定の場合は `~/.cache/pdfscorebar/models`）に配置されます。`PDFSCOREBAR_MODEL_CACHE` は引き続き明示的なオーバーライドとして使用できます。検証済みの登録を複数の worktree 間で再利用できるよう、デフォルトの場所は意図的にアクティブなチェックアウトから独立しています。移行期間中は、既存のチェックアウトローカルなキャッシュを `PDFSCOREBAR_MODEL_CACHE="$PWD/.model_cache"` で明示的に選択することも可能ですが、暗黙的なフォールバックとしては扱われなくなりました。

Real-ESRGAN リゾルバはイメージ内の `PDFSCORE_REALESRGAN_WEIGHTS_DIR` を使用し、従来のチェックアウトパスはホスト開発時のフォールバックとしてのみ保持します。標準の Docker スモークテストでは、`external/realesrgan/weights` への重みの手動コピーを必要としてはなりません。

イメージが所有するスモーク CNN パスはレガシー／ワークフロー専用のフィクスチャ向けに引き続き利用可能ですが、標準の精度スモークテストではなく、本番精度のエビデンスとして使用してはなりません。標準のスモークテストでは、`configs/dense_full_pipeline.yaml` と同じ `models/barline_cnn/manifest.json`、しきい値、dense 検出器ルート、および x4 サポートコントラクトを使用します。Docker は引き続き `src.common.model_artifacts` を通じて追跡対象マニフェストを実体化（SHA-256 チェックを含む）し、検証済みのバイトデータを上記の安定したスモーク専用互換パスで公開します。

OMR-DLN の重みは扱いが異なります。これは外部で配布されているものであり、Docker ビルドによって暗黙的にダウンロード、再配布、または代替されることはありません。選択された公式の `YOLOv8m_Measures.pt` を、以下のコマンドで一度だけ共通キャッシュに登録してください。

```bash
python3 -m src.common.model_artifacts import \
  models/omr_dln/manifest.json /path/to/official/YOLOv8m_Measures.pt
```

インポート処理では、選択されたバージョンのダイジェストを検証した上で、ファイルをアトミックにキャッシュへ公開します。標準の `make verify-gpu-smoke` は、その選択されたキャッシュエントリを自身で解決し、マニフェストで宣言されたコンテナパスに読み取り専用でマウントします。`OMR_DLN_MODEL_PATH` は引き続き明示的な互換性オーバーライドとして機能し、使用前に同じ選択バージョンのダイジェストに対して検証されます。従来のリポジトリローカルな OMR-DLN パスも互換性のために引き続き受け入れられますが、標準のステージングワークフローではありません。

### ソースとイメージの互換性

最終イメージは、ランタイムに影響するソースのフィンガープリントを `/workspace` 外の以下の場所に保存します。

```text
/opt/pdfscore-runtime/source_fingerprint.txt
```

標準の Docker 検証では、以下の 2 つの異なるアイデンティティを意図的に分離して扱います。

- **ソースフィンガープリント（source fingerprint）** は、イメージのビルドに使用されたチェックアウトの広範なプロビナンスです。これにはバインドマウントされるアプリケーションの Python コードも含まれ、ソースの乖離（ドリフト）を特定するのに役立ちます。
- **ランタイム互換性フィンガープリント（runtime compatibility fingerprint）** は、イメージおよび環境を定義するコントラクトを対象とします。具体的には、ビルド全体にわたる Dockerfile の命令（コピー後のイメージ所有アセットの実体化を含む）、`pyproject.toml`、HOMR ONNX プロバイダのビルドパッチ、イメージ所有の barline-CNN マニフェスト、およびその CNN の実体化時に実行されるプロジェクトローカルなモデルアーティファクト実体化／インポートチェーンが含まれます。Dockerfile のコメントと、認識されたソースプロビナンス専用の ARG/LABEL/フィンガープリント出力コマンドのみが正規化によって除外され、未知のコマンド記述は無視されずにハッシュ対象として残ります。

GPU スモークのホストリゾルバは、まず可変の標準タグを不変のイメージ ID に解決します。その後、認識されたすべてのイメージは、受け入れられる前にランタイム互換性フィンガープリントと照合されます。ソースフィンガープリントの一致はプロビナンス診断にのみ影響し、互換性検証をバイパスすることは決してありません。ソースプロビナンスが異なる場合、リゾルバは認識された PDFScoreBar イメージ内に保持されているビルドソースのコピーから互換性フィンガープリントを導出し、それをアクティブなチェックアウトと比較します。したがって、バインドマウントされる `src/` 配下の Python コードのみの変更であれば既存の互換イメージを再利用できますが、依存関係、CUDA/HOMR ビルドコントラクト、パッチ、またはイメージ所有モデルのコントラクトに変更がある場合は、引き続き互換イメージの選択または再ビルドが必要になります。

互換性コントラクトが異なる場合、検証処理はアクティブなトピックブランチを利用可能な `origin/develop`（またはローカルの `develop`）参照と比較し、トピックのベースが古い状態（stale topic base）なのか、トピック固有の環境変更なのか、あるいは純粋にイメージが古いのかを区別します。参照が古くなっている可能性がある場合は、分類前に `origin` を fetch してください。トピックのベースが古い場合は現在の `develop` 上に更新（リフレッシュ）すべきであり、それ自体はイメージを再ビルドする理由にはなりません。そのケースを除き、リゾルバは再ビルドを推奨する前に、ランタイム互換性フィンガープリントが一致するローカルの PDFScoreBar イメージを検索します。

コンテナ内のプリフライトは、ホスト側でのイメージ解決後にアクティブなチェックアウトのコントラクトコードを実行し、バインドマウントされた互換性フィンガープリントを再チェックすることで、選択から実行までの間に発生したソース変更から保護します。ソースフィンガープリントの不一致は、それ自体がイメージの非互換性として扱われるのではなく、プロビナンス情報として報告されます。

標準ビルドでは、ソースフィンガープリント、コミット、およびブランチのラベルをイメージに記録し、ホスト側のビルドプロビナンスを `artifacts/docker_build_provenance.txt` に書き出します。これらのラベルを持たない #352 以前の既存ランタイムイメージも、埋め込まれたソースフィンガープリントを通じて引き続き検査可能です。それらのランタイム互換性は保持されているビルドソースのコピーから導出できるため、新しいメタデータを追加するためだけに再ビルドする必要はありません。
再利用可能なローカルのランタイムイメージとそのプロビナンスを一覧表示するには、以下を実行します。

```bash
python3 scripts/docker_image_resolver.py list
```

`DOCKER_IMAGE=<ref>` は引き続き明示的なオーバーライドとして使用できます。これが設定されている場合、検証処理はその特定のイメージを検証し、別のローカルイメージに暗黙的に置き換えることは決してありません。

## Docker のビルドおよびクリーンアップのライフサイクル

`make docker-build` は、他の worktree で使用されているコンテナやイメージを削除することなく、選択されたイメージをビルドします。コンテナのクリーンアップは、別の明示的なコマンドとして用意されています。

```text
make docker-clean
  -> docker rm -f pdfscore_pipeline_gpu
```

このコマンドはイメージを削除**しません**。イメージの削除は明示的に行います。

```text
make docker-clean-full
  -> docker-clean
  -> docker rmi pdfscore_pipeline_gpu
```

Issue #261 / PR #325 で導入されたコンテナとイメージのクリーンアップ分離は維持されており、Issue #352 では他の worktree の中断を防ぐためにビルド時の暗黙的なコンテナクリーンアップが廃止されました。`context canceled` のようなビルド失敗は、実際の Docker／ビルドシグナルとビルドコンテキストのエビデンスから診断しなければならず、近くでクリーンアップが行われたというだけの理由で `docker rmi` が原因であると決めつけてはなりません。ビルドコンテキストの削減は `.dockerignore` の保守に属するものであり、ランタイムアセットの所有権を変更するものではありません。

`make docker-build` はデフォルトで共有の `pdfscore_pipeline_gpu` タグを更新し、そのビルドに使用されたソースフィンガープリント／コミット／ブランチを記録します。トピックブランチでランタイムに影響するファイルを意図的に変更し、共有タグの向き先を変更すべきでない場合は、明示的な一時タグを指定してビルドしてください。

```bash
make docker-build DOCKER_IMAGE=pdfscore_issue352
```

検証リゾルバは、可変の標準タグがそのイメージを指していなくても、フィンガープリントによってそのイメージを再利用できます。`make docker-clean` がランタイムイメージを削除することは決してありません。イメージの完全な削除は引き続き明示的に行います。デフォルト以外のタグを意図的に削除する場合は、`DOCKER_IMAGE=<ref> make docker-clean-full` を使用してください。

## 実行プリフライト

環境に依存するチェックを実行する前に、アクティブな worktree のコミット／差分、選択されたインタプリタまたは不変のイメージ ID、実際のチェックアウトマウント、実行時の UID/GID、書き込み可能な出力パス、および Docker／`gh` の権限が利用可能であることを確認してください。ホストの Python、共有 pytest コンテナ、本番 GPU イメージ、または Node/Playwright ブラウザランナーの選択には、[Local validation](dev/LOCAL_VALIDATION.md) を使用してください。コンテナ名や以前に確認したイメージタグは、現在のマウント状態や互換性を証明するものではありません。

標準の共有 pytest コンテナは、マネージャーチェックアウトを `/workspace` にマウントするため、`.worktrees/` 配下の Issue 用 worktree は `/workspace/.worktrees/` 配下に現れます。専用のコンテナプリフライトスクリプトは `/workspace` への直接のチェックアウトを要求するため、このネストされたレイアウトを意図的に拒否します。代わりに Local validation に記載されているネストされたパス用のチェックを使用してください。`/workspace` に直接マウントされた専用の固定（frozen）候補コンテナは例外のままとなります。

## ホスト／uv 環境

### デフォルトのホストチェック

軽量な検証にはリポジトリの Makefile を使用します。

```bash
make test-fast
make lint
```

より強力な検証については、`docs/dev/VALIDATION_POLICY.md` に従って選択してください。

### CNN 分類器環境

CNN 分類器の学習および評価ワークフローが必要な場合は、引き続きホスト／uv ベースで行います。

```bash
uv venv .venv_cnn_classifier
uv pip sync experiments/cnn_classifier/requirements_cnn_classifier_venv.txt
```

データセットおよび生成されたモデルのパスは、明示的な保持ポリシーで別途定められていない限り、オペレータローカルです。本番設定内に `logs/` のモデルパスが記載されていても、新規チェックアウト内にその重みが存在することの証明として解釈しないでください。

## HOMR プロファイル

dense 本番ルートでは、不変の保守対象オリジナル画像 HOMR プロファイルを使用します。そのコミットとランタイムパスは以下に保存されています。

```text
configs/detector_profiles/maintained_original_homr.json
```

過去の Stage-E プロファイルは、保持されている過去のツール向けの分離された互換性コンポーネントとして引き続き利用可能です。これは本番環境の依存関係ではありません。ルートの `Dockerfile` には、過去の venv、クローンされたソース、モデルのダウンロード、またはマーカーは一切含まれていません。標準のプリフライトは、保守対象プロファイルのパスと、そのマニフェストに記載された正確な HOMR／評価器マーカー値を検証します。

本番イメージから再現用拡張イメージを明示的にビルドするには、以下を実行します。

```bash
make docker-build
make -f tools/issue120/Makefile.stage_e.mk docker-build-stage-e
make -f tools/issue120/Makefile.stage_e.mk run-issue120-stage-e-full
```

この拡張は `docker/Dockerfile.stage-e` であり、デフォルトの出力イメージ名は `pdfscore_stage_e_reproduction` です。分離されたビルドを行う場合は、これらの Make コマンドで `ISSUE120_PRODUCTION_IMAGE=<production-image>` および `ISSUE120_STAGE_E_IMAGE=<reproduction-image>` を設定してください。再現プロビナンスを保持する場合は、ベースイメージを不変のイメージ ID にピン留めしてください。このイメージには個別のアセットコントラクトラベルが付与されるため、本番プリフライトへの明示的なオーバーライドを含め、標準のイメージ解決からは除外されます。この拡張は過去のソースコミット、モデルの SHA-256 チェック、および分離された依存関係バージョンを保持しますが、本番環境向けに過去のプロファイルを選択するものではありません。

旧来の Stage-E という名称は、#120 のツール、マニフェスト、および承認済みの過去の結果に対する互換性識別子として保持されています。残されている目的は、保持されているツールやコンポーネント比較実験に対して、ピン留めされたコンポーネントを公開することです。この拡張は現在の本番メイン venv を継承するため、過去の完全な 2 系統 HOMR（two-HOMR）環境を再構築するものではなく、その full68 メトリクスを保証するものでもありません。過去の環境の完全な再現は #398 の受け入れ基準の対象外です。標準の `maintained_original` ルートはこれを必要としません。この互換性コントラクトの削除やインターフェースの名称変更は別途の廃止決定事項となり、ここで過去のデータ、ソースのピン留め、またはプロファイルが削除されることはありません。後述のマイルストーンに記録されているとおり、正確な入力画像は引き続き外部の前提条件となります。

コンポーネントプロファイルの正確なプロビナンス、パッケージバージョン、モデルハッシュ、および `/opt/` のランタイムパスは以下に保存されています。

```text
configs/detector_profiles/stage_e_verified_homr.json
```

保守対象のオリジナルプロファイルと `current_x4_support` で使用される現行ランタイムの HOMR は、メインのイメージおよびランタイムを共有しますが、個別の入力コントラクトおよび座標コントラクトを保持しています。標準の dense ルートでは過去のプロファイルは選択されません。再現要件については `TWO_HOMR_MILESTONE.md` を参照してください。

## 過去の評価環境

### `homr_eval_gpu`

`Dockerfile.homr` は、分離された HOMR 評価または過去の HOMR 評価のために保持されています。これはデフォルトのフルパイプライン環境ではありません。Issue で分離された HOMR の挙動や過去の再現が明示的に要求されている場合にのみ使用してください。

以前の SR 専用互換セレクタであった `sr_eval_gpu` / `/opt/venv_sr` と、機能していなかった dense 設定キー `container_name: sr_eval_gpu_exp` は、Issue #379 で削除されました。保守対象の重いパイプラインサブプロセスは、統合された `pdfscore_pipeline_gpu` 環境のみを選択するようになり、保守対象の重いステップの環境が選択されていない場合の明示的なインタプリタオーバーライドとして `PIPELINE_PYTHON` が保持されています。以前の SR 環境を依然としてハードコードしている過去のツールはセットアップガイダンスではなく、廃止に向けて別途追跡されています。

## データおよび生成出力のポリシー

- リポジトリで保持される評価フィクスチャは、`data/README.md` および関連する Issue の保持記録に文書化されています。
- 生成された実行結果、メトリクス、モデル出力、および大規模な中間アーティファクトは、明示的な保持ポリシーで別途定められていない限り、Git 管理外の `logs/` パス配下に配置します。
- ローカルのスクラッチ／ワークベンチ用データは Git 管理外の `tmp/` 配下に配置してください。追跡対象の `data/workbench/` ツリーを再作成してはなりません。
- CNN データセットの作業では、一括処理を行う前にアクティブなデータセットをリポジトリの `datasets/` 配下にステージングしてください。`/mnt/*` はメタデータ処理の重いスクラッチ領域としてではなく、ソース／アーカイブとして使用してください。

承認済みの 2 系統 HOMR（two-HOMR）マイルストーンは、現在の互換性拡張だけでは**新規クローンからそのまま再現することはできません**。正確な評価画像は引き続き外部にあり、またこの拡張は過去の完全なメイン依存関係スタックを再構築しないためです。マイルストーンのドキュメントでは、それらの要件を、保持されている Stage-E コンポーネントのピン留めから分離して記載しています。Docker スモークテストでは、以前の Git 管理外／ローカル専用の CNN 依存関係が解消されています。OMR-DLN は引き続き明示的な外部アセットですが、選択されたバージョンを共通モデルキャッシュに一度登録すれば、標準スモークテストが場当たり的なチェックアウトローカルのモデルパスに依存することはなくなります。

## pytest 実行可能な永続パイプラインコンテナ

リポジトリの pytest も必要とする反復的なパイプライン評価には、`pdfscore_pipeline_gpu` をベースとした名前付きの永続コンテナを使用してください。本番ランタイムには意図的に pytest を含めていませんが、それを理由にリポジトリの pytest カバレッジを弱めたり書き換えたりしないでください。

この共有コンテナの作成や検査は、マネージャーチェックアウトから行ってください。このコンテナの `/workspace` マウントは `.worktrees/` 配下に Issue 用 worktree を公開するため、[Local validation](dev/LOCAL_VALIDATION.md#python-and-pytest) に従って、ネストされた worktree パスとそれに対応する `PYTHONPATH` を指定して pytest を実行してください。以下のコマンドはマネージャーチェックアウト自体に対して実行するものです。分離された候補環境から直接マウントされた専用コンテナは明示的な例外です。ブラウザチェックには、[Local validation](dev/LOCAL_VALIDATION.md#browser-validation) に記載されている別のランナーを使用します。

コンテナが存在しない場合は作成します。このコンテナでパイプラインチェックを実行できるよう、本番タグを検証済みの不変イメージに解決し、登録済みの外部 OMR-DLN 重みをマウントします。

```bash
image_id=$(python3 scripts/docker_image_resolver.py resolve \
  --repo-root . --image-ref pdfscore_pipeline_gpu --explicit)
omr_host=$(python3 -m src.common.model_artifacts verify models/omr_dln/manifest.json)
omr_runtime=$(python3 -c \
  'import json; print(json.load(open("models/omr_dln/manifest.json"))["runtime_path"])')
docker run -dit --gpus all \
  --name pdfscore_pipeline_pytest_dev \
  -v "$PWD":/workspace \
  -v "$omr_host:$omr_runtime:ro" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e OMR_DLN_MODEL_PATH="$omr_runtime" \
  "$image_id" bash
```

イメージタグを更新しても、既存コンテナのイメージは変更されません。Docker やランタイムの更新後は、コンテナを再利用する前にコンテナの不変イメージ ID を検査し、アクティブなチェックアウトに対してその ID を解決して互換性を確認してください。

```bash
docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}}'
python3 scripts/docker_image_resolver.py resolve --repo-root . \
  --image-ref "$(docker inspect pdfscore_pipeline_pytest_dev --format '{{.Image}}')" --explicit
```

非互換である場合は、代替コンテナを作成する前に、その inspect メタデータを保存し、実行中であれば停止して、未使用のアーカイブ名にリネームしてください。これにより書き込み可能レイヤーとバインドマウントが保持されます。通常の更新作業の一環としてコンテナを削除しないでください。pytest の再インストールは新しい開発用コンテナにのみ行います。パイプラインで使用する前に、CUDA、アセット、および本番プロビナンスを再度確認してください。

互換性のあるコンテナがすでに存在するものの停止している場合は、以下で起動します。

```bash
docker start pdfscore_pipeline_pytest_dev
```

永続検証コンテナに開発用のテストツールを一度だけインストールします。リポジトリのモック化された Docker ライフサイクルテストには Git が必要ですが、いずれのツールも本番イメージには追加されません。

```bash
docker exec pdfscore_pipeline_pytest_dev \
  /bin/sh -c 'apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*'
# Root in this container accesses the host-owned checkout; trust this mount only.
docker exec pdfscore_pipeline_pytest_dev git config --global --add safe.directory /workspace
docker exec -w /workspace pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pip install pytest
```

リポジトリの pytest は以下で実行します。

```bash
docker exec -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python -m pytest <tests-or-options>
```

パイプラインおよび評価コマンドでも同じインタプリタを使用できます。

```bash
docker exec -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_pytest_dev \
  /opt/venv_pipeline/bin/python <script-or-module>
```

この永続コンテナは、クリーンアップを明示的に意図する場合にのみ削除してください。このコンテナの目的は、短命な本番ランタイムコンテナに対して検証専用ツールを繰り返し再インストールする手間を省くことです。

### 本番専用環境の採用スナップショット (#398)

ローカルの保守対象環境は 2026-10-03 に更新されました。

| 参照 | 採用された環境 |
| --- | --- |
| `pdfscore_pipeline_gpu:latest` | アプリケーションリビジョン `b25af348` からビルドされた本番専用イメージ `5311cf22ab01` |
| `pdfscore_stage_e_reproduction:latest` | 保持されている Stage-E コンポーネント互換イメージ `c5da1954371d`（現行のメイン venv であり、完全な過去環境ではない） |
| `pdfscore_pipeline_pytest_dev` | `5311cf22ab01` をベースとした実行中の開発用コンテナ（GPU、チェックアウト／外部モデルマウント、pytest 8.4.2、および Git を含む） |
| `pdfscore_pipeline_gpu:before-issue398` | 保持されている以前のオールインワンイメージ（現在のセットアップ手順からは除外） |
| `pdfscore_pipeline_pytest_dev_before_issue398` | 旧開発用コンテナの停止済みアーカイブ（書き込み可能レイヤーを保持） |

その他の Issue スコープのコンテナや過去のコンテナは、保守対象環境へ昇格されませんでした。これは採用時点のスナップショットであり、タグは今後変更される可能性があります。現在のアイデンティティを確認するには、`docker image inspect` および `docker inspect` を使用してください。inspect スナップショット、移行コマンド、プリフライト、およびテストのエビデンスは、ローカルの `logs/issue398/environment-update/` 配下に保持されています。

## レビューヘルパー

手動での GT レビューヘルパーとしては、引き続きブラウザベースの GT エディタが推奨されます。

```bash
python3 tools/gt_relabel_gui/server.py --mode gt --config <config.json> --port 8010 --host 0.0.0.0
```

生成されたオーバーレイおよびレビュー出力は、該当するワークフローに従って `logs/` 配下または設定されたレビューパッケージルートに出力してください。
