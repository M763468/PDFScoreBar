# 第三者ライセンス義務と緩いライセンスの代替候補（#504 監査）

[#504](https://github.com/M763468/PDFScoreBar/issues/504) の調査記録。原文は日本語（正本）。英語版は未作成。
自リポジトリに付与するライセンスの検討は [リポジトリライセンスの選択肢（#505）](REPOSITORY_LICENSE_OPTIONS.md) に分離した。

> **法的助言ではない。** 本文書はライセンス文、上流の表示、現行ソースから読み取れる事実と一般的な解釈を整理したもの。
> 「未確定」と書いた項目は推測で埋めず、必要なら専門家確認を経て判断する。

## 0. 現行運用監査（2026-11-13 JST、`develop@6263350755f5`）

**この節が現在の監査の入口・提供判断の正本。** 以下の §1–§10 は PR #518 により採用された
`develop@3f7c8a632c6b`（2026-11-07）時点の監査スナップショットであり、歴史的証拠として保持する。
旧節の「現行」「必須」「ブロッカー」の記述が本節と矛盾する場合は本節を優先する。
本節は法律上の最終判断ではない。上流表示・依存定義・実際のイメージ同梱・提供方法を区別する。

### 0.0 実イメージ追跡の追加結果（2026-11-13）

調査対象は `develop@82853c5b1cab106fdc85e550944bcc6dcc9e0c0c`。実物は既存の
`pdfscore_issue522_candidate@sha256:71cbccf6d7f7bba3b96989f8043e1b6b991a3d90122bfe6afda0aae82d99610a`。
image label の source commit は `97b8bc3c4179ff3882d85c4b0c28941e5ce1be0f` であり、
最新developと同一commitではない。resolver は runtime environment contract の一致を報告し、アプリsourceは
bind mount する前提。元commitとの差分にはPDF修正等がある。イメージ内のsourceと最新develop全体が一致する証拠ではない。
`Dockerfile`、`pyproject.toml`、HOMR patch は両commit間で差分なし。

実物を読み取った証拠はローカル git 管理外 `logs/issue504/environment-audit/` に保持する。
`image-inspect.json`、`resolver.txt`、`source-diff.txt`、`python-sbom.json`（99 distributionsの版・
メタデータ・依存・VCS・検出された通知ファイルとハッシュ）、`dpkg.txt`（422行）、
`image-inventory.txt`（モデルhashとpip一覧）。メタデータとファイル名抽出は完全なライセンス判定や
配布用NOTICEではなく、個別レビュー・不足ファイルの確認が必要。例えばpypdfium2には `licenses/` 以下に
複数ライセンスがあり、単純なファイル名抽出では拾い切れない。
HOMR `direct_url.json` は `457e7c6518a10ba755db2e60883419e56c4d7369`、Real-ESRGANは
`a4abfb2979a7bbff3f69f58f58ae324608821e27`、BasicSRは1.4.2、PyMuPDFは1.26.4、
pypdfium2は5.15.1。Ultralytics distributionおよび `YOLOv8m_Measures.pt` は実イメージの検索で見つからなかった。
これは対象イメージの観測で、他の履歴イメージへの主張ではない。

実イメージのONNX SHA-256（ZIPのhashではない）:

| 資産 | SHA-256 |
| --- | --- |
| SegNet 308 FP16 | `60f495496cb41473c0521d0811d8f44b9d5cff892d287974a8aebb3eaee2fa83` |
| Transformer 426 encoder FP16 | `cd2da3ddec91af046d274506947f01da079c4ec5908ba0dd4c0c5985f780c82a` |
| Transformer 426 decoder FP16 | `58d55eebe22788ce98f0fc7730480a79c9f56534db064e8d32b1d5fe2579904a` |

上流ZIPの取得・公開digestとの照合、および展開後ONNXとイメージ内ONNXの独立比較は3件すべて一致（§0.0.1）。
上流の重みAGPL表明と、PrIMuS等の学習データ由来の法的不確実性は別の問題である。

HOMRの固定source、`docker/patch_homr_onnx_provider.py`、`src/homr_runtime/api_compat.py`、
Dockerfileと取得手順が対応ソース候補。BasicSR 1.4.2はDockerfileの `functional_tensor` →
`functional` のimport書換えがある。実イメージのHOMR encoder/decoderと固定上流、およびBasicSR 1.4.2上流と改変済みファイルの差分は `logs/issue504/environment-audit/source/` に保持。HOMRはprovider設定2か所、BasicSRはimport 1行。改変日と通知の完成、配布物に含む対応ソース全体の照合は提供前に必要。
対応ソースの法的な結合範囲は未確定であり、単にURLを並べるだけで充足したとは扱わない。
Ubuntuの各パッケージのライセンスと対応ソース、[Ubuntu商標方針](https://ubuntu.com/legal/intellectual-property-policy)、
[NVIDIAの各版・各部品の再配布条件](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html)を
配布候補ごとに確認する。現時点では一覧の取得であり、全パッケージの通知・対応ソース確認は未完了。

**状態:** 実環境の特定と根拠・未確定事項の分類は本節と §0.0.1 に記録。配布用NOTICE、対応ソースの実装、OS/NVIDIAの部品別条件の最終確認は配布前ゲートであり、本監査の完了と区別する。

### 0.0.1 今回の監査成果と配布前の引継ぎ

対象sourceは `develop@6263350755f5ddd6fe0371aa0fb061bf8b675077`、イメージのbuild sourceは
`97b8bc3c4179ff3882d85c4b0c28941e5ce1be0f`。`git diff --name-status 82853c5b 62633507` に依存・モデル・Dockerの変更はなく、
`git diff --name-status 97b8bc3c 62633507 -- Dockerfile pyproject.toml docker/patch_homr_onnx_provider.py models` も空。
resolverは環境契約の一致を示すが、source treeの同一性やイメージ自体に最新sourceが同梱されたことは示さない。
各配布候補のsource/image/実行時mountを固定する。

**Python 99件:** [全件の分類表](PYTHON_IMAGE_LICENSE_LEDGER.md) とローカル `logs/issue504/environment-audit/python-license-ledger.json` を参照。
Verified 3（HOMR、BasicSR、Real-ESRGANの最上位コードライセンスと記録された改変に限定）、Metadata only 94、
Unresolved 1（`cuda-toolkit==13.0.3.0` は宣言・同梱ライセンス未特定）、Not applicable 1（first-party `pdfscore-pipeline`）。
Metadata onlyの全94件は表に列挙し、いずれも最終配布物の条件確認は未了。特に `flatbuffers`、`rapidocr-onnxruntime`、
`tensorboard-data-server`、`types-Pillow` はdistribution管理ファイル中にLICENSE/NOTICEが見つからず、上流・配布アーカイブを照合する。
`pypdfium2` には多数の `licenses/` が実在し、同梱依存を別途評価する。分類は通知の自動作成・権利許諾ではない。
PyMuPDFはAGPL/商用二重表示を確認したが、wheel内の全構成物の条件確認を完了したわけではないためMetadata only。

**Ubuntu / NVIDIA:** `dpkg-query` 422行中、各packageに対応するcopyrightファイルを419件で検出、
`cuda-compat-12-3`、`cuda-keyring`、`cuda-libraries-12-3` の3件は通常の位置で未検出。
copyright全文の単純検索による候補はGPL 313、LGPL 196、AGPL 2、MPL 12、Apache 52（重複あり。文章・引用を含むためライセンス確定数ではない）。
`os-license-ledger.json` にbinary/source版と根拠pathを保持。配布前に候補と3例外の実際のソース・ライセンスを検証する。
OS内CUDA 12.3、cuDNN 9.0.0.312、NCCL 2.20.3 と、Python側のNVIDIA関連16 distribution（cuDNN 9.24を含む）は異なる層。
15件はNVIDIA独自条件を宣言、`nvidia-nvtx` はApache-2.0を宣言。各版・パス・ライセンス所在は `nvidia-inventory.txt` とPython台帳。
CUDA 12.3.2については[該当版EULA](https://docs.nvidia.com/cuda/archive/12.3.2/eula/index.html)を参照し、
wheel/cuDNNその他の版は同梱文書と対象製品の条件を別に照合する。(b)ではredistributableの範囲、通知・条件、Ubuntu各sourceと[商標](https://ubuntu.com/legal/intellectual-property-policy)を確認。(c)ではimageを渡さない場合の配布と利用条件を分ける。

**HOMRの独立照合:** `release.json` の上流公開ZIP SHA-256と、取得した3 ZIPの実測SHA-256はすべて一致。
`homr-release-validation.txt` にはZIP名・ZIP hash・各1ファイルの展開後ONNX hashを保存し、§0.0のイメージ内hashと3件とも一致。
この一致はモデルの来歴確認であり、学習データ由来の権利問題を解決しない。

**対応ソース手順（設計）:**
1. 配布対象imageのimmutable ID、label、source commit/fingerprintとbind mountされたsource版を固定し、この監査のIDと比較。再ビルド・依存変化があれば再採取する。
2. HOMR `457e7c6518a10ba755db2e60883419e56c4d7369`、BasicSR 1.4.2の上流source・LICENSEを取得し、`source/homr.patch` / `source/basicsr.patch` とイメージ内ファイルを照合。HOMRのencoder/decoderのHEURISTIC化、BasicSRのimport変更を記録。
3. `Dockerfile`、`pyproject.toml`、`docker/patch_homr_onnx_provider.py`、`src/homr_runtime/api_compat.py`、モデル取得処理、依存・build/installに必要なファイルと、該当ライセンス・NOTICEを対応ソース候補に含める。HOMR patch現行形の履歴は `437dffeec2a3`（2026-09-20）、BasicSR import変更導入は `8cf075692310`（2026-04-19）。これはgit記録の日付で、実際の個別image build日時とは区別する。
4. 改変表示と受領者／ネットワーク利用者への提供手段を準備し、実行版と提供sourceの一致を確認。結合著作物の厳密な範囲は法的に未確定。

**A/B/C:** A（現行source・対象imageの依存、主要モデル、改変、提供形態・未確定事項の調査と再検証証拠）は今回の監査範囲を完了。
B（最終配布物の全LICENSE/NOTICEと対応ソース提供の実装、上記未確認条件、HOMRデータ由来の判断、#505の正式LICENSE、fingerprintと方式ごとのGo/No-go）は
[#508](https://github.com/M763468/PDFScoreBar/issues/508) と #505 の正式リリース・試用判断前に完了させる。
(b) の配布は全NOTICE、ソース、NVIDIA条件と重み権利の確認まで保留。(c) は対象AGPL版のsource案内、first-party権限とモデル権利・運用条件の確認まで保留。
(a) は内部実験のまま継続し、第三者提供の許可とはしない。C（PyMuPDFの出力/補正と入力描画の別々の代替評価、HOMRや重みの長期対策）は
#504で継続管理し、着手可能な作業単位が成立した時点で重複を確認してfocused Issue化する。候補の回帰契約は §0.6。

証拠のSHA-256: Python台帳 `9585ec643a1a201bba63577014958a36f5dc0a31f52472887a8f3ab0dae77a06`、
OS台帳 `b751da8fd478abc9d8c01a50f68a1b2aea4f84cc81459394e63adaa9de84b0fa`、
モデル照合 `c78d496dfabfa403558c131195d0b5c0477ee3968b6ac6f68429fff9ba46b409`。
ローカル証拠は `logs/issue504/environment-audit/`。生成スクリプトと実行方法、未解決の範囲も同ディレクトリに保持。

### 0.1 対象と確定した変更

- 基点: `develop@52da54ec7a8fe7e65434abc8bfcd23306f0e4cee`
  （[PR #523](https://github.com/M763468/PDFScoreBar/pull/523)、2026-11-11 JST マージ）。
  `main@d8c54148a275dbd74411f2012f44da92b6fbe74c` は別のリリースツリーで、まだ
  `ultralytics==8.3.239` と `models/omr_dln/manifest.json` を持つ。**`develop` の監査結果を
  `main`/既配布物へ自動的に適用しない。**
- `develop` の production は OMR-DLN 重み `YOLOv8m_Measures.pt` の取得・import・mount・load・推論を
  行わず、Ultralytics も直接依存から削除された。検出は
  `dense_full_pipeline` / `maintained_original` と x4 HOMR 五線片支持で実行する。
  廃止した OMR の設定は未知キーとして拒否する。旧 OMR 関連コード・重みの法的な調査は歴史的証拠に
  留め、**現在の配布ブロッカーや新規再学習タスクとして再掲しない**。
- [#519](https://github.com/M763468/PDFScoreBar/issues/519) の単純な no-OMR ablation は
  TP3559 / FP0 / FN8 で旧ゲート FAIL のまま保持。採用された #522 / #523 の
  **retained-producer Full68 replay** は TP3560 / FP0 / FN7、物理小節3287、
  MMR 171/3/3/0。OMR 重みなしの **fresh 1ページ E2E** は 85/85 で成功。
  **fresh Full68 の再推論を実施した結果ではない。**
- 2026-11-11時点の調査は source/manifest/上流表示の読み取りであり、当時の最新イメージの
  `importlib.metadata` 全件再取得・GPU実行・コンテナ再ビルドは **未実施**。追加実測は §0.0。
  §1 にある「102 distribution」は旧イメージの記録であり、今回の最新SBOMではない。

### 0.2 現行の主要コード依存・改変・通知

| 対象 | `develop` の固定対象/取得経路 | 権利・結合上の整理 | 必要な継続作業 |
| --- | --- | --- | --- |
| **HOMR** | `Dockerfile` の git commit `457e7c6518a10ba755db2e60883419e56c4d7369` | [固定版の AGPL-3.0](https://github.com/liebharc/homr/blob/457e7c6518a10ba755db2e60883419e56c4d7369/LICENSE)。engine が同一プロセスで利用。`docker/patch_homr_onnx_provider.py` のインストール済みソース書換え、および `src/homr_runtime/api_compat.py` の実行時互換処理がある | 改変箇所・日付・提供すべき差分、ビルド/モデル初期化手順と対応ソース範囲を確定 |
| **PyMuPDF / MuPDF** | `PyMuPDF==1.26.4`（直接固定） | [AGPL-3.0 と商用ライセンスの二重体系](https://pymupdf.io/licensing)。PDF描画・入力検査・最終PDF・番号レイヤ・補正/再開に使用。改変は旧監査時点でなし | 出力/補正と入力描画を分け、結合範囲・通知・代替評価を管理 |
| **Real-ESRGAN** | git `a4abfb2979a7bbff3f69f58f58ae324608821e27` | BSD-3-Clause、SR worker で使用 | ソースのBSD表示、リリース重みの個別条件を区別 |
| **BasicSR** | Real-ESRGAN 経由、旧画像では `1.4.2` | Apache-2.0。`Dockerfile` が `basicsr/data/degradations.py` の import 1行を変更 | **改変通知**と該当ソース/patch、最新版の解決版を記録 |
| **RapidOCR / ONNX Runtime GPU** | `rapidocr-onnxruntime==1.4.4` / `onnxruntime-gpu==1.24.4` | RapidOCR: Apache-2.0、ONNX Runtime: MIT。OCR/推論経路 | 同梱 ONNX 重み・依存の NOTICE とモデル別権利を確認 |
| **PyTorch / torchvision** | `torch==2.14.0` / `torchvision==0.29.0` を直接固定 | BSD系。Ultralytics削除による間接解決差を抑制 | CUDA/triton等を含む実インストール版・NOTICE をSBOMで確認 |
| **OpenCV / NumPy等** | `pyproject.toml` の直接固定（`psutil==7.2.2` を含む） | 主として permissive。対象imageの間接依存一覧は §0.0.1 | 新しい固定イメージでライセンス・配布ファイルを再照合 |
| **CUDA / Ubuntu** | `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04` | NVIDIA独自条件、OSのGPL/LGPL等を含む。Docker image を渡す場合は別の配布義務が生じ得る | イメージ再配布か利用者自身のビルドかを明示して扱う |
| **OMR-DLN / Ultralytics** | `develop` production から除去 | **現在は不使用**。§2/§6 の旧監査記載は #523 前の証拠 | 既配布 `main` と履歴再現環境のみ別管理。置換・再学習は不要 |

`pyproject.toml` の直接依存と `Dockerfile` で導入するVCS依存は固定されているが、
`uv.lock` による完全な間接依存固定はない。旧イメージでの
`pypdfium2==5.13.0` 等の実在は**最新ビルドのインストール保証ではない**。
必ず「source定義」「実際のsite-packages」「image中の配布・重み」を分ける。

### 0.3 モデル重み・学習データの権利を分離する

| 資産 | 現行の導入/配布 | 2026-11-11時点で言えること・未確定点 |
| --- | --- | --- |
| **HOMR segmentation / transformer / ONNX** | `python -m homr.main --init --gpu force` でイメージに取得 | 上流の [LICENSE_FAQ.md](https://github.com/liebharc/homr/blob/main/LICENSE_FAQ.md)（2026年10月公開）および [作者回答](https://github.com/liebharc/homr/issues/187#issuecomment-6170272605) は**重みもAGPLで公開する意向**を明示。§3の「重みの個別ライセンス表示なし」だけでは現状を説明しきれない。ただし FAQ は固定コードcommitより後の説明であり、実際のrelease assetとimage内hashは §0.0.1 で照合した。学習データ由来の法的判断は残る |
| HOMR segmentation の学習データ | DeepScoresV2 | 上流FAQによれば CC BY 4.0。重みと学習データを同一の権利物と推定しない |
| HOMR transformer の学習データ | OpenScore Lieder / StringQuartets、GrandStaff、Camera-PrIMuS 等 | 上流FAQによれば OpenScore はCC0、GrandStaffは取得元に明示表示なし（HF複製はMIT）、**PrIMuSは元配布先に表示なし、HF複製はCC BY-NC 4.0**。全公開Transformer checkpointにPrIMuSが含まれるとの上流説明。さらに世代によってPDMX等の混入が異なる。**非商用条件が重みへ波及するかは上流も法的に未確定と認める**。商用配布/提供を自動許諾されたと判断しない |
| Real-ESRGAN x2/x4 | `Dockerfile` で上流releaseから取得、SHA-256照合後にimage同梱 | リポジトリのBSD-3-Clauseだけで各checkpointの来歴・再配布条件を確定しない |
| RapidOCRモデル | 関連wheel/初期化資産 | コード・モデルそれぞれの表示と同梱物を次回SBOMで確認 |
| Barline CNN | `models/barline_cnn/manifest.json` の固定GitHub release | first-party学習。重みの付与条件と初期化元を #505 と区別して確認 |
| MMR | `models/mmr/mmr_classifier_best.pth` をgit管理 | first-party学習、ImageNet事前学習を使った履歴あり。出典・派生条件を確認しないままコードのLICENSEを適用しない |
| 評価GT / fixture / 利用者PDF | 権利・取得元が異なる | 元の楽譜著作物、座標ラベル、合成fixture、ユーザーPDFを一括で再許諾しない。#505の権利分類を参照 |
| **OMR-DLN重み** | 現行の取得・配置・推論なし | 旧 §3/§6 は歴史的研究の証拠。production の重み・クラウド許諾ブロッカーから除外 |

**固定HOMRソースから特定できるGPU初期化資産（2026-11-11上流確認）:**
`Dockerfile` は `homr.main --init --gpu force` を実行する。
HOMR固定commitの
[segmentation/config.py](https://github.com/liebharc/homr/blob/457e7c6518a10ba755db2e60883419e56c4d7369/homr/segmentation/config.py)、
[transformer/configs.py](https://github.com/liebharc/homr/blob/457e7c6518a10ba755db2e60883419e56c4d7369/homr/transformer/configs.py)、
[main.py](https://github.com/liebharc/homr/blob/457e7c6518a10ba755db2e60883419e56c4d7369/homr/main.py)
から、GPU経路で選ぶ `onnx_checkpoints` release のZIP名を次のとおり特定できる。

| 用途 | 上流release ZIP（GPU FP16） | 上流GitHub Releaseが表示するZIPのSHA-256 |
| --- | --- | --- |
| SegNet | `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f_fp16.zip` | `8d05a37fe76829673bc9def0a7caf168e5860aa4d1a8f7ac1b6123aa69fe3d82` |
| Transformer encoder | `encoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644_fp16.zip` | `1390295d921a5e646a6405d23ca6a922a7dcefa97cb425317be84de5195fd49c` |
| Transformer decoder | `decoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644_fp16.zip` | `0d21e347661c147b073a35c880cfc52c1ae71d40a990e5964e3736a595657ce8` |

典拠: [HOMR `onnx_checkpoints` release](https://github.com/liebharc/homr/releases/tag/onnx_checkpoints)
の資産メタデータ（2026-11-11確認）。**これはGitHubが表示する配布ZIPのdigestであって、
当方がダウンロードして検算した値でも、解凍後のONNX単体のhashでもない。**
実イメージのONNX hashとsource fingerprintは §0.0。上流ZIPとのbytes照合は §0.0.1。
また、上流FAQの歴史的なcheckpoint 396の例を現行の **426** と混同せず、
426の正確な学習元は上流FAQ/Training資料との個別照合を残す。

上流FAQの「重みはAGPL」という記述は、**学習データを含むあらゆる権利の保証ではない**。
とくに商用化時は実際のcheckpoint/学習データと利用形態を特定したうえで、必要なら法律専門家に確認する。
作者への新規問い合わせは本Issueの現行方針では行わない。

### 0.4 現行の結合と提供形態（要件の判断表）

engine（`src/pipeline`、`src/homr_runtime`）はHOMRを直接利用し、PDF処理・補正/再開経路には
PyMuPDF が入る。`docker/review_relay.py` は `tools.review_correction.server.create_server` を
同一プロセスで読み込むため、単なる独立ネットワークプロキシとしてAGPL検討範囲から除外しない。
ブラウザ側HTML/JSとランチャー、将来の独立Web入口は結合/著作物の境界を個別に検討する。
**単に別リポジトリ・別プロセスとすることだけで独立とは結論しない。**

**PyMuPDFの直接importを現行sourceで確認した境界:**
- 入力検査・描画: `src/pdf_to_images.py` と `src/pipeline/engine_input_safety.py` が `fitz.open`、`Matrix`、`get_pixmap` を使用。
- 新規の通常PDF出力: `src/pipeline/review/final_output.py` が `fitz.open`、`new_page`、`insert_image` を使用。
- 既存PDFへの番号レイヤ・戻し: `src/pipeline/review/number_layer.py` が
  `wrap_contents`、`insert_text`、xref stream/key操作、注釈・ページ回転・cropbox検証を使用。
- 補正の再開・PDF同一性: `tools/review_correction/resume.py` が `fitz.open`、`annots`、`set_cropbox`、`get_pixmap` を使用。

したがって `pikepdf`/`pypdf` で番号レイヤの低水準操作を置換する課題と、
`pypdfium2` で描画・入力検査を置換する課題は、回帰契約も作業費も異なる。


以下は公開条文に基づく**遵守計画上の分類**であり、個別の結合著作物の法的判断を確定しない。
典拠: [AGPLv3 §1/§4–6/§13](https://www.gnu.org/licenses/agpl-3.0.html)、
[GNU FAQ](https://www.gnu.org/licenses/gpl-faq.html)、
[PyMuPDF licensing](https://pymupdf.io/licensing)、
[HOMR FAQ](https://github.com/liebharc/homr/blob/main/LICENSE_FAQ.md)。

| 項目 | (a) 内部実験 | (b) 配布（実行物/フォルダ/image） | (c) 招待制GPU/Web |
| --- | --- | --- | --- |
| AGPLの対応ソース・著作権/ライセンス通知 | 通常 **対象外**（第三者への複製物提供・遠隔ユーザーなし） | **必須**（AGPL対象のobject codeを受領者へ渡す場合）。改変版と構成・ビルド手順等を含む対応ソースを実行物と整合させる | **条件付き必須**（改変AGPL版にネットワーク経由で利用者が対話する場合、§13の無償ソース取得機会を提示）。ユーザーとの対話経路と対象ソース範囲を確定 |
| 自前のfirst-partyコードの利用許諾 | 内部開発は継続 | **未整備の提供ゲート**。結合物に必要な互換許諾を満たす方法を #505 のリリース判断に接続 | **未整備の提供ゲート**。AGPL結合の扱いとSource案内を具体化。独立Web入口全体が自動的にAGPLとは限らない |
| HOMR のpatch・互換処理 | 使用する版を保持 | **必須/要確認**: 改変表示、日付、取得元、差分/ビルド手順を含む対応ソース | **条件付き必須**: 実際の改変・ネットワーク提供と結合範囲で判定 |
| PyMuPDF のライセンス | 利用条件を確認 | **必須**: AGPL経路を取る場合は対象物の対応ソース・通知等、または必要な商用許諾 | **条件付き/要確認**: AGPL結合・ネットワーク提供の実態を評価し、必要な場合Source案内 |
| **HOMR / 他モデル重み** | 学習元などの不確実性は残る | **未確定**: image同梱checkpointと学習データ由来の条件を要確認 | **未確定**: 同じ重みを第三者サービスに使う権利はAGPL表記だけでは確定しない |
| Ubuntu/GPL・NVIDIA等 | 自身の環境で使用 | **条件付き必須**: ビルド済みimage等を渡す場合、個別の再配布・ソース/通知条件を確認 | **条件付き**: imageを利用者に渡さない場合は配布義務と分けるが、運用・利用条件は別途確認 |
| OMR-DLN/Ultralytics | 現行runtimeから除去 | **対象外**（新しい`develop` runtimeの配布） | **対象外**（新しい`develop` runtimeの実行） |

「試用者が少人数だから免除」「公開GitHubならすべて満たせる」「全周辺サービスのソースが必須」
のいずれとも断定しない。実際の対象版、提供相手、object codeの有無、遠隔利用、改変の有無を
案件ごとに記録する。受領者自身がソースからビルドする方式は、**当方がobject codeを渡す方式とは
区別**するが、それだけでfirst-partyの許諾問題や必要な通知を解決したことにはしない。

### 0.5 解消済み事項、残るブロッカーと #505 / #508 への引継ぎ

**解消済み（`develop`限定）:** OMR-DLN の出所不明な配布重みを
取得/配置する必要と、その推論に伴うUltralytics依存。#519/#522はClosed。
#523で Full68 replay・下流・補正・fresh 1ページの検証結果は確定した。
PDF出力4ページの配置問題は [#526](https://github.com/M763468/PDFScoreBar/pull/526) で修正され #524 は Closed。#523 の当時の失敗は履歴として保持する。

**未解消:** HOMRの対応ソース/改変通知、HOMR重み（特にPrIMuS）の権利・checkpoint同定、
PyMuPDFのAGPL結合範囲、第三者NOTICE、依存SBOMの不足通知の点検、
配布時のUbuntu/NVIDIA条件、実行版と一致するSource配布手順。

**#505の方針は変更しない。** 現時点で `develop` にfirst-partyの
`LICENSE`/`NOTICE`/`REUSE.toml`/`pyproject.toml license` を追加することはしない。
AGPL-3.0-or-laterをfirst-partyの第一候補とする意思は維持し、OMR除去を含む必要な整備と
`main` への昇格を済ませた**正式リリース時**に、対象ツリーと整合したライセンス付与を行う。
[#505](https://github.com/M763468/PDFScoreBar/issues/505) のオーナー決定・focusedなrelease PRとは分離する。
**first-party LICENSEがまだないことは、第三者ライセンス義務を消さない。**

**#508への試用ゲート:** 実際に使用するbranch/image/方式を指定し、上表 (b)/(c) の該当項目に
許諾・通知・Source案内を対応させる。`main` と現在の配布物がOMR依存を持つ間は
「OMR不要」としてGo判定しない。試用者に渡す版がどれかを固定する。

### 0.6 permissive代替の再優先順位（本Issueは評価計画まで）

1. **PyMuPDFの最終PDF・番号レイヤ・補正/再開:** `pikepdf`/`pypdf` 等と機能・低水準PDF操作を比較。
   AGPL結合面積を減らせる見込みがある一方、原注釈・所有レイヤ・undo/resume・フォント/幾何が難所。
   [#526](https://github.com/M763468/PDFScoreBar/pull/526) の修正後を基準とし、旧renderer失敗を候補回帰と誤分類しない。
   対象版・基準renderer・入力・出力契約・rollbackを固定して別Issueで評価する。
2. **PyMuPDFの入力レンダリング:** `pypdfium2`/PDFiumを候補とするが、レンダリング差は
   認識器入力も変える。出力経路置換とは分離し、Full68 GT・小節番号・PDF geometry・性能を検証する。
   対象イメージでは5.15.1を確認したが、再ビルド後の存在・版は再確認する。
3. **HOMR:** 中核依存。現時点で精度同等のpermissiveな既存代替の採用根拠なし。
   一律置換は目的化せず、法的な遵守策と重みの不確実性の解消を先行する。
4. **OMR-DLN代替モデル/独立再学習:** #522/#523で不要と判断済み。
   新たな性能・精度・権利問題の根拠がない限り再開しない。§7の旧候補は歴史的計画。

各置換のproduction化は本Issueの範囲外。必要なときだけ focused Issue/PR に切り出し、
合意済みの検出/番号/補正/再開/PDF幾何/性能ゲートを変更せず、失敗も保持する。

### 0.7 配布前と長期改善の終了条件

- #508の具体的な配布候補ごとに、§0.0.1のPython/OS台帳と実物を照合し、未確認ライセンス・通知・NVIDIA条件・対応ソースの提供を解決する。再ビルド時は新しいimageで再採取する。
- #505で正式リリース対象のfirst-partyライセンス・権利境界と第三者通知を確認する。HOMRの学習データ・重みに関する未確定事項は提供形態ごとに判断する。
- #504で出力/補正と入力描画を別々に評価し、精度・PDF幾何・注釈・履歴・性能の契約とrollbackを固定してから、必要に応じ重複のないfocused Issueに分ける。

---

## 1. 位置付けと証拠

- 調査日: 2026-11-07。対象: `develop@3f7c8a632c6b`（PR #516 統合後）の source、`pyproject.toml`、`Dockerfile`、
  `models/*/manifest.json`、[配布 manifest](../MINIMAL_MAINLINE_SURFACE.json)。
- 実インストール状況: ローカル既存イメージ `sha256:5c5979a26f4b…`（label `pdfscore.runtime.source_commit=9ccd57fb`）。
  `9ccd57fb..3f7c8a63` で `pyproject.toml`、`Dockerfile`、`docker/patch_homr_onnx_provider.py`、`models/` に差分なし。
  イメージ内の全 102 distribution の名称・版・ライセンスメタデータを `importlib.metadata` で抽出し、
  git 管理外の `logs/issue504/license-audit/` に保存した（`image_5c5979a26f4b_distributions.json`、`image_identity.txt`）。
- 上流のライセンス表示は GitHub API（`repos/<owner>/<repo>` の `license`、ファイル一覧）と Zenodo API で 2026-11-07 に取得した。
- パッケージメタデータのライセンス欄は自己申告であり、同梱ファイル全体のライセンスを保証しない。重要部品は上流の LICENSE で確認した。
- **注意:** Docker build は `uv.lock` を使わず `uv pip install` で間接依存を解決する。直接依存は固定されているが、
  間接依存の版（とライセンス）は再ビルドで変わり得る。この台帳は上記イメージに対する snapshot である。

## 2. 権利台帳: コード

| 部品 | 固定版 / 取得元 | ライセンス（証拠） | PDFScoreBar での使い方 | 改変 |
| --- | --- | --- | --- | --- |
| HOMR | git `457e7c6518a10ba755db2e60883419e56c4d7369` | AGPL-3.0（[固定 commit の LICENSE](https://github.com/liebharc/homr/blob/457e7c6518a10ba755db2e60883419e56c4d7369/LICENSE)） | `src/homr_runtime/*`、`src/pipeline/detection/*homr*`、`hybrid.py` 等が同一プロセスで import | **あり**: build 時に `docker/patch_homr_onnx_provider.py` が installed source を書換え。実行時に `src/homr_runtime/api_compat.py` が HOMR の関数束縛を差し替える |
| Ultralytics | PyPI `ultralytics==8.3.239`（間接: `ultralytics-thop==2.2.2`） | AGPL-3.0（[上流](https://github.com/ultralytics/ultralytics)、パッケージメタデータ）。商用 Enterprise License が別途存在（[licensing](https://www.ultralytics.com/license)） | `src/pipeline/detection/omr_dln_worker.py` が同一プロセスで import。worker は本体から別プロセスで起動される | なし |
| PyMuPDF（MuPDF 同梱） | PyPI `PyMuPDF==1.26.4` | AGPL-3.0 または Artifex 商用の二重ライセンス（[licensing](https://pymupdf.io/licensing)、メタデータ） | engine の PDF 描画・入力検査・最終 PDF 出力・番号レイヤ、補正 GUI の再開処理（`tools/review_correction/resume.py`）が同一プロセスで import | なし |
| Real-ESRGAN | git `a4abfb2979a7bbff3f69f58f58ae324608821e27` | BSD-3-Clause（GitHub API） | SR worker が import | なし |
| BasicSR | PyPI `basicsr==1.4.2`（Real-ESRGAN 経由） | Apache-2.0（GitHub API） | Real-ESRGAN 経由 | **あり**: build 時に `basicsr/data/degradations.py` の import を 1 行置換 |
| GFPGAN / facexlib | `gfpgan==1.3.8`、`facexlib==0.3.0`（間接） | Apache-2.0（メタデータ） | Real-ESRGAN の依存として導入のみ | なし |
| RapidOCR | `rapidocr-onnxruntime==1.4.4`（間接 `rapidocr==3.9.2`） | Apache-2.0（GitHub API、メタデータ） | MMR の OCR provider | なし |
| ONNX Runtime GPU | `onnxruntime-gpu==1.24.4` | MIT | HOMR / RapidOCR の推論 | なし |
| PyTorch / torchvision / triton | `torch==2.14.0`、`torchvision==0.29.0`、`triton==3.8.0`（間接） | BSD 系・Apache-2.0 等の複合 / BSD-3-Clause / MIT（メタデータ） | CNN、MMR、SR、Ultralytics | なし |
| OpenCV、NumPy、SciPy、scikit-learn、Pillow、matplotlib、coloredlogs | `pyproject.toml` の固定版 | Apache-2.0 / BSD-3-Clause 系 / BSD-3-Clause / BSD-3-Clause / MIT-CMU / PSF 系 / MIT | engine 全般 | なし |
| pypdfium2（PDFium 同梱） | `pypdfium2==5.13.0`（間接依存として既に導入済み） | Apache-2.0 / BSD-3-Clause と同梱依存のライセンス（[licensing](https://github.com/pypdfium2-team/pypdfium2#licensing)、`LICENSES/` に Apache-2.0、BSD-3-Clause、CC-BY-4.0、LGPL-3.0-or-later、MIT、MPL-2.0 等） | 本体は直接使っていない | なし |
| 弱いコピーレフト | `certifi`（MPL-2.0）、`tqdm`（MPL-2.0 AND MIT）、`lmdb`（OLDAP-2.8） | メタデータ | 間接依存 | なし（ファイル単位の義務は改変時のみ。配布時は通知を同梱） |
| NVIDIA CUDA | base image `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`、`nvidia-*` wheel 14 件 | NVIDIA 独自ライセンス（`LicenseRef-NVIDIA-Proprietary` 等） | GPU 実行 | なし |
| Ubuntu 22.04 系パッケージ | base image と `apt-get install`（`build-essential`、`python3.12`、`libgl1` 等） | GPL / LGPL を含む各 Debian/Ubuntu パッケージのライセンス | 実行環境、torch.compile 用コンパイラ | なし |

上記以外に、Python メタデータ上で GPL / AGPL / LGPL を宣言する distribution はイメージ内に見つからなかった
（ライセンス欄が空または不明瞭: `cuda-toolkit`、`Jinja2`（分類子は BSD）、`omegaconf`（分類子は BSD）、自パッケージ `pdfscore-pipeline`）。
補正 GUI のブラウザ側（`tools/review_correction/*.js` / `index.html`）は外部 CDN やライブラリを読み込まない first-party 資産である。

## 3. 権利台帳: モデル重みとデータ

| 対象 | 取得元 / 配置 | 確認できた権利表示 | 状態 |
| --- | --- | --- | --- |
| HOMR ONNX 重み（segnet、transformer encoder/decoder） | HOMR の GitHub release `onnx_checkpoints` を build 時の `homr.main --init` が取得し、**イメージに同梱** | release 本文は "Pretrained onnx models for homr" のみで個別ライセンス表示なし。学習データは PrIMuS、GrandStaff、Lieder、PDMX 等（上流 `Training.md`） | **未確定**: コードの AGPL-3.0 が release 資産の重みにも及ぶかは明示がない（コードと重みを同一視しない）。学習データ各々の条件は未検証 |
| OMR-DLN `YOLOv8m_Measures.pt` | 上流 README が案内する Google Drive。**同梱せず**、利用者が取得し `models/omr_dln/manifest.json` の SHA-256 で検証して import | 上流 [dmgonzalez8/OMR](https://github.com/dmgonzalez8/OMR) は LICENSE ファイルなし（GitHub API の license も null）。Ultralytics の事前学習 YOLOv8m から DeepScoresV2（Zenodo 4012193、**CC BY 4.0**）で学習と README に記載 | **未許諾**: 利用・再配布の明示許諾なし。§6 参照 |
| Real-ESRGAN `RealESRGAN_x4plus.pth` / `x2plus.pth` | Real-ESRGAN GitHub release v0.1.0 / v0.2.1。SHA-256 固定で**イメージに同梱** | リポジトリは BSD-3-Clause。重み個別の表示は未確認 | 条件付き: BSD-3 の通知で足りる見込み。学習データの条件は未検証 |
| RapidOCR 同梱 ONNX モデル | wheel 内 | Apache-2.0（PaddleOCR 由来） | 通知の同梱で足りる見込み |
| barline CNN `cnn_classifier_epoch_9.pth` | 本リポジトリの GitHub release（`models/barline_cnn/manifest.json`）。EfficientNet-B0 | first-party 学習。初期化元（事前学習重みの有無）は本監査で未確認 | #505 で扱う |
| MMR 分類器 `models/mmr/mmr_classifier_best.pth` | **git 管理・配布 manifest 選択対象** | first-party 学習。`tools/mmr_training/train_mmr_classifier.py` は torchvision `ResNet18_Weights.IMAGENET1K_V1` から初期化 | #505 で扱う。ImageNet 由来の事前学習重みの条件は専門家確認候補 |
| 評価 GT `data/evaluation2/annotations/**` | git 管理（座標 JSON）。楽譜画像・PDF は git 管理外 | first-party のラベル。対象作品には著作権保護期間内の作品（例: Shostakovich）を含む | 楽譜画像・PDF を配布しない。ラベルの扱いは #505 |
| テスト fixture 画像 `tests/fixtures/system_grouping/*.png` | git 管理（#218 で追加） | 出典記録なし | #505 で出典確認 |

## 4. 結合境界（現行の import / プロセス / 通信経路）

| 領域 | AGPL 部品との関係 | 観察 |
| --- | --- | --- |
| engine（`src/pipeline`、`src/homr_runtime`、`docker/distribution_job.py`） | HOMR と PyMuPDF を同一 Python プロセスで import し、HOMR の内部関数を実行時に差し替える | FSF の一般的解釈では AGPL 部品と一体の結合著作物とみなされる可能性が高い |
| OMR-DLN worker | 本体とは別プロセスで、JSON / ファイルの受け渡し。ただし worker 自体は PDFScoreBar のコードで Ultralytics を import する | worker と Ultralytics は一体。本体と worker の関係は、引数・データの受け渡し方やモジュール共有から判断が分かれる |
| 補正 GUI サーバ（`tools/review_correction/server.py` 等） | `resume.py` と `src.pipeline.review.*` 経由で PyMuPDF を同一プロセスで import | engine と同じく結合著作物とみなされる可能性が高い |
| 補正 GUI ブラウザ資産 | AGPL 部品を含まない | ブラウザへ送られる JS/HTML は first-party のみ |
| ローカルランチャー（`docker/distribution.py`） | ランチャー自身は AGPL 部品を import せず、`docker` CLI で起動する | first-party の `docker/runtime_contract.py`、`src/common/model_artifacts.py` を import。起動先は別途分類する |
| Docker Desktop レビューデータ転送（`docker/review_relay.py`） | `main()` が `tools.review_correction.server.create_server` を import し、同一プロセス内で補正 GUI サーバを実行。`resume.py` 経由で PyMuPDF (`fitz`) に到達 | **補正 GUI サーバ側の AGPL 結合境界に含む**（PR #518 Codex review 指摘を反映） |
| 将来の Web 入口（#449、別リポジトリ想定） | 現存しない | ジョブ投入のみの独立サービスにできる設計余地はあるが、別プロセス・別リポジトリという形式だけで独立と断定しない |

結論: engine、OMR-DLN worker、補正 GUI サーバ（Docker Desktop 経路の `docker/review_relay.py` を含む）は、プロセス分割の有無にかかわらず AGPL 部品と一体の作品として扱うのが安全側の前提である。
「別プロセスだから AGPL の対象外」という前提で提供方法を設計しない。

## 5. 提供形態ごとの義務

分類: **必須** / **条件付き**（条件を併記）/ **対象外** / **未確定**（法的または事実関係が未確定）。

- (a) 開発者自身の内部実験（第三者へ複製物を渡さず、第三者にネットワーク利用させない）
- (b) 1〜2 人の試用者へ実行ファイル・フォルダ・イメージ・インストール手順を提供
- (c) 招待制のリモート GPU / Web 利用（試用者は複製物を受け取らず、ネットワーク経由で操作）

| 義務 | 対象コード範囲 | (a) | (b) | (c) |
| --- | --- | --- | --- | --- |
| AGPL 部品の Corresponding Source 提供（AGPL §6） | HOMR（改変版）、Ultralytics、PyMuPDF/MuPDF | 対象外（conveying なし） | **必須**: イメージやポータブル版など AGPL 部品の object code を渡す場合。**条件付き**: 現行の Docker 手順のように受領者が上流から取得・ビルドし、こちらは自リポジトリの source と build script だけを渡す場合は、AGPL 部品自体の conveying には当たらないと読める余地がある（ただし改変 script は受領者の手元に既にある） | HOMR は**必須**（改変版をネットワーク越しに操作させるため §13 が適用。後述の first-party 部分も含む）。Ultralytics / PyMuPDF は自身を改変していないため単独では §13 の発動条件を満たさないが、結合著作物全体を「改変版」とみなす解釈では対象になる: **未確定** |
| 結合著作物として first-party コードを AGPL 互換の条件で許諾し、source を提供（AGPL §5(c)、§10） | engine、OMR-DLN worker、補正 GUI サーバ、build script | 対象外 | **必須**（結合した object code を渡す場合）。現状はリポジトリに LICENSE がなく、受領者に AGPL 以上の制限を課していると読まれ得る: **#505 の決定が前提のブロッカー** | **必須**として扱うのが安全（§13 の対応ソースに結合部分が含まれる解釈が一般的）。厳密な範囲は**未確定** |
| 改変の明示（AGPL §5(a)、Apache-2.0 §4(b)） | HOMR の build 時 patch と実行時差し替え、BasicSR の 1 行 patch | 対象外 | **必須**（改変版を渡す場合）。`docker/patch_homr_onnx_provider.py` と `Dockerfile` が改変内容そのものだが、日付・改変の旨の表示を通知文書に追加する | HOMR は**必須** |
| インストール情報・build script（AGPL の Corresponding Source の一部） | `Dockerfile`、`docker/patch_homr_onnx_provider.py`、`pyproject.toml`、固定 commit | 対象外 | **必須**（object code を渡す場合）。source 一式の配布で同時に満たせる | **必須**（HOMR 分） |
| ライセンス文・著作権表示・NOTICE | AGPL、Apache-2.0（NOTICE がある場合）、BSD、MIT、MPL 等の全同梱物 | 対象外 | **必須**（再配布する部品すべて）。site-packages の dist-info に含まれるが、受領者が参照できる `THIRD_PARTY_NOTICES` を用意する | **条件付き**: 複製物を渡さない部分は通常不要。AGPL の source 提供ページで併せて示すのが実務的 |
| GPL / LGPL のシステムパッケージ | Ubuntu base image と apt パッケージ | 対象外 | **必須**: ビルド済みイメージを渡す場合（対応ソースの入手方法の提示等）。受領者が自分でビルドする現行手順では当方の conveying なし | 対象外（イメージを渡さない） |
| NVIDIA CUDA のライセンス条件 | base image、`nvidia-*` wheel | 対象外 | **条件付き**: イメージを渡す場合、NVIDIA の再配布条件に従う。受領者自身のビルドなら受領者が NVIDIA と直接合意 | 対象外（自前クラウドでの利用条件は別途確認） |
| HOMR 重みの提供 | イメージ同梱の ONNX 重み | 対象外 | **未確定**（イメージ同梱で再配布する場合。上流 release の明示条件なし） | **未確定**（イメージ内の重みを当方のクラウドで第三者向けに使う場合。重みの条件は上流に明示がない） |
| OMR-DLN 重み | `YOLOv8m_Measures.pt` | **研究利用は黙示許諾の余地**（README にダウンロード・実験方法あり）。許諾範囲の法的確定はしていない | **同梱・再配布は回避**: その権限を明確に確認できない。利用者自身の取得は当方の再配布とは別に評価する | **未確定・提供ゲート**: 当方クラウドへ配置した第三者向け実行は README の実験案内だけでは許諾範囲を確認できないため保留 |
| Ultralytics が学習済みモデルにも AGPL が及ぶと主張する点 | OMR-DLN 重み | 未確定 | 未確定 | 未確定 |

補足:

- **受領者への提供と一般公開は別。** AGPL の source 提供義務の相手は object code の受領者と、§13 ではネットワーク越しの利用者である。
  不特定多数への一般公開は義務ではない。ただし公開 GitHub の固定 commit / tag への恒久リンクは、受領者への提供方法として最も簡単である。
- 「試用者が 1〜2 人だから不要」とはならない。人数は義務の有無を変えない。
- (c) で §13 を満たすには、ネットワーク越しの利用者に、実行中の版の Corresponding Source を無償で入手できる機会を目立つ形で提示する
  （例: GUI と Web 入口に「Source」リンクを置き、実行中 commit と一致させる）。

## 6. OMR-DLN: 研究利用、提供権限、自前再学習の区別

- 上流 [dmgonzalez8/OMR](https://github.com/dmgonzalez8/OMR) は 2024 年公開の研究・実験プロジェクト。README にモデルの Google Drive 取得先、学習手順・設定、評価結果を掲載する一方、リポジトリと重みに一般的な利用・改変・再配布権限を示す LICENSE は確認できない。
- **README に従った取得・研究実験を「違法」と断定しない。** 作者が実験利用を想定している根拠があり、状況により黙示的許諾の余地がある。ただし、権利範囲は法域・具体的な利用に依存する。**研究実験の想定 ≠ 重みの再配布や第三者向けクラウド提供の明示許諾**。現行の operator-supplied + SHA-256 import は当方の重み再配布を避けるもので、全ての利用形態の許諾を確定させるものではない。
- コードの権利、**上流の配布重み**、**Ultralytics の学習コード／初期重み**、**DeepScoresV2 等のデータ**を分離して評価する。推論だけを ONNX Runtime に変更しても、既存重みの権利関係は変わらない。
- **上流への問い合わせは行わない方針。** 公開情報で判断できない配布／クラウド利用は保留し、[#519](https://github.com/M763468/PDFScoreBar/issues/519) で既存補助検出経路の寄与と独立再学習を検討する。

### 6.1 公開済みの学習情報と再現性の不足

| 項目 | 確認した公開情報 | 再現時の注意 |
| --- | --- | --- |
| 対象 | YOLOv8m による小節領域の検出（`YOLOv8m_Measures.pt`） | PDFScoreBar は box 左右端を barline 支持情報に変換 |
| 学習設定 | [README](https://github.com/dmgonzalez8/OMR#yolo-training) / [`yolo/yolo.ipynb`](https://github.com/dmgonzalez8/OMR/blob/main/yolo/yolo.ipynb): 事前学習あり、500 epochs、batch=5、`imgsz=[704,992]`、patience=0、device 指定、deterministic/AMP | notebook ログに「`imgsz=992` へ更新」の警告あり。入力解像度が指定値どおりだったと仮定しない |
| データ | [DeepScoresV2](https://digitalcollection.zhaw.ch/items/1376f518-211d-49c8-a658-dbc7f085d2b1)（CC BY 4.0）、上流の処理済み `ds2_dense` / 小節box生成処理 | 小節用 GT の生成、データ分割、変換後の画像・box をそのまま再現可能か未確認。CC BY の帰属表示を行う |
| 学習コード | `yolo/yolo.ipynb`、`measure_detection/compute_barline_bboxs.py` 等 | 上流リポジトリに明示 LICENSE がないため、コードをコピーして本体へ組み込むのではなく、公開された**条件・手法を参考に独自実装**する案を優先 |
| Ultralytics | 元重みは事前学習済み `yolov8m.pt` を初期化に使用 | [Ultralytics公式](https://www.ultralytics.com/license) は、自社の学習コード／モデルを使ってゼロから作った重みにも AGPL が及ぶとの立場。法的な射程は事案ごとの確認事項 |

**追加の再現性ギャップ:** notebook には小節クラスを `label == 156` で抽出し、`deepscores_train_barlines_new.csv` / `deepscores_test_barlines_new.csv` を読み込む処理がある。しかし公開リポジトリの `yolo/deep_scores.yaml` に記載された `names` は少なくとも確認した版では `0..154` までで、`measure_detection/` にある同名 CSV は `_new` なしのファイルである。学習時に別途生成された YAML/CSV の可能性があり、**公開 notebook をそのまま実行すれば元モデルを再現できるとみなさない**。独立実装では学習用ラベル ID を新たに定義し、元データからの変換・分割・正規化を provenance に残す。

### 6.2 重みを独立に作る二つの経路

1. **A: Ultralytics を使い元の OMR-DLN 重みを使わず再学習**: 元作者の配布重みへの直接依存は削減できる。ただし、`yolov8m.pt` から初期化すれば事前学習元の条件が残り、`pretrained=False` で開始しても Ultralytics 実装・ライセンスの検討は残る。コードと重みを全て permissive にできる案とはみなさない。
2. **B: 独立した permissive 実装で再学習**: `torchvision` の検出器（BSD-3-Clause）、`YOLOX`（Apache-2.0）等を使用し、OMR-DLN の配布重み・無許諾の上流コード・Ultralytics 初期重みを使わずに小節検出器を学習する。必要なら scratch 初期化を優先し、追加で事前学習重みを使う場合はそれ自体の条件を確かめる。**元重みと上流コードの直接依存を回避する経路として本命候補**。ただし新規重みの配布条件は、学習データ・初期化元・実装条件を調べてから確定する。

上流の学習方法を参考にすることと、上流のコード・重みを複製することは異なる。どちらの経路も学習済みモデルの同等性は未検証で、精度を保証するものではない。

### 6.3 提供前の扱い

- **内部研究**: 現状の実験資産と provenance は維持。既存の実験利用を遡って違法と扱う根拠はないが、あらゆる利用が無条件に許諾されると断言もしない。
- **重みの再配布／自前クラウドから第三者提供**: 明示的な権限が確認できるまで OMR-DLN の重みを同梱・配置しない。完全な production 経路は OMR-DLN 支持を必須とするため、単純除去を production 化しない。
- **後続**: #519 で retained outputs による OMR-DLN ablation と、権利・精度が検証できる再学習・代替器の二本立てを進める。代替器は x4 画像入力、source 座標への戻し、`predictions.json` の既存出力契約を守る。学習・本番変更は別の検証ゲートで扱う。

## 7. 緩いライセンスの代替候補と比較計画

#504 の追加方針（2026-11-06）に従い、同等の契約を満たせる候補は置換を積極的に進める。ただし本 Issue では実装・再学習・production 変更をしない。
各候補は focused な後続 Issue で、固定入力・主要指標・regression gate・rollback 基準を事前に固定してから評価する。

| 対象 | 候補 | ライセンス | 機能互換と移植費用 | 必要な gate | 判断 |
| --- | --- | --- | --- | --- | --- |
| PyMuPDF（PDF 出力・番号レイヤ・再開） | `pikepdf`（MPL-2.0、qpdf は Apache-2.0）または `pypdf`（BSD-3-Clause） | 緩い / 弱いコピーレフト | 使用 API は `open`、`set_cropbox`、`get_contents` / `wrap_contents`、xref の get/set、`insert_text`、`insert_image`、`annots`、`get_fonts`、`save` 等。低水準の PDF オブジェクト操作が中心で、移植は中規模。`insert_text` のフォント埋め込みは代替実装が必要 | 番号レイヤの所有権・除去・往復（#441、MobileSheets roundtrip）、補正後最終出力、再開、[数値の幾何契約](../contracts/NUMBERING_GEOMETRY_CONTRACT.md)、ページサイズ・回転・cropbox、既存注釈の保持 | **有利**。補正 GUI サーバと出力経路から AGPL を外せる。最初の後続候補 |
| PyMuPDF（ページ描画・入力検査） | `pypdfium2`（PDFium。既にイメージに間接導入済み） | Apache-2.0 / BSD-3-Clause 系 | 描画結果のピクセルが変わり得るため、検出器入力が変わる。入力検査（画像・フォント・リンク列挙）も PDFium API で再実装 | 描画画像の差分評価に加え、`data/evaluation2` 全 68 ページの小節線 GT 指標、既存の GPU smoke gate、番号付け、性能 | **条件付きで有利**。精度 gate 通過が前提。出力経路の置換と分けて評価する |
| Ultralytics（OMR-DLN 推論） | ONNX へ export し ONNX Runtime（MIT）で推論 | MIT | 前処理・NMS・後処理の再実装が必要。費用は小〜中 | OMR-DLN 検出の一致（同一入力での box 差分）、下流の barline decision と番号付けの regression gate | **単独では限定的**。実行コードから AGPL を外せるが、重み（§6）と Ultralytics の学習済みモデルに関する主張は残る |
| OMR-DLN の寄与 | 保存済み baseline HOMR / current x4 HOMR / OMR-DLN / probe / CNN の retained artifact を用い、OMR 支持の削除による差分を再採点 | 新規依存なし | 変更なしで下流影響を調査可能かを先に確認。実行時の worker 削除とは別物 | focused/risk → full68、GT barline、番号付け、semantic topology、PDF 幾何、性能（事前固定） | **最優先**。検証結果は [#519](https://github.com/M763468/PDFScoreBar/issues/519) |
| OMR-DLN 重みだけ | YOLOv8m を自前再学習し、元の配布重みを使わない | Ultralytics の AGPL 義務が残る | 公開レシピを参照可能だが label 生成・split・実効 `imgsz` を調査 | 同一入力の box/support と下流の regression gate | **限定的**。元重みの依存解消だが、permissive 全面化ではない |
| OMR-DLN 重み + Ultralytics | permissive 検出器（torchvision BSD-3-Clause / YOLOX Apache-2.0）で DeepScoresV2 CC BY 4.0 等の由来明確なデータから自前再学習。元重み・元コード・Ultralytics 初期重みは使用しない | 緩い条件を目指す（最終的な重みの権利は要精査） | 再学習コストが大きい。source 座標の `predictions.json` という worker contract を維持した差し替えを想定するが、同等の精度が出るかは未検証 | box/support、downstream numbering、full68、PDF contract、性能、重み/コード/データの権利台帳 | **重点候補**。問い合わせを条件とせず [#519](https://github.com/M763468/PDFScoreBar/issues/519) で検証 |
| HOMR | 同等機能の緩いライセンス実装は見つかっていない。自前 segmentation の学習は費用大 | — | engine の基盤検出器で、置換は検出意味論全体を変える | 全面的な精度 gate | **現時点では置換不利**。AGPL を遵守して提供する（source 公開）方針が現実的。上流の状況が変われば再評価 |
| 追加の外部小節検出器 | [OMR-Research/MeasureDetector](https://github.com/OMR-Research/MeasureDetector) 等の学習済みモデルを調査。oemer は初期開発で不適合となり HOMR に変更した履歴がある | MeasureDetector の追加コードは MIT、同梱 TF 基盤は Apache-2.0。**モデル重み・学習元は別途確認** | 旧 TensorFlow 実装の移植費用あり。既存の不適合候補を根拠なしに優先しない | 条件が明確な重みに限定して同一入力比較 | **二次候補**。単にライブラリが permissive でも重みの権利問題は解消しない |
| Real-ESRGAN / BasicSR / RapidOCR / ONNX Runtime | 置換不要 | BSD / Apache / MIT | — | — | 通知の同梱のみ |

注意: 推論エンジンだけを替えても、モデル重み・学習成果物・追加 patch の権利は残る。置換候補が認識・番号付けの意味を変える場合は、
事前合意した指標と下流の PDF 契約をすべて通過したときにのみ採用し、閾値の調整で帳尻を合わせない。

## 8. 実行可能な遵守策（優先順）

**P0: (b) / (c) の試用前に必要**

1. #505 で自リポジトリのライセンスを決め、`LICENSE` を追加する（AGPL-3.0 と互換であることが条件）。
2. `THIRD_PARTY_NOTICES`（本台帳 §2・§3 の部品、ライセンス、取得元、固定版、改変の有無）を作り、配布物と GUI から参照できるようにする。
3. HOMR と BasicSR の改変について、改変日と内容を通知に明記する。
4. 提供時の source 提供方法を決める: 実行中の commit に固定した公開 GitHub の tag / commit へのリンクを、
   (b) では同梱文書に、(c) では GUI・Web 入口の「Source」リンクに置く。
5. OMR-DLN は、現在の上流公開表示だけでは第三者向けの重み再配布・当方クラウドでの提供権限を確定できないため、同梱・クラウド配置を保留する。上流への問い合わせは行わない。研究実験と公開提供を混同せず、#519 で代替を検証する（§6）。

**P1: イメージを配布する場合**

6. 間接依存を固定する（`uv.lock` 等から build）。候補イメージごとにライセンス台帳を再生成して provenance に含める。
7. Ubuntu / GPL パッケージの対応ソース入手方法と NVIDIA の再配布条件を整理する。受領者自身のビルドを既定にすればこの義務は当方に発生しない。

**P2: 長期のライセンス負担軽減（後続 Issue）**

8. PyMuPDF の出力経路を `pikepdf` / `pypdf` に置換する評価、続いて描画経路の `pypdfium2` 置換の評価。
9. #519 で OMR-DLN 支持を外した場合の retained-artifact ablation を最優先し、差分が無視できなければ、元重みと上流コードから独立した permissive 実装による再学習を評価する。元重みの ONNX 化だけでは権利問題は解決しない。

**専門家確認が望ましい事項**

- 別プロセスの OMR-DLN worker と本体、将来の別リポジトリ Web 入口が、AGPL 上の「結合著作物」に含まれるか。
- (c) で Ultralytics / PyMuPDF を無改変で使う場合の §13 の範囲。
- 学習済み重み（HOMR、OMR-DLN、ImageNet 初期化の first-party 重み）の著作物性と、学習データの条件が重みに及ぶか。
- 明示許諾のない公開重みのローカル利用の可否（法域による）。

## 9. #505 への引き継ぎ

確定事項（本監査の範囲で）:

- 現行 runtime は AGPL-3.0 部品（HOMR、Ultralytics、PyMuPDF）と同一プロセスで結合しており、結合したものを渡す・(c) で HOMR を使うときは、
  first-party コードを AGPL-3.0 と互換な条件で許諾する必要がある。MIT、Apache-2.0、AGPL-3.0 はいずれも互換。
- 互換性の要件は「結合物全体を AGPL の条件で受領者に渡せること」であり、first-party 部分に AGPL を選ぶことまでは要求しない。
- 第三者のコード・重みを first-party の LICENSE で再許諾することはできない。
- git 管理される重みは first-party の MMR 分類器のみ。外部重みは manifest のみを管理している。

未確定事項:

- OMR-DLN 重みの許諾、HOMR 重みの明示条件、Ultralytics の学習済みモデルに関する主張。
- ImageNet 初期化の first-party 重みと、著作権保護期間内の楽譜から作った GT・fixture の扱い。
- 別リポジトリ Web 入口と engine の結合関係。

## 10. #504 受入条件との照合と提供形態ごとのブロッカー

| #504 受入条件 | 本文書での対応 | 状態 |
| --- | --- | --- |
| 重要な第三者コード・重みごとのライセンスと証拠 URL / 版 | §2（コード）、§3（重み・データ）、§1（取得日と証拠の保存先） | 充足。間接依存は §1 の snapshot 限定 |
| 3 提供形態の 必須 / 条件付き / 対象外 / 未確定 の表（コード領域・理由つき） | §4（結合境界）、§5（義務表） | 充足。AGPL の厳密な範囲は未確定として残す |
| 自プロジェクトのライセンス選択と独立し、互換性を引き継げる形 | §9、[#505 の選択肢文書](REPOSITORY_LICENSE_OPTIONS.md) | 充足 |
| OMR-DLN の明示許諾がない場合の不明点と、確認・代替方針 | §6（問い合わせは行わず、#519 で寄与評価と独立再学習） | 充足。代替の技術検証は #519 |
| permissive 候補の機能・精度・geometry・再開・性能・ライセンスの比較計画と、置換が有利かの判断 | §7 | 充足。実装・再学習・production 変更は行っていない |
| 実装・配布・クラウド提供へ進むための未解決ブロッカーと専門家確認事項 | §8、下表 | 充足 |

提供形態ごとのブロッカー（2026-11-07 時点。解消したら該当 Issue / PR で記録する）:

| 提供形態 | ブロッカー | 解消先 |
| --- | --- | --- |
| (a) 内部実験 | なし。OMR-DLN の研究利用の許諾範囲は法的に確定していない（§6）が、現行の内部実験を止める根拠とはしない | — |
| (b) 少人数への配布 | first-party の `LICENSE` がない | #505（オーナー決定） |
| (b) | `THIRD_PARTY_NOTICES` と HOMR / BasicSR の改変表示がない | #505 承認後の focused PR |
| (b) | OMR-DLN の重みを同梱できない。重みなしでは production 経路が動かない | 受領者自身の取得を前提にするか、#519 の代替 |
| (b) イメージを渡す場合のみ | 間接依存が固定されていない。GPL / NVIDIA の再配布条件が未整理 | 受領者自身によるビルドを既定にすれば不要 |
| (c) 招待制リモート GPU / Web | (b) の LICENSE と NOTICE に加え、実行中 commit の source を案内する「Source」リンクがない | #505 承認後、#449 / #508 |
| (c) | OMR-DLN の重みを当方クラウドで第三者向けに使う権限が確認できない | #519 の結果（寄与が小さければ OMR-DLN を外す経路、大きければ独立再学習） |
| (c) | Ultralytics / PyMuPDF に対する §13 の範囲と、Web 入口と engine の結合関係が未確定 | 専門家確認、または AGPL 対象として source を提供する前提で設計 |
