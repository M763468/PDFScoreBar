# 第三者ライセンス義務と緩いライセンスの代替候補（#504 監査）

[#504](https://github.com/M763468/PDFScoreBar/issues/504) の調査記録。原文は日本語（正本）。英語版は未作成。
自リポジトリに付与するライセンスの検討は [リポジトリライセンスの選択肢（#505）](REPOSITORY_LICENSE_OPTIONS.md) に分離した。

> **法的助言ではない。** 本文書はライセンス文、上流の表示、現行ソースから読み取れる事実と一般的な解釈を整理したもの。
> 「未確定」と書いた項目は推測で埋めず、必要なら専門家確認を経て判断する。

## 0. 現行運用監査（2026-11-13 JST、`develop@6263350755f5`。最終調査 2026-11-15、`develop@25d0dad7ac8f`）

**この節が現在の監査の入口・提供判断の正本。** 以下の §1–§10 は PR #518 により採用された
`develop@3f7c8a632c6b`（2026-11-07）時点の監査スナップショットであり、歴史的証拠として保持する。
旧節の「現行」「必須」「ブロッカー」の記述が本節と矛盾する場合は本節を優先する。
本節は法律上の最終判断ではない。上流表示・依存定義・実際のイメージ同梱・提供方法を区別する。

**2026-11-15 の最終調査は [§0.8](#final-20261115) と、受入条件の照合は [§0.9](#acceptance-final)。**
**#533 の依存改善（非商用条件コード・HOMR transformer 重みの除去）と試用方式別の最終統合は [§0.10](#issue533-20261117)。** **Real-ESRGAN 重みの first-party SR への置換は [§0.11](#issue533-sr-20261118)。** 依存・重み・方式別の現在値は §0.10 を優先する。
§0.0–§0.7 の 2026-11-13 時点の記述（Python 台帳の「Metadata only 94 / Unresolved 1」、OS の未検出 3 件、
GPL/LGPL/AGPL の候補数、HOMR 重みの説明）は当時の結果として残す。分類と管理先が異なる場合は §0.8 を優先する。

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
  （2026-11-15 更新: この長期改善は [#533](https://github.com/M763468/PDFScoreBar/issues/533) に移管。§0.8.6）

<a id="final-20261115"></a>

### 0.8 最終調査（2026-11-15）

**対象:** repository `develop@25d0dad7ac8f17d1b9f2ed1a8398cc12d96f58f6`（PR #530 マージ後）。実物は §0.0 と同じ
`sha256:71cbccf6d7f7bba3b96989f8043e1b6b991a3d90122bfe6afda0aae82d99610a`（build source `97b8bc3c`）。
`git diff --name-status 97b8bc3c 25d0dad7 -- Dockerfile pyproject.toml docker/patch_homr_onnx_provider.py models src/homr_runtime/api_compat.py`
は空であり、依存定義・HOMR patch・モデル定義はこのイメージと一致する。**再ビルドはしていない。** 新しいimageを配布候補にする場合は
同じ手順で再採取する。イメージは `--network none`、mountなしで読み取り専用に検査した。

**証拠:** ローカル git 管理外の `logs/issue504/environment-audit/final-20261115/`。
`py-license-text-review.json`（99 distributionsの同梱ライセンス本文の分類、同梱shared library、NOTICE。SHA-256 `18461ec4…5988411459`）、
`os-dep5-review.json`（422 packagesのDEP-5 `License:` 欄。`95a9c812…8c42df2`）、
`python-license-ledger-20261115.json`（2026-11-13 の状態を `status_20261113` として保持した最終台帳。`82c2c9d2…416b1bc`）、
生成スクリプトとコマンドは同ディレクトリの `README.txt`。2026-11-13 の証拠ファイルは上書きしていない。
本文の分類は正規表現による本文の特徴照合と目視確認の組合せで、法的結論ではない。

#### 0.8.1 Python 99件の最終分類

[台帳](PYTHON_IMAGE_LICENSE_LEDGER.md) を 2026-11-15 の分類に更新した。各distributionの同梱ライセンス本文を読み、宣言と照合した。

| 2026-11-15 状態 | 件数 | 意味 | 対象 |
| --- | --- | --- | --- |
| Confirmed | 56 | 同梱本文が宣言と一致（または内容のないmeta-package）。通常の著作権・ライセンス表示の保持で足りる | 下記以外。`cuda-toolkit`、`facexlib`、`nvidia-nccl-cu13`（BSD-3）、`nvidia-nvtx`（Apache-2.0 WITH LLVM-exception）を含む |
| Confirmed + conditions | 24 | ライセンスは確認済み。ただし同梱部品や本文欠落により配布時に追加の作業・条件がある | numpy、scipy、opencv-python、opencv-python-headless、shapely、pillow、torchvision、torch、pypdfium2、onnxruntime-gpu、scikit-learn、grpcio、llvmlite、numba、fonttools、matplotlib、pip、setuptools、**PyMuPDF**、rapidocr、rapidocr-onnxruntime、flatbuffers、tensorboard-data-server、types-Pillow |
| Proprietary terms confirmed | 14 | NVIDIA独自条件の本文と該当条項を確認（§0.8.3） | CUDA Toolkit EULA 12件（cublas、cuda-cccl、cupti、nvrtc、cuda-runtime、cufft、cufile、curand、cusolver、cusparse、nvjitlink、nvshmem）、NVIDIA SDK License Agreement 2件（cudnn-cu13、cusparselt-cu13） |
| Verified | 2 | 固定版の上流LICENSEと改変を確認（HOMR、Real-ESRGAN） | homr、realesrgan |
| Legal review required | 2 | 非商用条件を含む同梱コードがあり、法的判断が必要（§0.8.5） | basicsr（2026-11-13 は Verified）、gfpgan |
| Not applicable | 1 | first-party | pdfscore-pipeline |

**2026-11-13 の未確定項目の解消:**
- `cuda-toolkit==13.0.3.0`（Unresolved → Confirmed）: [PyPI](https://pypi.org/project/cuda-toolkit/13.0.3.0/) とイメージ内METADATAが
  「ソフトウェアを含まずほかのpackageを入れるmeta-package」と示す。distribution自体に再配布するコードはない。torchの
  `cuda-toolkit[cublas,cudart,cufft,cufile,cupti,curand,cusolver,cusparse,nvjitlink,nvrtc,nvtx]==13.0.3` が選ぶ `nvidia-*` wheelの条件に従う。
- LICENSEを同梱しない4件: `flatbuffers`（[上流](https://github.com/google/flatbuffers) Apache-2.0）、`rapidocr-onnxruntime`（[上流](https://github.com/RapidAI/RapidOCR) Apache-2.0）、
  `tensorboard-data-server`（[上流](https://github.com/tensorflow/tensorboard) Apache-2.0）、`types-Pillow`（METADATA Apache-2.0、typeshed）。
  宣言は上流と一致したが、**(b)ではライセンス本文を通知へ補う必要がある**。`types-Pillow` は型スタブでruntimeに不要。
- `facexlib`: METADATAは Apache-2.0 だが、同梱本文と [上流](https://github.com/xinntao/facexlib) はMIT。本文を正とする。本番SR経路ではimportされない。
- 宣言と同梱本文の不一致はこの1件のみ（自動照合で他の94件に不一致なし）。

**同梱部品による追加条件（Confirmed + conditions の主な内容）:**
- **LGPL部品**: opencv-python（Qt5 LGPL-3、FFmpeg LGPL-2.1+）、opencv-python-headless（FFmpeg）、shapely（GEOS LGPL-2.1）、
  numpy / scipy（libquadmath LGPL-2.1+）、setuptools（vendored autocommand LGPL-3.0）。(b)ではLGPLの条件（ライセンス本文、
  利用者による置換を妨げない形、該当版のソース入手手段）を満たす。いずれも未改変のshared libraryとして同梱。
- **GPL-3 + GCC Runtime Library Exception**: libgfortran（numpy / scipy / opencv）、libgomp（scikit-learn）、pypdfium2のlibgcc/libstdc++表示。例外の範囲で通知保持。
- **opencv-pythonとopencv-python-headlessの二重導入**: `Dockerfile` が `opencv-python==4.11.0.86` を `--no-deps` で再導入するため両方が残る。
  通常版はQt5・X11系を含みLGPL部品が増える。ライセンス上の扱いは上記で足りるが、通常版が必要かは技術的に別判断（#533 の候補外。必要なら別Issue）。
- **PyMuPDF**: wheelの `COPYING` は「Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License」の1行だけで、AGPL全文と、
  同梱 `libmupdf.so` に含まれるMuPDFの第三者部品（FreeType、HarfBuzz、jbig2dec、libjpeg、lcms2mt、OpenJPEG、zlib 等）の通知を含まない。
  [上流 MuPDF](https://github.com/ArtifexSoftware/mupdf) / [PyMuPDF](https://github.com/pymupdf/PyMuPDF) はAGPL-3.0。(b)ではAGPL全文、対応ソース（MuPDFを含む）、第三者通知を補う。
- **torchvision**: CUDA EULAの部品 `libcudart`・`libnvjpeg` をwheel内に同梱するが、wheelのLICENSEはBSD部分のみ。NVIDIA部品は §0.8.3 の条件に従う。
- **onnxruntime-gpu**（325 KBの `ThirdPartyNotices.txt`）、**torch**（90ファイル）、**pypdfium2**（37ファイル）、pillow（18 shared libraries）等は
  同梱通知が多く、配布用NOTICEは自動抽出だけでなく同梱ファイルそのものを保持する方式が必要。

#### 0.8.2 Ubuntu 422件

全binary packageのcopyrightを再読し、DEP-5形式の `License:` 欄を抽出した（DEP-5 227件、自由形式 192件、copyrightなし 3件。source package 259件）。

- **copyrightなし3件（未検出 → 内容確認済み）:** `cuda-keyring`（apt鍵とsource設定のみ）、`cuda-libraries-12-3`（ファイルなしのmeta-package）、
  `cuda-compat-12-3`（source `cuda-drivers`、`libcuda.so.545.23.08` 等のドライバ互換ライブラリ）。前2件は再配布するコードを実質含まない。
  `cuda-compat-12-3` は個別copyrightがなく、ベースイメージの [NGC Deep Learning Container License](#ngc-container-license)（`/NGC-DL-CONTAINER-LICENSE`）と
  CUDA EULA Attachment A の「NVIDIA CUDA Driver Libraries」に該当する。**どちらの条項で再配布するかの解釈は法的確認事項**。
- **2026-11-13 の「AGPL 2件」は誤検出**: `ca-certificates`、`publicsuffix` のcopyright中のMPL-2.0「Secondary License」定義文。DEP-5 `License:` 欄にAGPLはない。
- **GPL/LGPL**: GPL系 `License:` 欄を含むpackage 245件（うちGPL-3系 98件）、LGPL系 192件、copyleft欄なし 122件。
  複数ライセンスのpackageを重複して数えるため、「binaryがGPL」という件数ではない。自由形式の18件（`base-files`、`diffutils`、`patch` 等）は欄を抽出できず、本文を個別に読む必要がある。
  `build-essential`（gcc/g++ 11、binutils 等）が最終imageに含まれる（`torch.compile` のため）。`python3.12` は Ubuntu ではなく `ppa:deadsnakes/ppa` から導入しており、ソースはPPA側で取得する。
- **配布形態ごとの扱い:** (a) 対象外。(b) imageを渡す場合、GPL/LGPL packageの対応ソースを同梱するか、各ライセンスが認める書面の申し出等で提供し、
  全copyrightを保持する。Ubuntu archiveへのリンクだけで義務を果たせるかは GPLv2 §3 / GPLv3 §6 の方式ごとの**法的確認事項**。
  未改変パッケージの再配布は [Ubuntu IP policy](https://ubuntu.com/legal/intellectual-property-policy) の範囲で行う。
  受領者が自分で `docker build` する方式では当方はこれらを配布しない。(c) imageを渡さない場合は配布義務の対象外。

<a id="ngc-container-license"></a>

#### 0.8.3 NVIDIA / CUDA / cuDNN（実同梱版）

| 層 | 実同梱版（対象image） | 条件の根拠（確認した本文） | 再配布の要点 |
| --- | --- | --- | --- |
| ベースイメージ全体 | `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04` | `/NGC-DL-CONTAINER-LICENSE`（NVIDIA Deep Learning Container License） | §1(b) 自前インフラで第三者向けサービスを提供可（コンテナを配布せず、NVIDIA APIを利用者へ直接公開しない）。§1(c) コンテナ全体を含む「Compatible」な派生コンテナを配布可。§2 の「配布」はインターネット経由の第三者向けサービスでの展開を含み、実質的な追加機能、NVIDIA保護と同等以上の条件、不遵守時の通知が条件 |
| OS CUDA | CUDA 12.3（cudart 12.3.101、nvrtc 12.3.107、cuBLAS/cuFFT/cuRAND/cuSOLVER/cuSPARSE/NPP/nvJPEG/nvJitLink/cuFile 12.3系） | 各copyright（CUDA EULA）、`/usr/local/cuda-12.3/gds/EULA.txt`、[CUDA 12.3.2 EULA](https://docs.nvidia.com/cuda/archive/12.3.2/eula/index.html) | Attachment A の部品、§2.3 のLinux向け未改変object code |
| OS cuDNN | `libcudnn9-cuda-12` 9.0.0.312 | copyright = NVIDIA SDK License Agreement | runtime `.so`/`.h` のみ配布可、§1.2の条件、§2.5 OSSライセンスの対象化禁止 |
| OS NCCL | `libnccl2` 2.20.3 | BSD-3-Clause | 通知保持 |
| ドライバ互換 | `cuda-compat-12-3` 545.23.08 | 個別copyrightなし | 上記 §0.8.2。解釈は法的確認事項 |
| Python CUDA 13 wheel | §0.8.1 の12件 | wheel同梱 `License.txt` = CUDA Toolkit EULA | §1.1.2: 実質的な追加機能をもつアプリへの組込み、アプリ経由のみのアクセス、NVIDIA保護と整合する配布条件、不遵守時の通知。Attachment A は CUDA Runtime、cuFFT、cuBLAS、cuSPARSE、cuSOLVER、cuRAND、NPP、nvJPEG、NVRTC、CUPTI、NVTX、Driver Libraries 等を列挙。**nvJitLink、cuFile、NVSHMEM、CCCL は列挙を確認できず**、§2.3（Linux向け部分は未改変なら再配布可）で足りるかは法的確認事項 |
| Python cuDNN / cuSPARSELt | `nvidia-cudnn-cu13` 9.24.0.43、`nvidia-cusparselt-cu13` 0.8.1 | NVIDIA SDK License Agreement | OS cuDNN と同じ |
| torchvision同梱 | `libcudart.so.13`、`libnvjpeg.so.13` | CUDA EULA（Attachment A掲載部品） | wheel LICENSEに現れないためNOTICEで補う |

**AGPLとの関係:** NVIDIA SDK License §2.5 / CUDA EULA は「SDKをOSSライセンスの対象にする使い方」を禁じる。AGPL §1 は「System Libraries」等を対応ソースから除外するが、
NVIDIA部品がこれに当たるか、**AGPL結合物と同じimageでNVIDIA部品を配布することが両条件と矛盾しないかは
法的確認事項**として残す。(c) では当方がNVIDIA部品を利用者へ渡さないため、NGCライセンス§1(b)/§2の条件で扱う。

#### 0.8.4 モデル重み・学習データ（公開情報で確認できた範囲）

- **HOMR transformer checkpoint 426（実同梱）**: 上流 [Training.md の Run 426](https://github.com/liebharc/homr/blob/72fdfa85e59933abb84e5ac2815e5918b28c48d6/Training.md)
  （commit `b6fd20809a8d`、2026-07-13）は「lieder+grandstaff+primux+pdmx+musetrainer」で学習したと記載。固定commit `457e7c65` の Training.md にも同じ記載がある。
  **426がPrIMuSとMusetrainerを含むことは上流表示で確認済み。** 2026-11-12 時点の
  [LICENSE_FAQ.md（`365283fef92a`）](https://github.com/liebharc/homr/blob/365283fef92a/LICENSE_FAQ.md) も「これまで公開したtransformer checkpointはすべてPrIMuSを含む」とする。
  PrIMuSは [配布元](https://grfia.dlsi.ua.es/primus/) に条件の表示がなく、HF複製は CC BY-NC 4.0。Musetrainerの条件は本監査で確認していない。
- **上流の変化（2026-11-13）**: Run 566（commit `ccd1cb311c36`）は「PrIMuS と Musetrainer を除外」と記載され、上流mainの既定checkpointは566に移った。
  現行の [LICENSE_FAQ.md（main `72fdfa85e599`）](https://github.com/liebharc/homr/blob/72fdfa85e59933abb84e5ac2815e5918b28c48d6/LICENSE_FAQ.md) はPrIMuSを学習データ表から外し、
  「非商用条件の学習データはない（GrandStaffは配布元に表示なし、HF複製はMIT）」とする一方、「変更前に公開した重みは当時の学習データのまま」と明記する。
  したがって **現行固定版（426）の条件は改善されていない。** 566への更新は固定commit・APIの変更と認識精度の再評価を伴うため、#533 の候補とする。
- **重みの権利**: 上流FAQは重みもAGPLで公開するとしつつ、「データセットの条件が重みに及ぶかは未解決の法的問題」「商用利用の法的リスクは利用者側」とする。**法的判断が必要。**
- **HOMR segmentation（segnet 308）**: DeepScoresV2（CC BY 4.0）。帰属表示が必要。重みへの波及の解釈は transformer と同じく未確定。
- **Real-ESRGAN x4plus / x2plus**: 上流 [Training.md](https://github.com/xinntao/Real-ESRGAN/blob/a4abfb2979a7bbff3f69f58f58ae324608821e27/docs/Training.md) によれば DF2K（DIV2K + Flickr2K）と OST で学習。
  [DIV2K](https://data.vision.ee.ethz.ch/cvl/DIV2K/) は「学術研究目的に限り提供」と表示。重み自体の個別ライセンス表示はない。**HOMRと同じ種類の未確定事項**として扱う。
- **RapidOCR同梱モデル**: `rapidocr_onnxruntime/models`（PP-OCRv4 det/rec、mobile cls）と `rapidocr/models`（PP-OCRv6 det/rec small、mobile cls）。
  [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) はApache-2.0。学習データは追跡していない。
- first-party重み（barline CNN、MMR）と評価データは #505 の範囲。変更なし。

#### 0.8.5 新たに見つかった非商用条件のコード

- **BasicSR 1.4.2**: `basicsr/ops/fused_act`、`basicsr/ops/upfirdn2d`（`.cu` を含む）は rosinality/stylegan2-pytorch からの改変とファイルに記載。
  BasicSR上流の [LICENSE/](https://github.com/XPixelGroup/BasicSR/tree/v1.4.2/LICENSE) は `LICENSE-NVIDIA`（**Nvidia Source Code License-NC**、「非商用 = 研究・評価目的のみ」）を
  StyleGAN2由来部分の条件として収録するが、wheelには Apache-2.0 の `LICENSE.txt` だけが入る。
  本番SR経路の `from basicsr.archs.rrdbnet_arch import RRDBNet` は `basicsr.archs` パッケージの一括importにより
  `basicsr.archs.stylegan2_arch`、`basicsr.ops.fused_act`、`basicsr.ops.upfirdn2d`、`basicsr.ops.dcn` を**読み込む**（2026-11-15 のimageで確認）。
  RRDBNetはこれらを実行せず、CUDA拡張はビルドされていない。
- **GFPGAN 1.3.8**: 同梱LICENSEに StyleGAN2 の NVIDIA ライセンス（非商用）と DFDNet 由来部分の CC BY-NC-SA 4.0 を含む。Real-ESRGANの依存として導入されるだけで、本番SR経路では読み込まれない。
- **扱い:** (a) 研究・評価の内部実験は非商用条件の範囲と読める余地が大きい。(b) imageにはこれらのファイルが含まれるため、
  非商用条件ファイルの再配布・商用試用との整合は**法的判断が必要**。(c) 実行コードとして読み込む点の評価も同様。
  技術的な回避（BasicSRのRRDBNetのみを使う構成、gfpgan/facexlibの除外）は #533 の候補。今回は変更しない。

#### 0.8.6 permissive代替候補と既存計画の十分性

§0.6 の評価計画（PyMuPDF出力/補正と入力描画を分け、精度・PDF幾何・注釈/履歴・再開・性能のゲートとrollbackを事前固定）は、
置換の有利・不利を判断する計画として十分と判断する。今回の調査で次を追加し、評価の管理先を
[#533](https://github.com/M763468/PDFScoreBar/issues/533) に移す（#504の完了条件には含めない）。

| 候補 | ライセンス上の効果 | 技術・評価上の注意 | 判断 |
| --- | --- | --- | --- |
| PyMuPDF出力・番号レイヤ・補正/再開 → `pikepdf`（MPL-2.0、qpdf Apache-2.0）/ `pypdf`（BSD-3-Clause） | engine・補正GUIからAGPL部品の一部を外せる | 低水準PDF操作・注釈・フォント・幾何の互換 | 有利（変更なし。§0.6 / §7） |
| PyMuPDF入力描画 → `pypdfium2`（Apache-2.0 / BSD-3-Clause + 同梱依存。対象imageに 5.15.1 が既に存在） | 両方を置換すればPyMuPDFを除去できる | 描画差が認識入力を変える。Full68等のゲートが前提 | 条件付きで有利（変更なし） |
| HOMR checkpoint 426 → 上流566以降 | PrIMuS（HF複製 CC BY-NC 4.0）由来の不確実性を除ける見込み。コードと重みのAGPLは残る | 固定commit・API互換・`api_compat.py`／ONNX provider patchの再確認、認識精度ゲート | **新規の有力候補**（#533） |
| HOMR全体のpermissive代替 | — | 精度同等の既存代替なし | 現時点で不利（変更なし） |
| BasicSRの非商用ops・GFPGANの回避 | 非商用条件ファイルの同梱・読み込みを除ける見込み | SR出力のbyte/数値同等性とFull68ゲート | **新規候補**（#533） |
| Real-ESRGAN重みの代替 | DIV2K由来の学術限定表示を除ける見込み | 代替SRモデルは認識入力を変える | 必要時のみ（#533） |

#### 0.8.7 配布形態ごとの義務（今回の追加分）

§0.4 の表に次を加える。分類は**必須 / 条件付き / 対象外 / 未確定（法的判断）**。

| 項目 | (a) 内部実験 | (b) 配布（実行物/フォルダ/image） | (c) 招待制GPU/Web |
| --- | --- | --- | --- |
| Confirmed 56件の通知 | 対象外 | **必須**: ライセンス・著作権表示の保持 | 条件付き: 複製物を渡さなければ通常不要。Source案内に併記が実務的 |
| Confirmed + conditions 24件 | 対象外 | **必須**: 同梱ファイル一式の保持、本文欠落4件とPyMuPDF（AGPL全文・MuPDF通知）の補充、LGPL部品のソース入手手段 | 条件付き: PyMuPDFは §0.4 のAGPL評価に従う |
| NVIDIA 14 wheel + OS CUDA/cuDNN | 対象外（GPU上の使用） | **条件付き**: CUDA EULA §1.1.2 / SDK License §1.2 / NGC §1(c)・§2 を満たす。nvJitLink・cuFile・NVSHMEM・CCCL・`cuda-compat` の根拠条項は**未確定（法的判断）** | **条件付き**: NGC §1(b)/§2（コンテナを配布しない、NVIDIA APIを直接公開しない、実質的な追加機能） |
| Ubuntu GPL/LGPL | 対象外 | **必須**（imageを渡す場合）: 対応ソースと通知。提供方式の十分性は**未確定（法的判断）**。受領者が自分でbuildする方式なら当方は配布しない | 対象外 |
| BasicSR NC ops / GFPGAN | 研究・評価の範囲と読める余地 | **未確定（法的判断）**: 非商用条件ファイルを含むimageの配布 | **未確定（法的判断）** |
| HOMR 426 / Real-ESRGAN 重み | 研究・評価の範囲と読める余地 | **未確定（法的判断）**: 学習データ（PrIMuS、DIV2K）の条件が重みに及ぶか | **未確定（法的判断）** |
| HOMR segnet / DeepScoresV2 | 対象外 | **必須**: CC BY 4.0 の帰属表示（重みに及ぶと解する場合を含め、表示しておく） | 条件付き: 同上を表示 |

#### 0.8.8 確認できたこと・未確認のこと・法的判断が必要なこと

| 区分 | 内容 |
| --- | --- |
| **確認済み** | Python 99件すべての宣言と同梱本文（不一致は `facexlib` 1件、本文なし4件は上流で確認）、`cuda-toolkit` がmeta-packageであること、同梱shared libraryとLGPL/GCC例外部品、PyMuPDF wheelにAGPL全文とMuPDF通知がないこと、OS 422件のDEP-5 `License:` 欄、copyrightなし3件の内容、OSの「AGPL」誤検出、NVIDIA各層の実同梱版と条件本文、Attachment Aの部品一覧、HOMR 426の学習データ構成（PrIMuS・Musetrainerを含む）と上流566での除外、Real-ESRGAN重みの学習データとDIV2Kの表示、BasicSR/GFPGANの非商用条件と本番経路での読み込み状況 |
| **未確認（事実関係）** | 自由形式copyright 18件の本文の個別読解、Musetrainer・GrandStaff・Flickr2K・OST・PaddleOCR学習データの条件、HOMR 566 の精度・API互換、新しいimage（再ビルド時）の依存差分 |
| **法的判断が必要** | AGPL結合物の厳密な範囲（§0.4）、学習データの条件が重みに及ぶか（HOMR、Real-ESRGAN）、NC条件コード（BasicSR ops、GFPGAN）を含むimageの配布と商用試用、NVIDIA部品のうちAttachment Aに列挙されないもの・`cuda-compat` の再配布根拠、NVIDIA独自条件とAGPL結合物の同時配布、Ubuntu GPL部品のソース提供方式の十分性 |

#### 0.8.9 未解決事項の影響と管理先

| 未解決事項 | 影響 | 管理先 |
| --- | --- | --- |
| 配布用 `THIRD_PARTY_NOTICES` の完成（同梱ファイル一式、本文欠落4件、PyMuPDF/MuPDF、torchvision内NVIDIA部品、DeepScoresV2帰属） | (b) の配布不可 | [#508](https://github.com/M763468/PDFScoreBar/issues/508)（試用の配布ゲート）、[#505](https://github.com/M763468/PDFScoreBar/issues/505) G6 |
| 対応ソース一式（HOMR改変、BasicSR改変、PyMuPDF/MuPDF、LGPL部品、Ubuntu GPL）の提供手段 | (b) の配布不可、(c) の §13 案内不可 | #508 |
| NVIDIA条件の適用条項（未列挙部品、`cuda-compat`）とAGPLとの同時配布 | image配布の (b) 不可。受領者build方式または (c) を選べば影響が縮小 | #508（方式選択）、必要なら専門家確認 |
| HOMR 426・Real-ESRGAN重みの学習データ由来の権利、BasicSR/GFPGANの非商用条件 | (b)(c) の商用・第三者提供の判断不可。内部実験は継続 | #508（Go/No-go）、技術的回避は [#533](https://github.com/M763468/PDFScoreBar/issues/533) |
| PyMuPDF / HOMR / SR関連のpermissive代替 | AGPL・NC負担の長期削減 | #533 |
| first-partyライセンスの正式付与 | (b) の前提 | #505（`main` 正式リリース時） |

<a id="acceptance-final"></a>

### 0.9 #504 受入条件の最終照合と Close 判断の根拠

| #504 受入条件 | 根拠 | 状態 |
| --- | --- | --- |
| 重要な第三者コード・重みごとにライセンスと証拠URL/版を追跡できる | §0.2、§0.3、§0.8.1–§0.8.4、[Python台帳](PYTHON_IMAGE_LICENSE_LEDGER.md)、ローカル `final-20261115/` | **充足**。Python 99件は全件で同梱本文または上流を確認し、Unresolved は 0 件。OS 422件・NVIDIA各層・重みは版と根拠を記録 |
| 3提供形態の 必須 / 条件付き / 対象外 / 未確定 の表（コード領域・理由、AGPLの範囲） | §0.4、§0.8.7 | **充足**。AGPL結合の厳密な範囲は「未確定（法的判断）」として明示 |
| 自プロジェクトのライセンス選択と独立し、互換性を引き継げる | §0.5、[REPOSITORY_LICENSE_OPTIONS.md](REPOSITORY_LICENSE_OPTIONS.md) §6 | **充足**。#505 の方針は変更なし |
| OMR-DLNの明示許諾がない場合の不明点と確認/代替方針 | §6、§0.1、§0.5 | **充足**。#523 で `develop` production から除去済み。`main` と過去の配布物は別管理 |
| permissive候補の比較計画と、置換が有利かの判断 | §0.6、§0.8.6、§7 | **充足**。候補ごとに有利/条件付き/不利を判断。置換・再学習・production変更はしていない |
| 実装・配布・クラウド提供へ進むための未解決ブロッカーと専門家確認事項 | §0.8.8、§0.8.9 | **充足**。管理先は #508 / #505 / #533 |

**Close 判断（推奨）:** 監査として求められた台帳・義務表・境界・代替評価計画・ブロッカーの整理は完了し、残る事項は
(1) 配布物の作成と配布時のGo/No-go（#508 / #505）、(2) 法的判断、(3) 置換の実施（#533）であり、いずれも #504 の受入条件ではなく管理先がある。
このため本PRの受入後に #504 を Close 可能と判断する。**Close は配布・商用利用の許可を意味しない。** 最終判断はオーナーが行う。


<a id="issue533-20261117"></a>

### 0.10 #533 の依存改善の統合（2026-11-17）

**対象:** branch `feature/issue533-sr-drop-basicsr`（base `develop@9b04b0a4`、PR #534 マージ後）。候補イメージ
`sha256:718454a8189cb98fc20a936250e608a977ab8c5026b11925221205f2acb61945`（build source `e82bdc56`、source fingerprint
`8abb32502b86…`、`pdfscore_issue533_candidate:e82bdc56`）。比較対象は §0.8 の監査イメージ `sha256:71cbccf6…`。
証拠はローカル `logs/issue533/`（`sr-equivalence/`、`homr-transcription-skip/`、`sr-replacement/`、`image-check/`、`validation/`、`handoff/`）。

#### 0.10.1 採用した変更

| 変更 | 内容 | 解消したライセンス上のリスク |
| --- | --- | --- |
| **SR コードの vendoring** | `realesrgan`（git）の導入をやめ、推論に使う `RRDBNet`（BasicSR 1.4.2、Apache-2.0）と `RealESRGANer`（Real-ESRGAN `a4abfb29`、BSD-3-Clause）だけを `src/third_party/realesrgan_sr/` に置く。ライセンス本文・出典・改変表示を同梱。build と runtime preflight は `basicsr`/`realesrgan`/`gfpgan`/`facexlib` が入っていれば失敗する | BasicSR の StyleGAN2 由来 ops（NVIDIA Source Code License-NC）と GFPGAN（NVIDIA-NC、CC BY-NC-SA 4.0）がイメージから消え、本番で読み込まれなくなった（§0.8.5 の「Legal review required」2件が 0件）。依存が23件減った |
| **HOMR transformer の不使用** | 本番の HOMR worker は SegNet の小節線・マスクだけを使い、transformer の転写結果（MusicXML）は捨てていた。`HomrPredictor` は転写を既定でスキップし、SegNet だけを要求する。イメージは `docker/init_homr_segnet.py` で SegNet 308 だけを取得し SHA-256 を照合する（transformer の ONNX があれば build 失敗） | checkpoint 426（上流 Training.md で PrIMuS・MuseTrainer を含めて学習）がイメージに入らず実行もされない。HOMR の segmentation 重みは SegNet 308 で、上流 FAQ の学習データは DeepScoresV2（CC BY 4.0、帰属表示） |

副次効果: x1 HOMR の処理時間が 1 ページ約 34.6 秒 → 9.5 秒（試行 1 ページ。性能主張の正式な測定ではない）。

#### 0.10.2 回帰ゲート（評価前に固定。結果）

| ゲート | 入力 | 結果 |
| --- | --- | --- |
| G1 本番 `CurrentX4SRRuntime`（eager、fp16、channels_last、tile=-1）の出力が upstream と byte 一致 | `data/evaluation2/images` 全73ページ（Full68 を含む） | **Passed** 73/73（監査イメージ上で vendored と upstream を同一 GPU で比較） |
| G2 本番設定 `compile_mode=reduce-overhead` で byte 一致 | 各曲の先頭ページ 5 | **Passed** 5/5 |
| G3 汎用 `RealESRGANer.enhance`（x4/x2、tile 0/400、pre_pad 0/10、BGR/gray/乱数） | 9 ケース × 8 設定 | **Passed** 72/72、state dict も一致 |
| H1 本番 x1 HOMR worker の全成果物（検出 JSON、staff/notehead/clef/connector マスク、proxy）が転写あり/なしで byte 一致 | 全73ページ | **全73ページで成果物一致。** 事前の判定式は「on 側で transformer が 1 回以上動くこと」も要求し、表紙・空ページ 5 件（HOMR が `No staffs found` で早期終了し、どちらの設定でも transformer が動かない）がこの条件で不一致と判定された。出力差ではない |
| H1b（H1 の結果を見た後に定義。H1 の記録はそのまま保持） | H1 の73ページ。表紙・空ページ5件は早期終了を記録する計測を加えて両設定を再実行 | **Passed** 73/73: 全成果物が byte 一致。68ページは on 側で transformer が実行され、5ページ（Shostakovich Sym5 p1/p17/p23、Prokofiev Sym5 p6/p12）は両設定とも HOMR の `No noteheads found` による早期終了で、transformer はどちらでも呼ばれない |
| G4 候補イメージ: 除外パッケージと transformer ONNX がないこと、他の版が不変であること | 候補イメージ | 除外は **Passed**。版の不変は**厳密には不合格**: 固定していない間接依存の再取得で `cuda-pathfinder`・`filelock`・`pypdfium2` が小版更新、`nvidia-cuda-cccl` が消えた。torch・onnxruntime・numpy・opencv・PyMuPDF 等の固定版は不変。OS 422 件は版まで一致 |
| G4' 間接依存を固定して再ビルド（2026-11-17、build source `2c5cb66e`） | 候補イメージ `sha256:7900ac2c9ebd…` | **Passed**: 監査イメージとの差は意図した23件の除去だけ（追加・版の変化なし）。`filelock` 4.2.9、`cuda-pathfinder` 1.8.6、`pypdfium2` 5.15.1 を `pyproject.toml` で固定。`nvidia-cuda-cccl` は監査イメージ内に要求元がなく（除去した Real-ESRGAN 導入工程の残り）、消えるのが正しい。OS 422件は版まで一致 |
| 本番精度 smoke（`make run-smoke`、`configs/smoke_test.yaml`） | 候補イメージ、Va_Prokofiev_Symphony1 p1 | **Passed**（preflight fingerprint 一致、85/85、hard FP 0、FN 0、soft 0） |
| 本番精度 smoke（固定後イメージ） | `sha256:7900ac2c9ebd…`、同じ入力 | **Passed**（fingerprint 一致、85/85、hard FP 0、FN 0、soft 0） |
| Full68 replay（#522 と同じ手順。x4 HOMR を候補イメージで再実行し下流を再生成） | 68ページ、`e82bdc56` と `2c5cb66e` の両イメージ | **Passed**: どちらも TP 3560 / FP 0 / FN 7 / 小節 3287（#522 の受入値を再現）。2つのイメージ間で全68ページの予測・番号付けが byte 一致 |
| fast tests / focused tests | 使い捨て検証コンテナ | **Passed**（fast 149、focused 166） |

SR と HOMR の各段の出力が byte 一致したため、下流（候補生成・CNN・番号付け）の入力は変わらない。最終イメージでは x4 HOMR の再実行を含む Full68 replay を追加で確認した。x1 HOMR を含む Full68 の新規実行（fresh run）はしていない（x1 は H1/H1b で全ページ byte 一致）。

#### 0.10.3 #533 の各候補の判断

| 候補 | 判断 | 根拠 |
| --- | --- | --- |
| BasicSR の NC ops・GFPGAN の除去 | **採用** | §0.10.1・§0.10.2 |
| HOMR 426 → 566 以降への更新 | **不採用（不要化で代替）** | 566 は語彙（vocabulary）が変わり、固定コードに重みだけ差し替えることはできない。HOMR 本体の更新と認識精度の再評価が必要になる。PDFScoreBar は transformer の出力を使っておらず、transformer を実行しない方が学習データの不確実性を完全に除ける（AGPL は残る） |
| Real-ESRGAN 重みの不要化（x4 を非学習の補間で作る） | **不採用（ゲート不合格）** | 評価前に固定した契約: Full68、#522 と同じ replay（保持済み x1 baseline、本番の consensus・CNN・番号付け、閾値の変更なし）で x4 HOMR の入力だけを差し替え、同じハーネスの Real-ESRGAN 対照と比べ、FP 増・新規 FN・小節数/番号の変化ページがないこと。対照は TP 3560 / FP 0 / FN 7 / soft 117 / 小節 3287（#522 の受入値を再現）。`INTER_LANCZOS4` は FP **101**、`INTER_CUBIC` は FP **107** に増え、どちらも13ページで小節数が変わった（新規 FN 0）。ローカル `logs/issue533/sr-replacement/` |
| Real-ESRGAN 重みの別モデルへの置換 | **実施・採用（§0.11）** | 学術用途に限定されない学習データの SR 重みで、同じ契約を満たす公開候補を確認していない。独自学習は精度・費用の別課題。現行重みの扱いはオーナー・法的判断（§0.10.6） |
| PyMuPDF の出力・番号レイヤ・補正の置換（`pikepdf`/`pypdf`） | **今回は不採用（AGPL遵守で維持）** | first-party は AGPL-3.0-or-later の方針（#505）で、HOMR も AGPL のため、PyMuPDF を外しても製品全体の AGPL は消えない。受領者 build 方式（§0.10.5）では当方は PyMuPDF を配布しない。イメージ・portable 配布では AGPL 全文・MuPDF を含む対応ソース・第三者通知で遵守できる。first-party を permissive にする判断が出たときに再評価する |
| PyMuPDF の入力描画の置換（`pypdfium2`） | **今回は不採用** | 同上。描画差は認識入力を変え Full68 の再評価が必要で、ライセンス上の効果が上記理由で小さい |
| NVIDIA / CUDA | **方式で回避**（§0.10.5） | 受領者 build 方式とリモート提供では、当方は NVIDIA 部品を再配布しない。イメージ・portable を配布する場合だけ §0.8.3 の条件と法的確認事項が残る。`nvidia-cuda-cccl` は消えた |

#### 0.10.4 採用後の版と fingerprint

| 項目 | 値 |
| --- | --- |
| source | `feature/issue533-sr-drop-basicsr`（PR の最終 HEAD は PR 本文に記録） |
| image | `sha256:7900ac2c9ebd1cbdd4a1835341cd5fa1da34cc2402faa1a43f7f55b764b09461`（build source `2c5cb66e`、source fingerprint `7310f616…`）。初回候補 `sha256:718454a8…`（`e82bdc56`）は間接依存の版が動いたため置き換えた |
| base image | `nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04`（OS 422 packages、監査イメージと同一） |
| Python | 76 distributions（`PYTHON_IMAGE_LICENSE_LEDGER.md` の #533 節） |
| HOMR | `457e7c6518a10ba755db2e60883419e56c4d7369`（改変: `docker/patch_homr_onnx_provider.py`。SegNet 308 のみ、ONNX SHA-256 `60f49549…eee2fa83`） |
| Real-ESRGAN 重み | x4 `4fa0d389…d682f1`、x2 `49fafd45…266abb`（PR #536 時点。§0.11 で first-party の x4 SR に置換し、Real-ESRGAN 重みは使わない） |
| vendored コード | `src/third_party/realesrgan_sr/`（Apache-2.0 / BSD-3-Clause） |

#### 0.10.5 試用方式の比較と、準備を完成させた方式

試用者の環境（OS・GPU）は未確定（#508 Phase 0）。#506 は同一マシンの Windows ネイティブ PoC を確認したが、第三者向け portable build は未承認・未検証。

| 方式 | 当方が渡すもの | 第三者ライセンス上の残作業 | 技術前提 |
| --- | --- | --- | --- |
| **(A) 受領者 build**（最小配布ソース + 受領者が `docker build`） | `tools/materialize_distribution.py` が作る 125 ファイル（first-party、vendored SR コード、HOMR patch スクリプト） | **第三者分は完了**（下記）。first-party の許諾（#505）と重みの判断が残る | Linux または Windows+WSL2+Docker Desktop（#503）、NVIDIA GPU、build 時のネットワーク |
| (B) イメージ配布 | Docker image | Ubuntu GPL/LGPL の対応ソース、NVIDIA 再配布条件（未列挙部品・`cuda-compat` の法的確認）、PyMuPDF の AGPL 全文と MuPDF 通知、本文欠落3件、LGPL 部品 | Docker |
| (C) Windows portable | フォルダ | (B) から Ubuntu を除き、Windows 用 NVIDIA DLL 等の再配布条件を加えたもの | #506 で未承認 |
| (D) 時間限定リモート GPU | アクセスのみ | AGPL §13（改変 HOMR = 固定 commit + patch、PDFScoreBar 自身）の対応ソース案内、NGC §1(b)/§2、データ保護 | #449 は保留、運用構築が必要 |

**(A) を第三者ライセンス上の準備を完成させた方式とする。** 理由: 当方が配布するのは first-party のソースと
ライセンス本文付きの vendored コードだけで、HOMR・PyMuPDF・NVIDIA・Ubuntu・PyPI の部品と第三者重みは受領者の build が上流から直接取得する。
当方はそれらを再配布せず、改変版 HOMR も受領者の手元で作られ、ネットワーク越しに第三者へ提供されない。
(A) で当方が満たすべき第三者条件と状態:

| 条件 | 状態 |
| --- | --- |
| vendored コードのライセンス本文・著作権表示・改変表示（Apache-2.0 §4、BSD-3 §1） | **完了**（`src/third_party/realesrgan_sr/`。配布 manifest に登録済み） |
| HOMR 引用断片（`docker/patch_homr_onnx_provider.py`）の表示 | #505 パッケージの `NOTICE`/`THIRD_PARTY_NOTICES.md` に記載済み |
| build で取得する部品と条件の案内（NGC コンテナライセンス・CUDA EULA は取得者が受諾） | 改訂版 `THIRD_PARTY_NOTICES.md` を作成（ローカル `logs/issue533/handoff/`。#505 の適用時に差し替え） |
| 非商用条件コード・PrIMuS 由来重みの不在 | **完了**（build と preflight で強制） |
| 受領者側の検証手順 | 下記 |

受領者側の構築・検証手順（(A)）:

1. 提供者: 凍結した source commit から `python3 tools/materialize_distribution.py materialize <dir>` と `... check <dir>` を実行し、`DISTRIBUTION_PROVENANCE.json` の hash を記録して渡す。
2. 受領者: `docker/distribution.py` の手順（`docs/USER_GUIDE.md`）で build する。Dockerfile が（§0.11 以降は first-party SR 重み、それ以前は Real-ESRGAN 重み）・SegNet の SHA-256、HOMR の固定 commit を照合し、除外パッケージや transformer ONNX があれば build を止める。
3. 受領者: preflight（`docker/runtime_contract.py`）が source fingerprint・除外モジュール・CUDA を確認する。提供者は fingerprint を受領者の結果と照合する。

**(A) で残る、技術では解消できない事項:** first-party の許諾（#505。正式リリース前なら試用者への書面の個別許諾をオーナーが判断）、
first-party 重み（MMR、barline CNN）の許諾、Real-ESRGAN 重みの学習データ（DIV2K の学術研究限定の表示。§0.11 の置換で解消）、SegNet の DeepScoresV2 帰属表示の方法。

#### 0.10.6 #504 の最終統合: 残る条件と判断先

| 事項 | 種類 | 回避策・判断先 |
| --- | --- | --- |
| Real-ESRGAN 重み（DF2K: DIV2K は学術研究限定と表示、Flickr2K、OST） | 権利 → **技術的に解消（§0.11）** | first-party の x4 SR（ランダム初期化・自作合成データのみ）に置換し、Full68 ゲートに合格。Real-ESRGAN の重みは取得・同梱・受け入れをしない。PR のマージで製品から除かれる |
| SegNet 308（DeepScoresV2、CC BY 4.0）。上流は重みを AGPL と表示 | 帰属表示 | THIRD_PARTY_NOTICES に記載（改訂版で対応）。重みへの波及は法的判断だが CC BY は商用可 |
| first-party の LICENSE と重み | オーナー判断 | #505（develop には先行付与しない） |
| (B)/(C) を選ぶ場合の Ubuntu・NVIDIA・PyMuPDF の再配布義務 | 方式依存 | §0.8.7。(A)/(D) では発生しない |
| AGPL 結合の範囲、NVIDIA 部品と AGPL 結合物の同時配布 | 法的判断 | (A)/(D) では当方が NVIDIA 部品を配布しないため問題にならない |
| (D) の AGPL §13 の案内 | 方式依存 | 改変 HOMR（固定 commit + patch）と PDFScoreBar の source commit の案内を UI 等に置く |


<a id="issue533-sr-20261118"></a>

### 0.11 Real-ESRGAN 重みの置換（#533 第2段、2026-11-18）

**オーナー方針（2026-11-18）:** 既存の Real-ESRGAN 重みの権利上の不確実性は、権利者への問い合わせではなく技術的な置換か独自学習で解消する。外部への問い合わせはしない。

**対象:** branch `feature/issue533-sr-replacement`（PR #536 の上に積む）。評価は §0.10 の最終イメージ `sha256:7900ac2c9ebd…` で行った。
証拠はローカル `logs/issue533/sr-replacement/`、`sr-train/`、`sr-perf/`、`sr-nonlearned/`。

#### 0.11.1 評価契約（候補の結果を見る前に固定）

| 項目 | 内容 |
| --- | --- |
| 対照 | 同じイメージ上の Real-ESRGAN x4（`replay_2c5cb66e/esrgan`）。TP 3560 / FP 0 / FN 7 / soft 117 / 小節 3287 |
| 入力 | Full68（68ページ）。#409 で保持された x1 baseline、#522 と同じ replay（本番の consensus・CNN・番号付け）。x4 HOMR は候補の SR 画像で本番 worker を再実行。`configs/dense_full_pipeline.yaml` と閾値は変更しない。推論は決定的で seed 不要 |
| 主要ゲート | 対照比で FP が増えない、新規 FN がない、TP が減らない、全ページの譜表ごとの小節数リストが一致、全ページの小節番号の列が一致 |
| 記録のみ | soft、予測と小節 bbox の幾何、x4 HOMR の検出数、GPU メモリ・処理時間 |
| 段階 | Lanczos で失敗した36ページでスクリーニング（他ページは対照の結果を使う）→ 合格した候補だけ全68ページ |
| 学習データ | Full68 と評価 GT・楽譜 PDF・第三者画像は使わない。学習・holdout とも自作の合成データ（holdout は学習と重ならない seed） |
| rollback | 不合格なら Real-ESRGAN 構成を維持 |

#### 0.11.2 候補と結果

| 候補 | 内容 | 結果 |
| --- | --- | --- |
| Lanczos / Cubic（§0.10.3、既知） | 補間だけ | 不合格（FP +101 / +107、13ページで小節数変化） |
| NL-A | Lanczos x4 → Gaussian σ=1.0 → シグモイド階調（中心128、幅10）。輪郭を保ちつつ 2 値に近づける | **不合格**: FP 1（Prokofiev 交響曲1番 p3）。小節数・番号の変化 0 |
| NL-B | NL-A で σ=2.0 | **不合格**: 同じ FP 1 |
| NL-C | Lanczos x4 → アンシャープマスク（σ=3、量1.5） | **不合格**: FP 21、新規 FN 1、5ページで小節数変化 |
| NL-D | NL-A で中心150（線を太らせる側） | **不合格**: 同じ FP 1 |
| 学習 s1 | ランダム初期化の RRDBNet（nf32、6ブロック、growth 16、111.9万パラメータ）、合成データ、L1、6000 iter | スクリーニング合格、Full68 **合格**（FP 0 / FN 7 / soft 119、小節・番号一致）。学習時のスクリプトは整形前のバイト列を保存していないため出荷しない |
| **学習 s1r（採用）** | s1 と同じ設定を、コミット済みスクリプト（SHA-256 を manifest に記録、seed 533）で再学習 | Full68（68ページすべてを新規に計算）**合格**: TP 3560 / FP 0 / FN 7 / 新規 FN 0、全5曲で小節数（349/815/613/504/1006）と番号が対照と一致。soft 121（対照 117） |
| 学習 s2 | nf48、8ブロック、20000 iter | 学習のみ（holdout PSNR 約30dB）。Full68 では評価していない（s1r が合格したため。複数モデルを Full68 で比べて選ぶ選択バイアスを避けた） |

非学習型の3条件は同じ1件の FP だけで不合格になった。閾値や対象ページの事後変更はしていない。

#### 0.11.3 採用モデル `pdfscorebar-sr-x4` `issue533-s1r`

| 項目 | 内容 |
| --- | --- |
| 重み | `models/sr_x4/pdfscorebar_sr_x4_issue533_s1r.pth`（4.5 MB、SHA-256 `3b6b37a3947c7960632175efa81d24b5efbfc29e621004df79361ce040d8a1a6`）。`models/sr_x4/manifest.json` に構造・学習コマンド・seed・スクリプトのハッシュ・実行環境を記録 |
| 初期値 | ランダム（事前学習重みなし）。Real-ESRGAN/ESRGAN の重みも出力も使わない（蒸留なし） |
| 学習データ | `tools/issue533/synth_score.py` が OpenCV の描画関数と OpenCV 組込みの Hershey フォントで生成する手続き的な合成楽譜（譜線・小節線・符頭・符尾・連桁・スラー・文字等）と、再現可能な劣化（ぼけ・縮小・1bit 原稿の再標本化・ノイズ・JPEG）。ファイルを読み込まないことをテストで確認 |
| コード | 学習 `tools/issue533/train_sr.py`、ネットワークは vendoring した Apache-2.0 の RRDBNet |
| 再現性 | 初期化と holdout は seed で再現する（s1 と s1r の iter 0 の指標が一致）。CUDA と DataLoader の並列順序は bit 単位で決定的でないため、再学習は同等だが同一バイトにはならない。出荷するのは評価したバイト列そのもの |
| 権利 | first-party。リポジトリのライセンス判断（#505）に従う。第三者の重み・データの権利は含まない |

#### 0.11.4 影響（記録のみ）

| 項目 | 結果 |
| --- | --- |
| 予測・PDF の幾何 | 25ページで最終予測の座標が変化（主に soft 判定の予測。追加42 / 削除38）。小節 bbox の最大ずれは 4px（360dpi で約0.3mm）。小節数・番号は全ページ一致 |
| HOMR | x4 HOMR の生検出数は 4424 → 3965（約−10%）。後段の合議・CNN の後で最終結果は対照と同じ |
| 補正・再開・PDF 出力 | これらのコードは変更していない。入力となる予測の変化は上記の幾何の範囲 |
| SR 段の処理時間・GPU メモリ（RTX 4060、5ページ） | eager: 1ページ 8.5秒（Real-ESRGAN 54.7秒）、ピーク 543 MiB（939 MiB）。本番設定の compile（reduce-overhead）: 2ページ目以降 6.9秒（43.4秒）、初回ページ（compile を含む）28.0秒（207.6秒）、ピーク 506 MiB（838 MiB） |
| 本番経路との一致 | 本番の読み込み経路（manifest → ハッシュ照合 → 推論）と評価ハーネスの SR 出力が5ページで byte 一致 |
| #532 の空ページ判定（develop の #537 で追加。閾値は Real-ESRGAN の x4 画像で校正） | E1（評価前に固定）: 表紙・空白5ページを本番の x4 HOMR worker に通し、対照と s1r で同じ結果になること。**合格**: 5ページとも両方で `non_score_page` として正常通過。s1r の譜表証拠（inner staff fraction 最大 6.6e-6、最大行 0.0052）は対照（最大 1.3e-4、0.018）より閾値（5e-4、0.05）から遠い |
| develop（#537）merge 後の再検証 | merge 後のコードで対照と s1r の Full68 replay を再実行。対照は merge 前と全68ページで同一、s1r も merge 前と全ページで同一で、ゲート**合格** |

#### 0.11.5 本番への反映

- Real-ESRGAN の release 重み（x4plus・x2plus）の取得・同梱をやめた。`PDFSCORE_REALESRGAN_WEIGHTS_DIR` と `/opt/pdfscore-assets/realesrgan` は廃止。
- x4: `resolve_first_party_sr` が manifest を読み、読み込みのたびに SHA-256 を照合する（`CurrentX4SRRuntime`、`apply_advanced_sr`、compile cache の識別）。
- x2: 本番は `sr_scale=4` 必須で、x2 は評価スクリプトだけが使っていた。first-party の x2 は作らず、x2 の要求は失敗させる（非 strict の評価経路は入力を返す）。
- Docker build と runtime preflight は manifest が選択する first-party の重みを照合する。配布 manifest に重みと manifest を追加（develop の #537 と合わせて128ファイル）。

#### 0.11.6 #504 への反映

§0.10.6 の Real-ESRGAN release 重みは本変更で実行経路から除かれる。第三者モデルとして HOMR SegNet 308（DeepScoresV2 の CC BY 4.0 帰属表示）、HOMR の OCR 資産、および RapidOCR 同梱モデル（§0.8.5）が残る。各モデルの表示・条件の確認は引き続き必要である。first-party 重みの扱いは #505 に従う。
`THIRD_PARTY_NOTICES.md` の改訂案（ローカル `logs/issue533/handoff/`）から Real-ESRGAN 重みの行を削除し、first-party の SR 重みは `NOTICE`／#505 の扱いに移す。

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
