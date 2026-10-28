# 現行productionパイプラインのアーキテクチャ

<!-- translation: {"original":"PIPELINE_ARCHITECTURE.md","source":{"sha256":"fb355d027d054bf3fc13d94759c887f45bd6b86a538c896621433125378df274"},"state":"draft"} -->

[English / 原文](PIPELINE_ARCHITECTURE.md)

- 原文: [PIPELINE_ARCHITECTURE.md](PIPELINE_ARCHITECTURE.md)（英語正本）。
- 翻訳元: same PR。相互リンク追加後の原文ファイルの SHA-256: `fb355d027d054bf3fc13d94759c887f45bd6b86a538c896621433125378df274`。
- 状態: `draft`。全文に対応する日本語版。意味・網羅性と日本語文章のレビュー結果はPRに記録する。

> **アーキテクチャの正本。** 本文書は`develop`上の現行productionパイプラインを、
> 特に`dense_full_pipeline`ルートを中心に説明する。記述と食い違う場合は、ソースコード、
> テスト、機械可読プロファイルを優先する。過去のIssue文書はこのアーキテクチャに
> 至った経緯を説明するものであり、現行ルートの理解に必須ではない。
>
> 将来のengine/serviceの責任境界は、別の文書
> [将来のサービスアーキテクチャ（英語・未翻訳）](FUTURE_SERVICE_ARCHITECTURE.md)に記載する。
> このロードマップ文書は、現行の実行時動作の正本ではない。

## この文書の読み方

この文書は、楽譜から小節番号を生成する現行productionパイプラインを理解したい開発者や
レビュー担当者向けである。過去のIssueを読んでいない読者も対象とする。まず以下の全体像と
コンポーネント表を読み、具体的な設定、成果物、座標の所有権、失敗時の規則、閾値、過去の
根拠は後続の詳細節で確認できる。**譜表**は一つのパートのための譜線の集まり、
**段（system）**は同時に演奏する譜表を横一列にまとめたもの、**小節**は小節線で区切られる
楽曲上の区間である。段の端には暗黙の境界もある。

## 楽譜から番号付き出力まで

入力はPDFまたは保存済みページ画像である。PDFレンダリングが有効なら最初にページを画像化する。
小節線候補を再構築するdense detectorは、保存済みのページ画像ファイルを必要とする。選択した各ページで、
小節線の候補を探してスコアを付け、譜表・段・小節の構造を作り、複数小節休符（MMR）を
認識して、最終的な小節番号を計算する。小節線候補のスコア付けには畳み込みニューラル
ネットワーク（CNN）を使う。設定に応じてオーバーレイ、manifest、レビューパッケージも生成する。
ユーザー向け配布では、レビュー操作を通じて番号付きの最終PDFも生成できる。

```text
PDFまたは保存済みページ画像
  -> 有効な場合はPDFページをレンダリングし、ページ画像を保存
  -> 選択ページのx4超解像（SR）画像を準備（Real-ESRGAN）
  -> 元画像とx4画像を検出（HOMRは2回、OMR-DLNはx4画像で実行）
  -> 補助検出を組み合わせ、小節線候補を生成・判定（CNN）
  -> ページのフィルタリングと、任意のユーザー小節線補正
  -> Phase A: 譜表を段にまとめ、小節構造と基本番号を作成
  -> Phase B: 有効な場合は複数小節休符とその小節数を認識
  -> 認識結果とユーザーの小節上書きを統合
  -> Phase C: 上書きと楽章境界を適用し、番号を確定
  -> 設定に応じた出力: 番号付け、オーバーレイ、manifest / レビューパッケージ / 最終PDF
```

HOMRとOMR-DLNは、ここでは小節線を含む楽譜の特徴を検出するために使う楽譜認識システムである。
**ページごとに行う2回のHOMR推論は役割が異なる。** 保守対象の元画像HOMRは、
正本となるbaseline小節線boxと譜表ジオメトリを提供する。2回目のHOMRは保存済みx4画像を読み、
検出の裏付け、コネクターの意味情報、MMRの切り出しに必要な情報を提供する。
OMR-DLNも同じx4画像を読む。後続に渡す検出結果は必要に応じて元ページ座標に戻す。
これは入力と所有する結果の役割が2つあるということで、過去版と現行版の2つのHOMR実行環境を
productionで併用するという意味ではない。保守対象の元画像プロファイルとcurrent-x4サポートは
保守対象のproductionイメージ/実行環境を使う。過去のbaselineである`stage_e_verified`実行環境の資産は、
別途ビルドするStage-E再現用拡張に隔離され、設定された正規のproductionルートには含まれない。

| コンポーネント | 入力 | 出力と役割 |
| --- | --- | --- |
| Real-ESRGAN x4 | 選択した元ページ画像 | 2つのx4サポート検出器向けにx4画像とprovenance（生成元を示すメタデータ）を保存する。1つのSRプロセスをバッチで使い、HOMR/OMR推論の前に終了する。 |
| 保守対象の元画像HOMR | 元ページ画像 | ソースページ座標のbaseline小節線検出結果と譜表マスクを出力する。検出とPhase Aの正本ジオメトリとなる。 |
| Current-x4 HOMR | 保存済みx4ページ画像 | 補助検出結果、譜表マスク、コネクター意味情報マスクを出力する。必要な検出/サポート座標は元に戻す。 |
| OMR-DLN | 同じ保存済みx4ページ画像 | x4 HOMRとともに元画像baselineの検出を確かめるための補助小節線予測を出力する。 |
| 小節線CNN | 必要に応じて譜表ストロークアダプターで譜表単位に正規化した、ページ上のdense候補 | detectorが使う候補スコアを出力し、その後に譜表ストロークの重複を抑制する。 |
| MMR CNN + RapidOCR | Phase Aの小節、元ページ画像、任意のx4由来の譜表y方向サポート | 複数小節休符と数字を認識し、最終番号付けのための小節上書きを生成する。 |

**Phase A — 譜表・小節構造と基本番号付け:** 採択した小節線ジオメトリ、任意のユーザー小節線補正、
元画像の譜表ジオメトリ、current-x4のコネクター根拠から、物理的な段と小節を構築する。
結果は`intermediate/<page>/numbering_base.json`である。これは次のフェーズで共通に使う
トポロジーであり、これがなければMMRが参照すべき小節の位置とindexを共有できない。

**Phase B — 複数小節休符の認識:** 複数小節休符（MMR）は、複数の休止小節を1つの記号と
小節数で表す。MMRが有効な場合、MMR CNNとRapidOCRはPhase Aの小節と任意のx4由来の
垂直方向の譜表サポートを使って元画像を調べ、`intermediate/<page>/overrides_mmr.json`を生成する。
Phase BはPhase Aのトポロジーを再利用し、食い違う可能性のある別の構造を作らない。
ページのPhase A結果がない場合、そのページのMMR準備をスキップする。

**Phase C — 補正を反映した最終番号付け:** MMRとユーザーの小節上書きを統合し、通常の最終番号付けで
それらと楽章境界を適用して`outputs/<page>/numbering_final.json`を書き出す。
表示上1つのMMRが複数小節を表す場合やユーザー補正によって番号が変わる場合があるため、この処理が必要になる。
任意のオーバーレイと、設定されたレビュー/最終出力は確定後の結果を使う。

## 検出とグルーピングで使う用語

**denseルート**は、CNN判定前に現在の実行から幅広く小節線候補を再構築する、設定で選択された
検出経路である。**ディスパッチ**は設定した検出ルートに応じて実行する処理を選ぶことを指す。
このルートでは`src/pipeline/detection/__init__.py`が`dense_orchestrator_batch_sr.py`を選択する。

**hybrid合意判定**は、元画像HOMRのbaseline boxをx4 HOMRまたはOMR-DLNの結果で確かめ、
裏付けのあるbaseline boxを元の座標のまま残す。続いて**probe**が対象となる譜表帯域と
画像のインクを走査し、追加候補を生成する。**rescue**は既存の帯域横断・最右・間隙の規則を使い、
候補を拾い直す処理である。これらは候補の生成であり、すべてが小節線だという保証ではない。
`src/pipeline/steps/staff_strokes.py`の**譜表ストロークアダプター**はCNN判定の前に、
複数譜表にまたがる候補を、条件を満たす場合に1譜表単位の断片（譜表ストローク）へ調整する。
また、対象となる元画像HOMRの断片を既存の合意判定に通して補充する。
CNN判定後の重複抑制は、重なった譜表ストローク候補を除く。詳細な条件と例外は後述する。

Phase Aの**グルーピング**は、譜表を段に割り当て、譜表と小節線のジオメトリから
縦に対応する小節を構築することを指す。ここでの**コネクター**は、隣接する譜表を同じ段に
まとめるかを決める際、ジオメトリとともに使う段の左端・開始位置付近の結合の根拠である。
current-x4 HOMRは2種類の意味情報マスク、`connector_symbols`（記号レイヤー）と
`connector_brace_dot`（括弧/点レイヤー）を提供する。`SystemConnectorEvidenceExtractor`は
隣接譜表の組について該当領域を測定し、`ConnectorAwareSystemBuilder`はその有無を
グルーピングの判断材料の一つとして使う。これらのコネクターマスクは、Phase Aの譜表ジオメトリの
正本となる元画像の譜表マスクとは別である。**sidecar**は、`mmr_support.json`のように
メイン結果とは別に出力し、サポート情報や監査情報を持つ成果物である。
**producer**は成果物を生成する処理、**consumer**は後続でそれを読む処理を指す。

現行設計では、追加のHOMR推論やMMR専用構造の再構築を行わず、サポート成果物を
グルーピングとMMRで再利用する。以前はSRをページごとに実行していたが、現在は選択ページを
バッチで処理してそのプロセスを終了した後、ページ単位のHOMR/OMR処理を行う。
過去の元画像Stage-E baselineは保守対象の元画像baselineに置き換えられ、旧実行環境の資産は
別の再現用拡張に残している。
[Issue #274](https://github.com/M763468/PDFScoreBar/issues/274)、
[Issue #284](https://github.com/M763468/PDFScoreBar/issues/284)、
[Issue #294](https://github.com/M763468/PDFScoreBar/issues/294)に、それぞれの調査と判断の経緯がある。
各Issueの測定値や旧設定は過去の根拠であり、今回の新たな検証結果でも、現行sourceとプロファイルの代わりでもない。

## 対象範囲と正規のエントリポイント

ユーザー向け配布には、Linux Dockerランチャーとして`docker/distribution.py`、
既存v1の`PipelineJobExecutor`への薄いアダプターとして`docker/distribution_job.py`を追加する。
engineとともに、パッケージに紐付く`tools/review_correction`アプリケーションを配布する。
ローカルレビューアプリケーションは、不変の`history/`チェックポイント、パッケージ単位の
再開セッション、プロセスロックで保護されたアプリケーション状態を所有する。
アップロードされた注釈付きPDFは、チェックポイントの元のソースと照合して検証し、
クリーンな認識入力とは別に表示する。再開後の適用処理は保持済みの認識結果を再利用し、
`review/number_layer.py`で検証済みの9 pt番号レイヤーを追加し、ネイティブ注釈とCropBoxを保持する。
注釈だけを変更した再エクスポートでもxrefが変わる場合がある。再開アダプターは、
所有する古いストリームを除去する前に、順序付きのコンテンツ/ストリームハッシュ、マーカー、
ページ全体のレンダリングを、検証の裏付けがあるパッケージ内の結果と照合して同一性を確認する。
未知の書き換えは拒否する。旧形式の入力スナップショットは、ソース/補正のidentityを
検証してからのみ取り込む。古いPDFが存在するだけでは成功とはみなさない。
再開を繰り返す場合は、元のレビュー配下のフラットなセッションレジストリを使い、
チェックポイント状態と番号付けの所有権をそれぞれ解決する。
チェックポイントIDとセッションIDはローカルな成果物のidentityであり、公開service/job APIを追加するものではない。
[Issue #441の製品統合](dev/ISSUE441_PRODUCT_INTEGRATION.md)を参照。
正確な選択範囲とdevelop限定の境界は
[最小mainline構成（英語・未翻訳）](MINIMAL_MAINLINE_SURFACE.md)、ユーザーの操作方法は
[ユーザーガイド（英語・未翻訳）](USER_GUIDE.md)に記載する。
共通の小節線ジオメトリは`src/common/barline_geometry.py`に置く。GTマッチングは配布対象外とする。

保守対象のフルパイプライン実行環境は`pdfscore_pipeline_gpu`イメージであり、
設定駆動のエントリポイントは`src/pipeline/main.py`にある。
ルートの`Dockerfile`は保守対象のproduction実行環境だけをビルドする。
過去のStage-Eのソース、venv、モデル資産、provenanceは、明示的な再現用拡張
`docker/Dockerfile.stage-e`に置く。正規の事前確認で必要なのは、保守対象プロファイルのprovenanceだけである。
2種類のビルド経路は[環境（英語・未翻訳）](ENVIRONMENTS.md)を参照。

```bash
make docker-build
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

dense production設定は次を選択する。

```yaml
detection:
  detector_route: dense_full_pipeline
  homr_profile: maintained_original
  enable_sr: true
  sr_scale: 4
  sr_compile_mode: reduce-overhead
```

`src/pipeline/detection/__init__.py`は、このルートを
`src/pipeline/detection/dense_orchestrator_batch_sr.py`にディスパッチする。
これは採択済みのdense orchestratorに、Issue #284の専用処理を1つ加えたものである。
Real-ESRGAN x4生成を、ページごとのHOMR/OMRソース生成より前の、全ページ専用フェーズへ移している。
汎用の`src/pipeline/detection/orchestrator.py` / `HybridDetector`経路は別の標準ルートであり、
これを根拠にdense productionのアーキテクチャを推測してはならない。

## 入力から出力までの処理順序

現行の呼び出し順序は次のとおり。

```text
PDFまたは永続化済みページ画像
  -> 必要に応じたプロセス内PDFレンダリング / ページ収集
  -> dense detectorルートのディスパッチ
       -> 全ページ専用のcurrent-x4 SRプロセス
            -> 選択した全ページで1つのReal-ESRGAN x4モデル/実行環境を再利用
            -> FP16 + channels_last + tile=400/tile_pad=10
            -> torch.compile(reduce-overhead)
            -> タイルごとのCUDA uint8変換 + CPUでの結合
            -> 永続化したx4画像 + ページごとのprovenance
       -> SRプロセスが終了し、CUDA/モデル状態を解放
       -> ページ単位の保守対象ソースworker（maintained_source_page_worker）
            -> 不変commitに固定した保守対象HOMRを元画像に適用
            -> current-x4サポートworker（事前計算済みx4画像を入力として利用）
                 -> 事前計算して永続化したx4画像でcurrent-runtime HOMRを実行
                 -> 同じ永続化済みx4画像でOMR-DLNを実行
            -> hybrid合意判定
       -> dense候補/probeの再構築
       -> 譜表単位のCNN候補正規化（maintained_originalのみ）
            -> 複数譜表にまたがるboxを分割し、元画像HOMRの断片をSRまたはOMRの合意判定で補充
            -> 元のprobe行のseedとコネクターマスクの根拠を保持
       -> CNNスコアリング + 厳密な譜表ストローク重複抑制
  -> ページフィルタリング / ユーザーによる小節線補正
  -> Phase Aの物理グルーピング + numbering_base
       -> 保守対象の元画像の譜表ジオメトリ
       -> current-x4コネクターの意味的根拠
  -> current-x4 MMRサポートsidecar
       -> Phase-Aのトポロジー/xジオメトリを再利用
       -> current-x4 HOMRの譜表yジオメトリを対応付け
  -> MMR CNN + RapidOCR
  -> MMRとユーザーの小節上書きを統合
  -> Phase Cの最終番号付け / 任意のオーバーレイ
  -> 設定されている場合はmanifest / レビューパッケージを実体化
```

譜表ストロークアダプターはdense生成、フィルタリング、rescueの後に動く。
抽出済みの少なくとも2つの譜表それぞれと2譜表単位以上交差するboxだけを分割し、
単一譜表のコネクターの尾部は変更しない。追加する元画像HOMRの断片は、実際のCNN推論の前に、
既存のSRまたはOMRとのIoU > 0.5の合意判定を通過する必要がある。
CNN後の重複抑制は、X中心間距離 <= 抽出譜表単位の中央値の0.1倍、垂直方向の重なり >= 0.8を使い、
番号付けと互換性のある正規のジオメトリと、そのジオメトリ自体のCNNスコアを保持する。
これは論理的な時間境界の統合とは別である。ページごとの正規化・抑制sidecarは、
ソースハッシュと代表候補を保持する。この実行時処理にGTや評価データは入らない。
CNNの検索では、相対パス、絶対パス、シンボリックリンクの画像パスを同じ譜表単位マップ（画像と譜表単位サイズの対応表）のidentityに解決する。
probeディレクトリは、rescue、アダプター、CNNを通じて画像の親ディレクトリ/stemによるidentityを
一貫して使い、複合的なscore/pageのstemも対象とする。inventoryの論理的なscore/pageラベルは、
アダプターディレクトリの選択には使わない。
inventoryはシンボリックリンクを解決せずに画像パスを絶対化し、rescueとCNNの出力先について
呼び出し元の親ディレクトリ/stemを保持する。サポートメタデータはこのidentity、または使い捨ての
source-page worker内で解決したidentityを使える。アダプターは、これら既知の場所に結果の実体が
ちょうど1つ存在することを要求し、その画像と完了状態を確認する。unit-mapの検索は引き続き
ファイルidentityを解決する。
重複除去が有効なら、正常に得られた空のCNN結果にも空の抑制監査を出力し、
重複除去を無効にした再実行では古い抑制sidecarを除去する。
採択された譜表のうち1つでも単位を推定できないページ（1線の打楽器記譜を含む）は、
元の候補を保持し、このアダプターとストローク重複除去をスキップする。
そのsidecarは幾何学的な閾値を作り出さず、`no_staff_unit_size`を記録する。
これにより、混在ページ上の未知の声部も保持される。
固定入力での検証は`tools/issue416/IMPLEMENTATION.md`を参照。

`pdf_to_images`は、有効な場合、現在は`PipelineOrchestrator`内でインプロセス実行される。
検証済みdenseルート自体は永続化済みのページ画像ファイルを要求し、
detector境界でメモリ内にしかない画像を拒否する。

## オーケストレーションとprobeのモジュール境界

`PipelineOrchestrator`は、入力の検証/レンダリング、フェーズ順序、共有モデルキャッシュ、
telemetry、manifest/reviewへのディスパッチを所有する。既存のフェーズメソッドは実行を
`steps/numbering_phases.py`へ委譲する。このモジュールは、基本レイアウト/小節線補正、
バッチMMR準備、最終上書きの適用、ページをまたぐ番号付け、オーバーレイを含む。
同モジュールの`NumberingPhaseServices`は、ディスパッチ時に現行orchestratorの操作フックを渡す。
フェーズヘルパーは同じコンテキストとキャッシュを共有し、呼び出し元をimportしない。
レビューの設定/前提条件とmanifestへの投影は`review/pipeline_review.py`に置く。

probeのエントリポイントは、既存のオプション/API契約と候補の採択順序を維持する。
`bands.py`は譜表帯域と対象となるx領域を解決する。`measurements.py`は帯域と延長部のインクを
投影し、seedを選び、候補ごとの走査帯域、行プロファイル、xピーク、はみ出しを測定する。
測定処理は候補の採択やrescueを行わない。`existing.py`は既存小節線とのマッチングを所有し、
`rescue.py`は既存の帯域横断/最右/間隙rescueを実行する。`debug.py`はデバッグの根拠を
シリアライズし、`types.py`は設定レコードを保持する。これらのモジュール境界によって、
閾値、丸め規則、結果schema、プロセス寿命は変わらない。
probeの診断レンダリングと任意の幅広候補分割は、要求された場合にのみimportする。
最小ユーザー配布は、これらのdevelopツールと単独の番号付けCLI/オーバーレイを含まない。
最終ユーザーPDFは`review/final_output.py`が生成する。

## 検出失敗時の契約

正規のbatch/source-page/support workerは、HOMR実行前にnullでない有効な`precomputed_sr`を要求する。
`sr_mode=page_local`は明示的なdevelop互換モードであり、バッチ失敗からの復旧手段ではない。
旧形式の非バッチプロファイルは、このモードを明示的に記録する。
ページ単位のSRは`strict=True`で汎用ヘルパーを呼び、正確なx4形状を確認する。
汎用の開発用呼び出し元は`strict=False`の互換性を維持する。バッチSRは実行時エラーと形状チェックの失敗を伝播する。
正規のHOMR/OMR合意判定は、有限の数値座標と有効な境界を含む厳密な検出JSON解析を行う。
有効な空予測は引き続き正常として扱う。正規のdense rescueはseedファイルを要求する一方、
汎用probeは引き続きseedなしでも動作できる。エラーはworkerを通じて伝播し、
final/reviewを公開する前にengine jobをFAILEDにする。

## HOMRモジュールの所有権

保守対象/current workerはproductionが所有する`src/homr_runtime/`をimportする。

| 責任 | モジュール |
| --- | --- |
| 予測/座標レコードと確立済みの実行時デフォルト | `types.py` |
| 画像/セグメンテーションの座標変換 | `transforms.py` |
| 画像特徴とセグメンテーションによる小節線候補 | `barline_candidates.py` |
| 譜表/記号の組み立てと互換性用のパッチ箇所 | `heuristics.py` |
| 符頭/譜表のフィルタリングと終端小節線の回復 | `filtering.py`, `end_barlines.py` |
| モデル予測、Segnetキャッシュ、callable APIの適合 | `predictor.py`, `segnet_cache.py`, `api_compat.py` |
| ロギングと予測/マスクのシリアライズ | `utils.py`, `reporting.py` |

`maintained_profile.py`は保守対象baselineの実行を所有する。
共通のソース生成とbatch-SRのスケジューリングは`profile_sources*.py`に置く。
`maintained_profile_hybrid.py`は保守対象backendと`maintained_source_page_worker.py`を選択する。
過去のプロファイル用アダプターは、`homr_profile.py`、`homr_profile_compat.py`、
`profile_hybrid*.py`、`verified_source_page_worker.py`に残す。
これらは過去のプロファイルを明示的に選んだ場合にのみロードする。
`src/homr_eval_scripts/core/`は旧importアダプターに加え、評価指標、診断CSV生成、比較レポートを保持する。
productionはこのパッケージをimportしない。

callable互換性とコネクター取得の処理は、引き続きconsumerが保持する実際のpredictor/heuristicsの
bindingへパッチを適用する。heuristics、predictor、Segnetキャッシュのアダプターは、
正規モジュールオブジェクトの別名となり、古いimportパスでのcallableのパッチ箇所と
クラス/キャッシュidentityを保持する。これらの所有権変更によって、以下のTwo-HOMRの
入力/座標契約やプロセス寿命の契約は変わらない。

## Two-HOMRの所有権契約

dense productionルートの各ページには、HOMRニューラル推論の用途がちょうど2つある。
全ページReal-ESRGANフェーズは追加のHOMR推論ではなく、ページ単位のsource workerが
利用する共通のx4画像producerである。

### 1. 元画像を使う保守対象HOMR

- **Producer:** `BatchSRVerifiedProfileHybridDetector` / `VerifiedProfileHybridDetector`を通じた
  `run_homr_profile("maintained_original", ...)`。
- **入力:** 元の/ソースのページ画像。倍率1。
- **Provenance:** `configs/detector_profiles/maintained_original_homr.json`。
- **役割:** 正本となるdetector baseline、およびPhase-Aの段/小節構築で正本となる譜表ジオメトリ。
- **座標空間:** ソースページ座標。
- **永続的な実行時成果物の主なサブツリー:**
  `<hybrid_output>/baseline/batch/<page>/...`。
- **Consumer:** detector inventory / hybrid合意判定。その後、番号付けは解決済みbaseline譜表マスクを利用する。

この固定プロファイルは、現行productionにおける正本の元画像baselineを提供する。
過去のStage-E実行環境ではなく保守対象の実行環境を使い、現行production経路ではx4で再実行しない。

### 2. 永続化済みx4サポート上のcurrent-runtime HOMR

- **x4画像producer:** `src/pipeline/detection/current_sr_batch_worker.py`。
  `BatchSRVerifiedProfileHybridDetector`が選択ページ集合に対して1回起動する。
- **x4 HOMR/サポートの所有者:** `src/pipeline/detection/current_support_worker.py`。
- **入力:** 専用SRプロセスが事前計算して永続化したReal-ESRGAN x4画像。
- **Producerの実行環境:** 過去の`stage_e_verified`実行環境ではなく、現行パイプラインのHOMR実行環境。
- **公開するbundle:** ソース座標の`current_sr_detection`、current-HOMR譜表マスク、
  完全なコネクター意味情報のペア、x4画像/provenance、OMR-DLN予測。
- **座標契約:** downstream consumerへ渡す検出と意味情報のサポートは、必要に応じて
  ソースページ座標へ戻す。永続化済みx4画像は物理的なx4ソース成果物のまま保持する。
- **Consumer:** detectorのhybrid合意判定、コネクターを考慮したグルーピングのサポート、
  MMRの垂直方向の譜表サポート。

元画像用の固定された`maintained_original`プロファイルは不変であり、現行production経路ではx4で再実行しない。
過去の`stage_e_verified`プロファイル用に隔離された実行環境の資産は、ルートのproductionイメージではなく、
別途ビルドするStage-E再現用拡張イメージ（`docker/Dockerfile.stage-e`）に保持する。
過去のプロファイルは正規のディスパッチには含めない。この拡張は過去のTwo-HOMR環境全体を再構築するものではなく、
そのfull-68指標を保証しない。

production経路は、各ページのsupport worker内でReal-ESRGANを初期化しない。
専用SRプロセスが先に全ページを処理して終了する。その後で初めて、使い捨てのページ単位workerが
保守対象baseline HOMR、current-x4 HOMR、OMR-DLNを実行する。
これにより、ページ間でSRモデルを再利用しながら、Real-ESRGANのモデル/活性化状態と
後続HOMR/OMRのGPUフェーズが重ならないようにする。

## Current-x4 SRの実行時契約

Issue #284で、Real-ESRGANフェーズを明示的な再利用可能な実行時境界にした。

- モデル: `RealESRGAN_x4plus`。
- 精度/レイアウト: FP16、`channels_last`。
- タイル設定: `tile=400`、`tile_pad=10`。
- 出力経路: 各タイルをCUDA `uint8`へ変換し、CPUへコピーして結合し、永続化するx4ページ画像として書き出す。
- モデル寿命: 選択ページのバッチ全体で1つのSRプロセス/モデルを再利用する。
- コンパイルモード: production設定では`torch.compile(..., mode="reduce-overhead")`。
- メモリ境界: ページ単位のHOMRまたはOMR-DLN推論を始める前にSRプロセスが終了する。

コンパイル版とeager版のSR経路は、意図的にバイト単位の一致を必須としていない。
受入判定はdetector/トポロジー/番号付け/MMRの意味的契約に対して行う。
Issue #284の最終full-68ゲートは、正規の全68ページでこれらの契約を保持しながら、
SRバッチとE2Eの両方の実時間を短縮した。

## Detector入力のprovenanceとスコアリングのデフォルト

Detector入力のprovenanceは機械可読契約であり、実行ディレクトリ名やHOMR/SR/OMRが実行された
という事実から推測するものではない。`src/pipeline/detection/input_contract.py`は、
各detector設定を次のいずれかに分類する。

```text
fresh_upstream
precomputed_candidate_route
```

両方の候補ソース上書きが未設定の場合に限り、実行は`fresh_upstream`となる。

```text
precomputed_probe_candidates_root
cnn_bands_from
```

いずれかの上書きを設定すると、現行HOMR/SR/OMRステージも実行され、新しい出力ディレクトリに
新しい候補JSONが書かれた場合であっても、その実行は`precomputed_candidate_route`となる。
新たな出力bytesだけでは、正本入力が新規生成された証拠にならない。

detector orchestratorはこの契約を次に記録する。

```text
<run_dir>/intermediate/detector_input_contract.json
```

manifestが次を報告する場合に限り、その結果を新規入力によるdetector検証と表現できる。

```text
mode = fresh_upstream
fresh_upstream_authoritative = true
override_keys = []
```

チェックポイント/事前計算ルートは、過去結果に対する回帰確認、CNN比較、downstreamの切り分けに
引き続き有用だが、その指標には入力モードを明記し続ける必要がある。
この区別を確立した原因調査はIssue #245とPR #251に保持されている。
現在の正本は現行のソース/テストと機械可読manifestである。

CNNスコアリングのNMSは`src/pipeline/detection/config.py`でデフォルト無効
（`DEFAULT_CNN_APPLY_NMS = False`）であり、引き続き`detection.cnn_apply_nms: true`による
明示的な有効化を必要とする。Issue #142に過去の因果関係の根拠と、このデフォルトを確立した
PR #154を記録している。将来デフォルトを変更する場合は、スコアリング方針を黙って変更せず、
正規の精度/downstreamの明示的な根拠を必要とする。

## Detectorの合意判定とdense候補ルート

`BatchSRVerifiedProfileHybridDetector`は`VerifiedProfileHybridDetector`と同じ
合意判定の意味を保持し、次を組み合わせる。

- 保守対象の元画像baselineの検出結果。
- `current_x4_support.current_sr_detection`。
- 永続化済みx4サポート画像から生成したOMR-DLN予測。

hybridステップは、x4 HOMRまたはOMR-DLNの裏付けを使ってbaseline HOMRのboxをフィルタリングする。
返すbaseline boxへx4座標を混ぜ込むことはない。以前の固定HOMRをx4上で実行する推論は、
この合意判定には含まない。current x4 HOMRの出力が唯一のx4 HOMRの所有元であり、再利用する。

続いて`dense_orchestrator_batch_sr.py`は採択済みのdense orchestratorルートに従い、
現行実行のinventoryを書き出して`reconstruct_dense_full_pipeline_route()`を呼ぶ。
候補/probeの再構築とCNNスコアリングは現行実行に対して動作する。
検証済みproductionルートでは`historical_detector_artifact_runtime_input`はfalseである。

## 譜表・小節構造と基本番号付け（Phase A）：コネクターの意味情報と座標の所有権

Phase A（`run_base_numbering_and_barline_correction`）は、
`MeasureNumberingPipeline`で物理的な番号付けレイアウトを構築する。

- **小節線のxジオメトリ:** 任意のユーザー小節線補正を適用した後の、採択済みdense detector出力。
- **譜表/段のジオメトリ:** 保守対象の元画像譜表マスク。
- **コネクターの意味情報:** 宣言されたcurrent-supportサブツリーから取得した、current-x4 HOMRのコネクター意味情報成果物。
- **番号付けに使う画像:** ソース/元のページ画像。
- **出力:** `intermediate/<page>/numbering_base.json`。

宣言された`current_support`サブツリーは契約である。このサブツリーが存在しながら
必要なコネクター意味情報のペアが欠ける場合、productionはコネクターの根拠の意味を
黙って切り替えることなく例外を送出する。current supportを宣言しない汎用の呼び出し元は、
従来のフォールバック動作を維持する。

採択済みproductionの番号付け動作は、意味情報成果物の欠落とproducerのジオメトリの不一致も区別する。
current-HOMRの意味情報側の譜表マスクと番号付け用の譜表ジオメトリで譜表数が異なる場合は、
コネクターの根拠を測定するために番号付け用の譜表ジオメトリを使う。コネクターマスクは引き続き使う。
この互換動作は意図的なもので、Issue #274でも保持した。

## 複数小節休符の認識（Phase B）：MMRサポートの再利用

dense MMRは、元ページでHOMRを**再実行せず**、MMR専用サブツリーでPhase-Aの番号付けを**再構築しない**。

`src/pipeline/mmr_geometry_handoff.py`は、`src/pipeline/mmr_support_reuse.py`を通じて
`intermediate/<page>/mmr_support.json`を構築する。

この契約は意図的に非対称としている。

- Phase-Aの`numbering_base`は、トポロジー、小節番号、段への所属、通常の水平方向/xジオメトリの正本であり続ける。
- current-x4 HOMRの譜表ジオメトリは、MMRの垂直方向/yの切り出しサポートを提供する。
- 譜表スロットの対応付けはスケールに依存しない。あるスロットにcurrent-x4の譜表を
  対応付けられない場合、サポートビューは新しいトポロジーを作らず、そのスロットのPhase-Aジオメトリへフォールバックする。
- MMRサポートのprovenanceでは、`original_image_homr`はfalse、`second_numbering_rebuild`はfalseである。

`run_mmr_batch()`は、Phase-Aのページpayload、元のページ画像、任意のMMRサポートビューを利用する。
永続的な`MMRClassifier`と`MMROCREngine`（RapidOCR）は、orchestratorプロセス内でページをまたいで再利用する。

## 補正を反映した最終番号付け（Phase C）：削除済みのMMR再構築との違い

Phase Cは引き続き`numbering_final.json`を実体化する。採択済みの小節線と譜表マスクを再ロードし、
通常の`MeasureNumberingPipeline`でページオブジェクトを再構築してから、
統合済みのMMR/ユーザー小節上書きを適用し、必要に応じてオーバーレイをレンダリングする。

MMR/手動の上書きと楽章境界は、`numbering_base.json` / `numbering_final.json`の
空でない段だけを詰めた`systems`配列における0始まりのindexを使う。
内部の`Page.systems`は空の段も保持する。Phase Cは補正適用前に、未補正の小節ジオメトリから
表示対象を解決するため、空の段が公開system indexを消費することはない。
page indexは統合時にはバッチ全体を基準とし、ページごとの番号付けでは0始まりに付け替える。
最終メタデータは`system_index_contract: compact_nonempty_systems.v1`を記録する。
このマーカーのないキャッシュ済み最終成果物は、補正が別の物理的な段を指す可能性があるため再構築する。
この契約は統合JSONと最終PDFの行ラベルで共通である。

この通常の最終化処理は、**削除済みの旧MMR専用の2回目の番号付け再構築**とは異なる。
削除した経路は、別のPhase-B/MMRジオメトリを準備するためだけに存在し、Phase Aから乖離する可能性があった。
現行のMMRサポートは、代わりにPhase-Aのトポロジーを再利用する。

## プロセスとメモリの境界

| 境界 | プロセスモデル | メモリ/所有権上の目的 |
| --- | --- | --- |
| `src/pipeline/main.py` / `PipelineOrchestrator` | メインパイプラインプロセス | オーケストレーション、番号付け、永続的なMMR classifier/OCRを所有 |
| `current_sr_batch_worker` | 選択した全ページに対する1つの使い捨てプロセス | Real-ESRGANのモデル/import/CUDA寿命と永続化するx4生成を所有 |
| SRバッチプロセスの終了 | 厳密なフェーズ境界 | HOMR/OMRより前にReal-ESRGAN/コンパイル/CUDA状態を解放 |
| `maintained_source_page_worker` | SRバッチ後に起動するページごとの使い捨てトップレベルPython worker | ページ単位の検証済みソース生成の寿命を限定 |
| 保守対象の元画像HOMR | ページworker内 | 不変の保守対象baselineのみ |
| `current_support_worker` | 事前計算済みx4を使う子worker | current x4 HOMR + OMR-DLNサポート契約。productionのSRモデル寿命は所有しない |
| denseルート + CNN | source worker終了後にimport/実行 | 重いソース生成状態を保持し続けることを回避 |
| MMRバッチ | メインパイプラインプロセス | 永続的なclassifier/OCRを再利用。HOMRを実行しない |

子プロセスの具体的なinterpreterは`src/pipeline/core/python_env.py`が選択する。
保守対象の実行環境は`pdfscore_pipeline_gpu`で、`/opt/venv_pipeline/bin/python`を使う。
Issue #379で以前のSRコンテナー互換selectorを削除したため、重いサブプロセスの選択は
別の旧コンテナー/interpreter環境へフォールバックしなくなった。

## 主な成果物

アーキテクチャに関係する、実行ごとの代表的な成果物は次のとおり。

```text
<run_dir>/
  intermediate/detector_input_contract.json
  intermediate/dense_full_pipeline_inputs/inventory.json
  intermediate/dense_full_pipeline_route/**
  intermediate/<page>/barlines_corrected.json        # 実体化する場合
  intermediate/<page>/numbering_base.json
  intermediate/<page>/mmr_support.json
  intermediate/<page>/overrides_mmr.json
  intermediate/<page>/overrides_combined.json        # デバッグ用
  outputs/<page>/numbering_final.json
  outputs/<page>/numbering_overlay.png                # 有効な場合
  filters.json
  manifest.json
```

detectorのhybrid rootには`baseline/`、`current_support/`、`hybrid_results/`も含まれる。
current-supportのページサブツリーには、全ページSRフェーズに由来する、永続化済みの事前計算x4画像/provenanceが含まれる。
生成された実行出力は、限定的な保持方針で明示的に別の指定がない限り、Git管理対象外の`logs/`配下に置く。

## 将来の変更で守る不変条件

以下を暗黙のdownstream操作として導入してはならない。

- dense productionの各ページで、ページ単位のReal-ESRGANモデル初期化を行うこと。
- productionのReal-ESRGANの寿命と後続の重いHOMR/OMRフェーズを重ねること。
- detectorの合意判定だけを目的として、固定したStage-E HOMRをx4で実行すること。
- MMRの譜表ジオメトリだけを目的として、current-runtime HOMRを元ページで実行すること。
- トポロジーがPhase Aから乖離し得る、MMR専用の2回目の番号付け再構築を行うこと。

将来のステージが異なるHOMR producer/入力/プロファイルを実際に必要とする場合は、
そのproducerを名前付きのupstream成果物とし、機械可読provenanceと明示的な所有者を持たせる。
SRのスケジューリングを変える場合は、所有権/provenanceの明示を維持し、SRピクセルの一致だけに
頼らず、full-68のdownstream意味的契約を再検証する。

これらの所有権境界、ルート順序、正本となるジオメトリ、主要なプロセス/メモリ境界を変更する場合は、
本文書を更新してから、`docs/ai-workflow/GRAPHIFY.md`に従ってcommit済みのGraphify成果物を更新する必要がある。

現行実行環境の変更が、将来のengine境界から見える前提（1 jobの呼び出し/結果の意味、外部的に意味のある
final/review成果物、補正の意味、ライフサイクル/エラー/リソースの所有権、または呼び出し元から見える
分離の前提）も変える場合は、
[将来のサービスアーキテクチャ（英語・未翻訳）](FUTURE_SERVICE_ARCHITECTURE.md)も確認する。
長期的な境界が実質的に変わる場合にのみ同文書を更新し、詳細なパイプライン内部処理をコピーしない。

Issue #284のSRスケジューリング/実行環境最適化に先立つ、採択済みIssue #274の精度/性能マイルストーンは
`docs/TWO_HOMR_MILESTONE.md`を参照。
