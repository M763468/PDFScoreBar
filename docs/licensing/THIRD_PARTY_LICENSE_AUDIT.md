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
