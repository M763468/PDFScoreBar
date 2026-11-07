# 第三者ライセンス義務と緩いライセンスの代替候補（#504 監査）

[#504](https://github.com/M763468/PDFScoreBar/issues/504) の調査記録。原文は日本語（正本）。英語版は未作成。
自リポジトリに付与するライセンスの検討は [リポジトリライセンスの選択肢（#505）](REPOSITORY_LICENSE_OPTIONS.md) に分離した。

> **法的助言ではない。** 本文書はライセンス文、上流の表示、現行ソースから読み取れる事実と一般的な解釈を整理したもの。
> 「未確定」と書いた項目は推測で埋めず、必要なら専門家確認を経て判断する。

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
| HOMR ONNX 重み（segnet、transformer encoder/decoder） | HOMR の GitHub release `onnx_checkpoints` を build 時の `homr.main --init` が取得し、**イメージに同梱** | release 本文は "Pretrained onnx models for homr" のみで個別ライセンス表示なし。学習データは PrIMuS、GrandStaff、Lieder、PDMX 等（上流 `Training.md`） | **未確定**: リポジトリの AGPL-3.0 に従うと読むのが自然だが明示なし。学習データ各々の条件は未検証 |
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
| ローカルランチャー（`docker/distribution.py`、`docker/review_relay.py`） | AGPL 部品を import しない。`docker` CLI でコンテナを操作 | first-party の `docker/runtime_contract.py`、`src/common/model_artifacts.py` のみ import |
| 将来の Web 入口（#449、別リポジトリ想定） | 現存しない | ジョブ投入のみの独立サービスにできる設計余地はあるが、別プロセス・別リポジトリという形式だけで独立と断定しない |

結論: engine、OMR-DLN worker、補正 GUI サーバは、プロセス分割の有無にかかわらず AGPL 部品と一体の作品として扱うのが安全側の前提である。
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
| HOMR 重みの提供 | イメージ同梱の ONNX 重み | 対象外 | **未確定**（イメージ同梱で再配布する場合。上流 release の明示条件なし） | **未確定**（ただし AGPL 準拠で上流 release を案内すれば実務上の不足は小さい） |
| OMR-DLN 重み | `YOLOv8m_Measures.pt` | **未確定**（公開されているが利用許諾の明示なし） | **提供不可**（同梱・再配布しない）。受領者自身による取得と利用の可否も**未確定** | **未確定・実質ブロッカー**: 当方が運用するクラウドに配置し他者のために推論するには明示許諾が必要と扱う |
| Ultralytics が学習済みモデルにも AGPL が及ぶと主張する点 | OMR-DLN 重み | 未確定 | 未確定 | 未確定 |

補足:

- **受領者への提供と一般公開は別。** AGPL の source 提供義務の相手は object code の受領者と、§13 ではネットワーク越しの利用者である。
  不特定多数への一般公開は義務ではない。ただし公開 GitHub の固定 commit / tag への恒久リンクは、受領者への提供方法として最も簡単である。
- 「試用者が 1〜2 人だから不要」とはならない。人数は義務の有無を変えない。
- (c) で §13 を満たすには、ネットワーク越しの利用者に、実行中の版の Corresponding Source を無償で入手できる機会を目立つ形で提示する
  （例: GUI と Web 入口に「Source」リンクを置き、実行中 commit と一致させる）。

## 6. OMR-DLN

- 上流リポジトリに LICENSE ファイルはなく、README は Google Drive のモデルフォルダへの案内のみ。著作権法上、明示許諾のない公開物は利用・再配布の許諾を意味しない。
- 重みは Ultralytics の事前学習 YOLOv8m から学習されたと README にある。Ultralytics は学習済みモデルにも AGPL-3.0 が及ぶと主張しており、
  仮に上流作者が許諾しても AGPL 条件が付く可能性がある（**未確定**）。学習データ DeepScoresV2 は CC BY 4.0 で、帰属表示が必要になる。
- 現行の「同梱せず、利用者が取得してハッシュ検証つき import」という扱いは、当方の再配布を避けるが、利用者の利用許諾問題は解決しない。
- 推論を ONNX Runtime 等へ移植しても重みの権利問題は消えない。

上流への問い合わせ案（GitHub issue または README 記載の連絡先。英語）:

> We use the `YOLOv8m_Measures.pt` measure-detection weights linked from your README in PDFScoreBar
> (https://github.com/M763468/PDFScoreBar), a tool that numbers measures in score PDFs. The repository does not
> state a license for the code or the weights. Could you tell us under which license (for example MIT, Apache-2.0,
> CC BY 4.0 or AGPL-3.0) we may (1) run the weights locally, (2) run them on a cloud GPU on behalf of a few invited
> users, and (3) redistribute the unmodified weights inside a Docker image with attribution? Adding a LICENSE file
> to the repository would also resolve this for other users. Thank you for publishing the work.

許諾が得られない場合の方針:

1. (b)(c) の提供では OMR-DLN の重みを同梱・配置しない。(c) は OMR-DLN を当方クラウドで実行しない。
2. OMR-DLN を外した経路は現行 production 契約外であり、精度 gate の再評価なしに既定にしない（§7 の比較計画で扱う）。
3. 長期策は、許諾が明確なデータと緩いライセンスの学習コードで小節検出器を自前学習すること（§7）。

## 7. 緩いライセンスの代替候補と比較計画

#504 の追加方針（2026-11-06）に従い、同等の契約を満たせる候補は置換を積極的に進める。ただし本 Issue では実装・再学習・production 変更をしない。
各候補は focused な後続 Issue で、固定入力・主要指標・regression gate・rollback 基準を事前に固定してから評価する。

| 対象 | 候補 | ライセンス | 機能互換と移植費用 | 必要な gate | 判断 |
| --- | --- | --- | --- | --- | --- |
| PyMuPDF（PDF 出力・番号レイヤ・再開） | `pikepdf`（MPL-2.0、qpdf は Apache-2.0）または `pypdf`（BSD-3-Clause） | 緩い / 弱いコピーレフト | 使用 API は `open`、`set_cropbox`、`get_contents` / `wrap_contents`、xref の get/set、`insert_text`、`insert_image`、`annots`、`get_fonts`、`save` 等。低水準の PDF オブジェクト操作が中心で、移植は中規模。`insert_text` のフォント埋め込みは代替実装が必要 | 番号レイヤの所有権・除去・往復（#441、MobileSheets roundtrip）、補正後最終出力、再開、[数値の幾何契約](../contracts/NUMBERING_GEOMETRY_CONTRACT.md)、ページサイズ・回転・cropbox、既存注釈の保持 | **有利**。補正 GUI サーバと出力経路から AGPL を外せる。最初の後続候補 |
| PyMuPDF（ページ描画・入力検査） | `pypdfium2`（PDFium。既にイメージに間接導入済み） | Apache-2.0 / BSD-3-Clause 系 | 描画結果のピクセルが変わり得るため、検出器入力が変わる。入力検査（画像・フォント・リンク列挙）も PDFium API で再実装 | 描画画像の差分評価に加え、`data/evaluation2` 全 68 ページの小節線 GT 指標、既存の GPU smoke gate、番号付け、性能 | **条件付きで有利**。精度 gate 通過が前提。出力経路の置換と分けて評価する |
| Ultralytics（OMR-DLN 推論） | ONNX へ export し ONNX Runtime（MIT）で推論 | MIT | 前処理・NMS・後処理の再実装が必要。費用は小〜中 | OMR-DLN 検出の一致（同一入力での box 差分）、下流の barline decision と番号付けの regression gate | **単独では限定的**。実行コードから AGPL を外せるが、重み（§6）と Ultralytics の学習済みモデルに関する主張は残る |
| OMR-DLN 重みと Ultralytics | 緩いライセンスの検出フレームワーク（例: torchvision の検出モデル BSD-3-Clause、YOLOX Apache-2.0）で、許諾が明確なデータ（例: DeepScoresV2 CC BY 4.0、自前 GT）から小節検出器を再学習 | 緩い | 再学習・評価が必要で費用大 | 置換前後で同一入力の OMR-DLN 支持の役割（barline decision）に対する regression gate、精度・性能 | **長期的に有利**。OMR-DLN の許諾回答を待ってから着手判断 |
| HOMR | 同等機能の緩いライセンス実装は見つかっていない。自前 segmentation の学習は費用大 | — | engine の基盤検出器で、置換は検出意味論全体を変える | 全面的な精度 gate | **現時点では置換不利**。AGPL を遵守して提供する（source 公開）方針が現実的。上流の状況が変われば再評価 |
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
5. OMR-DLN は再配布・当方クラウド配置をしない。上流への問い合わせを送る（§6）。回答なしの間は (c) で OMR-DLN を使わない。

**P1: イメージを配布する場合**

6. 間接依存を固定する（`uv.lock` 等から build）。候補イメージごとにライセンス台帳を再生成して provenance に含める。
7. Ubuntu / GPL パッケージの対応ソース入手方法と NVIDIA の再配布条件を整理する。受領者自身のビルドを既定にすればこの義務は当方に発生しない。

**P2: 長期のライセンス負担軽減（後続 Issue）**

8. PyMuPDF の出力経路を `pikepdf` / `pypdf` に置換する評価、続いて描画経路の `pypdfium2` 置換の評価。
9. OMR-DLN の許諾結果を受けて、ONNX 推論化または緩い条件での小節検出器再学習を評価。

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
