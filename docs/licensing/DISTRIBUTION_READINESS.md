# 配布候補ごとの権利・通知・対応ソースの判定（#553）

[#553](https://github.com/M763468/PDFScoreBar/issues/553) の記録。原文は日本語（正本）。英語版は未作成。
判定日 **2026-11-23**。

> **法的助言ではない。** ライセンス本文・上流の表示・実物（wheel、checkpoint、データ）から確認した事実と、
> それに基づく分類を記録する。「法的判断が必要」とした論点は推測で埋めず、§5 に必要資料とともに示す。
> この文書は first-party のライセンスを付与しない（#505 の正式適用はオーナー承認後）。

前提として再利用した記録：[#504 監査](THIRD_PARTY_LICENSE_AUDIT.md) §0.8–§0.11（Linux image の Python・OS・NVIDIA、
HOMR、BasicSR/GFPGAN の除去、SR 重みの first-party 化）、[#505](REPOSITORY_LICENSE_OPTIONS.md)（first-party は
AGPL-3.0-or-later に決定、適用は未実施）。これらを再調査せず、**配布物ごとに未確認だった事実**だけを追加で確認した。

## 0. 判定の対象

| 配布候補 | 固定値 | 当方が渡すもの |
| --- | --- | --- |
| **Windows 限定試用**（#508、同一組織の 1〜2 人） | portable source `93e2c2b2cdb5a24dbd9fd8a7ceb8b2dc5a4e6460`（#551 / PR #552） | フォルダ一式：`app/`（main 最小配布 135 件 + provenance）、`launcher/`、**CPython と第三者 wheel 一式（ネイティブ DLL を含む）**、barline CNN 重み、DejaVu フォント |
| **main 最小配布**（#550 rc1） | source `a757211a9e02e5b3c9626db6a188227dbcd1738b`、candidate `9bb4f416…` | **ソースのみ**（manifest 選定 135 件。MMR 重みと first-party SR 重みを含む）。第三者部品・HOMR・NVIDIA は受領者の `docker build` が上流から取得。barline CNN は GitHub release asset から取得 |

Docker image の配布は選定されていない（§4.3）。

## 1. 結論

| 配布候補 | 判定 | 理由（詳細は §3・§4） |
| --- | --- | --- |
| **Windows 限定試用** | **判断待ち**（オーナー判断・法的判断）＋ **未完了**（実ビルドでの照合） | (1) first-party の許諾が未付与（#505）。(2) MMR・barline CNN 重みの受領者への許諾と、学習用スキャンの入手条件の確認がオーナー待ち。barline CNN の初期化重みには「ImageNet の条件が重みに及ぶと想定すべき」という上流作者の表示がある。(3) Windows では CUDA EULA の再配布対象に**列挙されていない NVIDIA ファイル**（`ptxas.exe`、`nvperf_host.dll`、`cusolverMg64_11.dll`、`cuda.lib`、`cuda.h`）が同梱される。(4) torch 同梱の Intel OpenMP DLL の条件（逆アセンブル禁止を受領者契約で課す義務、Reciprocal OSS 化の禁止）と AGPL 製品フォルダとの関係。(5) 実ビルドの `build_manifest.json` での照合と bundle 生成は Windows ビルド後 |
| **main 最小配布** | **判断待ち**（オーナー判断） | 第三者のバイナリは配布しない。必要な通知・対応ソース・ライセンス一式は非公開パッケージで準備し検証済み（§4）。残るのは (1) #505 の正式適用の承認、(2) MMR 重み（ソースに同梱）と barline CNN release asset の扱い（現状 NotLicensed のまま配布するか、許諾・置換するか） |

どちらも **GO ではない**。受領者への受け渡し、LICENSE の公開、main 昇格、tag/release は実施していない。

## 2. モデル重みの lineage と判断

### 2.1 確認した事実

| 重み（同梱場所） | SHA-256 | 初期化 | 学習データ | 証拠 |
| --- | --- | --- | --- | --- |
| **MMR**（`app/models/mmr/mmr_classifier_best.pth`） | `f163fa2a…903a` | torchvision ResNet18 `IMAGENET1K_V1`（`resnet18-f37072fd.pth`） | 小節の切り抜き約3,700件（正例192）：evaluation2 の 5 曲（下表）と旧 `data/training`・`data/evaluation` の3ページ（うち training は IMSLP19910 = Beethoven 交響曲9番 Vn1、IMSLP のパブリックドメイン版）。ラベルは first-party の rest GT | 2026-01-12 の commit `b01bf49a2` で追加されて以来 **bytes 不変**（blob `be518166`）。学習スクリプトは同 commit（`pretrained=True`）。当時の学習集合そのものは保持されていない |
| **barline CNN** D27（`assets/model-cache/barline_cnn/…`） | `f41a9b57…c5cd` | torchvision EfficientNet-B0 `IMAGENET1K_V1`（`efficientnet_b0_rwightman-7f5810bc.pth`、timm から移植） | evaluation2 5 曲の候補切り抜き（現行 producer）と、**DeepScoresV2 dense** の切り抜き 15,417 行 | #296 diagnostic_27 の summary（`initialization: torchvision ImageNet only`）。ローカル source checkpoint の hash が production と一致。DeepScoresV2 の手元アーカイブは Zenodo（doi:10.5281/zenodo.4012193、**CC BY 4.0**）の `ds2_dense.tar.gz` と md5 一致 |
| **SR x4**（`app/models/sr_x4/`） | `3b6b37a3…a1a6` | ランダム | 手続き的な合成データのみ | #533 §0.11。manifest・配布 manifest・portable の規則で同じ bytes を確認 |
| HOMR SegNet 308（HOMR 初期化） | `60f49549…fa83` | — | DeepScoresV2（上流 FAQ） | #504 §0.10。transformer は取得・同梱しない |
| PP-OCR ONNX（rapidocr / rapidocr-onnxruntime wheel 同梱） | wheel 内 | — | PaddleOCR | rapidocr 3.10.0 の `MODEL_LICENSES.md`：重みは Baidu/PaddleOCR、Apache-2.0 |

**初期化重みの実測確認**：本番 checkpoint と上記 ImageNet 重みの畳み込み層を比較し、相関の中央値は
ResNet18 0.9987、EfficientNet-B0 0.9992（ランダム初期化との対照は約 0.003）。両 checkpoint がこの ImageNet 重みからの
fine-tune であることは確定した。

**evaluation2 の楽譜**（5 曲。いずれもヴィオラ・パート）：Shostakovich「祝典序曲」「交響曲5番」、Sibelius
「ヴァイオリン協奏曲」、Prokofiev「交響曲1番」「交響曲5番」。PDF の producer はオフィス複合機（KONICA MINOLTA、RICOH）または
`tiff2pdf` で、紙のパート譜をスキャンしたものとみられる。**入手元（購入・レンタル・図書館等）と、その契約上の複製・利用条件はリポジトリに記録がない。**

### 2.2 初期化重みの条件

| 初期化重み | 上流の表示 | 判断 |
| --- | --- | --- |
| ResNet18 `IMAGENET1K_V1`（PyTorch が学習） | torchvision のコードは BSD-3-Clause。ドキュメントは「事前学習モデルは学習データ由来の独自の条件を持ちうる。用途に応じた許可の有無は利用者の責任で判断」とのみ記載。重み個別のライセンス表示はない | 違反を示す条件は見当たらない。ImageNet の利用条件が派生重みに及ぶかは未確定（法的判断） |
| EfficientNet-B0 `IMAGENET1K_V1`（timm の作者が学習、torchvision が移植） | timm README：「ImageNet は非商用の研究目的に限り公開された。……ImageNet で学習した私のモデルは研究目的で、**元のデータセットのライセンスが重みに適用されると想定すべき**。商用製品で使う場合は法的助言を」 | 上流作者が非商用条件の想定を明示している。**商用・公開配布では法的判断が必要**。非商用の評価目的の内部試用は、この想定の範囲と読める余地がある |
| ImageNet の利用条件本文 | 公式サイト（image-net.org）にこの環境から接続できず、今回は本文を取得していない | 本文の確認は §5 の必要資料 |

自前で学習したことは、初期化重みと学習データの条件を消さない。一方、ImageNet の画像そのものは重みに含まれず、当方は
ImageNet データセットの利用契約の当事者でもない。**事前学習重みの利用だけを理由に違反・再学習必須とは判断しない。**

### 2.3 楽譜・GT の条件

- 学習に使ったのは楽譜ページの切り抜き（入力）と first-party のラベル。配布する重み（2値分類器）から楽譜の表現を再生できるわけではない。
- 作曲者の没年：Prokofiev 1953、Sibelius 1957、Shostakovich 1975。日本では Shostakovich の作品は保護期間中。
- 日本の著作権法 30 条の 4（情報解析）の適用、学習用複製と重み配布の関係、**スキャン元の楽譜に付いた契約条件（レンタル譜の複製禁止等）**は、事実の確認と法的判断が必要（§5）。
- DeepScoresV2（CC BY 4.0）は商用を含め利用可。帰属表示を compliance bundle と `THIRD_PARTY_NOTICES.md` 案に入れた。

### 2.4 モデル別の判定

| 重み | 試用（同一組織・評価目的） | 公開配布（main の source・release asset） |
| --- | --- | --- |
| SR x4 | **cleared**（first-party。#505 適用で AGPL） | 同左 |
| HOMR SegNet 308 | **cleared_with_notice**（AGPL、DeepScoresV2 帰属） | 受領者が取得（当方は配布しない） |
| PP-OCR ONNX | **cleared_with_notice**（Apache-2.0、MODEL_LICENSES.md を同梱） | 受領者が取得 |
| MMR | **permission_needed**：オーナーによる受領者への許諾（例：評価目的に限定）と、スキャン入手条件の確認 | **legal_interpretation_needed**：ImageNet 由来初期化と楽譜由来の学習データ。置換するなら §6.2 |
| barline CNN | **legal_interpretation_needed**：上流作者の非商用想定（EfficientNet-B0）＋上記 MMR と同じ確認。非商用の評価試用であることをオーナーが確認し、残るリスクを受け入れるなら許諾付きで渡す判断はオーナーに委ねる | **legal_interpretation_needed** → 解消には §6.2 の置換が最も確実 |

なお MMR 重みは 2026-01-12 から公開リポジトリに、barline CNN は GitHub release に、ライセンス表示なし（＝許諾なし）で既に置かれている。
これは許諾の根拠にならない（#505 では NotLicensed として扱う）。

## 3. Windows 限定試用：構成物ごとの判定

**根拠の範囲**：`tools/windows_portable/requirements-cu126.txt` の固定版に対応する **win_amd64 wheel 57 件**（各 index の
SHA-256。中身は HTTP range で一覧化し、ライセンス・通知ファイルと DLL の版情報を実物から取得）と、
python-build-standalone `cpython-3.12.12+20260211`（Windows、`c38fba3a…`）。Linux image の #504 台帳は流用していない。
**Windows で実際にビルドした `build_manifest.json` ではまだ照合していない**（Windows 担当の検証中。§7）。

照合結果（擬似 manifest 24,906 ファイル）：審査済み規則のない配布物・DLL・モデル **0 件**、ブロック **5 件**。

| 構成物 | 条件 | 判定 | 根拠・残作業 |
| --- | --- | --- | --- |
| PDFScoreBar（`app/`、`launcher/`、SR 重み） | AGPL-3.0-or-later（決定済み・未付与） | **permission_needed** | #505。受領者は許諾を持たない。正式適用、または試用者への書面の個別許諾をオーナーが決める |
| MMR / barline CNN 重み | §2 | **permission_needed** / **legal_interpretation_needed** | §2.4 |
| CPython 3.12.12（OpenSSL、SQLite、libffi、Tcl/Tk、`vcruntime140*.dll`） | PSF-2.0 ほか。`python/LICENSE.txt` に同梱物と Microsoft Distributable Code の条件 | cleared_with_notice | 同梱の `LICENSE.txt` を保持。**PBS の release tag を build manifest が記録していない**（版の特定は `python312.dll` 等の hash による） |
| Microsoft VC++ ランタイム（`msvcp140*`、`vcomp140`、`vcruntime140*`） | Visual Studio Distributable Code | cleared_with_notice | 未改変、Windows 上でのみ使用 |
| 一般の Python パッケージ（49 件。CPython 同梱の pip を含む） | MIT/BSD/Apache-2.0/PSF/MPL-2.0 | cleared_with_notice | dist-info の本文を bundle にコピー |
| flatbuffers、rapidocr-onnxruntime、types-Pillow | Apache-2.0（wheel に本文なし） | cleared_with_notice | Apache-2.0 本文を補う（収集済み） |
| PyMuPDF 1.26.4 / MuPDF | AGPL-3.0 | cleared_with_notice | wheel の `COPYING` は1行のみ。AGPL 全文、**対応ソース**：PyMuPDF sdist（`be13a066…`）と、その `setup.py` が固定する MuPDF 1.26.7 source（`52014fce…`）を収集済み |
| HOMR `457e7c65`（ビルド時に改変） | AGPL-3.0 | cleared_with_notice | 上流 source（`41511b37…`）＋ `app/docker/patch_homr_onnx_provider.py`（改変）＋ `init_homr_segnet.py`。改変表示は THIRD_PARTY_NOTICES 案 |
| OpenCV の FFmpeg DLL（`opencv_videoio_ffmpeg*.dll` ×2） | LGPL-2.1 | cleared_with_notice | 未改変・置換可能な別 DLL。書面の申し出（3年）を用意。**申し出を守れるよう、受け渡し前に該当 source を取得・保持する** |
| TinyCC 0.9.28rc（triton-windows の `tcc.exe`、`libtcc.dll`） | LGPL-2.1 | cleared_with_notice | wheel には MIT 本文しかない。LGPL 本文と書面の申し出を補う。上と同じく source の取得・保持が必要 |
| NVIDIA CUDA 12.6 DLL（cudart、cuBLAS/cuBLASLt、cuFFT/cuFFTW、cuRAND、cuSOLVER、cuSPARSE、NVRTC、nvJitLink、CUPTI、NVTX、nvJPEG、libdevice） | CUDA EULA 12.6 **Attachment A に Windows 版が列挙** | cleared_with_notice | §1.1.2（実質的な追加機能、アプリ経由のみ、EULA と整合する受領条件、不遵守の通知）。**torch / torchvision の wheel には NVIDIA の本文がない**ため EULA 本文を補う（収集済み） |
| NVIDIA cuDNN 9.10.2.21（`cudnn*64_9.dll`） | cuDNN SLA：runtime の `.so`/`.dll` は再配布可 | cleared_with_notice | SLA 本文を補う（最新版の本文。対象版との差は §5） |
| **NVIDIA の非列挙ファイル**：`ptxas.exe`、`cuda.lib`、`cuda.h`（triton-windows）、`nvperf_host.dll`（Nsight Perf SDK）、`cusolverMg64_11.dll`（torch） | Attachment A に Windows 版の記載なし。§2.3 の「未改変なら再配布可」は Linux/FreeBSD 向けのみ | **legal_interpretation_needed** | 解消策は §6.1（除外）。`ptxas.exe` は本番 SR の `torch.compile`（triton）に必要 |
| **Intel OpenMP**（`libiomp5md.dll` FileVersion 20260213、`libiompstubs5md.dll`） | Intel EULA for Developer Tools（2024-08）。§2.1.D(2) 受領者に逆アセンブル禁止の契約を課す、§3.1(x) Reciprocal OSS 化の禁止 | **legal_interpretation_needed** | wheel に本文なし（intel-openmp 2026.2.0 から本文を収集）。AGPL 製品フォルダ内での同梱と両立するか、対象版の EULA 版の確認 |
| torch / torchvision 同梱の libuv、zlib 1.2.3、libjpeg-turbo、libpng、libwebp | MIT / Zlib / IJG・BSD / libpng / BSD | cleared_with_notice | wheel に本文なし。上流の本文を補う（収集済み。版は最新の本文） |
| ONNX Runtime GPU 1.24.4 | MIT ＋ `ThirdPartyNotices.txt` | cleared_with_notice | TensorRT は同梱しない（provider DLL は ORT のコード） |
| DejaVu Sans Bold | Bitstream Vera / DejaVu | cleared_with_notice | `COPYRIGHT.fonts-dejavu-core` を隣に同梱 |

### 3.1 compliance bundle の方式

`app/`（main と同一の 135 件）や `verify --full` の対象を変えないため、**portable フォルダの外に隣接する bundle** とした。

- 判定データ：[`windows_portable_components.json`](windows_portable_components.json)（配布物・ファイル規則→構成物→判定・義務・補う本文）。
- 検査・生成：`tools/licensing/portable_compliance.py`
  - `check <folder>/runtime/build_manifest.json`：manifest の全配布物・全 DLL/EXE/PYD/モデル/フォントが審査済みの規則に当たらなければ、版が審査時と違えば、モデルの hash が違えば **error（exit 2）**。判定が cleared でない構成物、補う本文が未収集のものは **blocked（exit 1）**。
  - `bundle <folder> <隣の新ディレクトリ> --supplemental-dir <非公開資料>`：フォルダ内のライセンス本文（manifest の hash を照合してコピー）、補う本文・対応ソース、生成した `THIRD_PARTY_NOTICES.md`・`SOURCE.md`、**`build_manifest.json` の SHA-256 と tree digest に結び付けた** `COMPLIANCE_REPORT.json`、`SHA256SUMS`。フォルダ内への出力は拒否する。
- 補う本文と対応ソースは非公開の作業領域に収集済み（§7）。

## 4. main 最小配布

### 4.1 当方が配布するもの

manifest 選定のソース 135 件（#550 rc1）。第三者で当方が配布するのは vendored の SR コード（Apache-2.0 / BSD-3-Clause、本文・改変表示を同梱済み）と、
HOMR の短い引用断片（`docker/patch_homr_onnx_provider.py`）だけ。HOMR、PyPI、NVIDIA、Ubuntu の部品は受領者の build が上流から取得する（#504 §0.10.5 方式 A）。

### 4.2 準備した非公開の適用パッケージ（#505）

旧パッケージ（base `04c16674`）を現行 source `a757211a` に適用し直し、リモートのない隔離クローンで検証した。

| 項目 | 結果 |
| --- | --- |
| 適用 | `docs/MINIMAL_MAINLINE_SURFACE{,.ja}.md` の件数行だけ衝突、解決 |
| 修正 | `reuse lint` 不合格2点（vendored `upsampler.py` の `BSD-3-Clause` 本文が `LICENSES/` にない、テスト内の文字列が SPDX 式と誤認）を修正。配布 manifest 135 → 143 |
| 内容の更新 | `THIRD_PARTY_NOTICES.md` を #533 以降の構成（BasicSR・Real-ESRGAN 重み・transformer なし）にし、§2 の初期化重みと DeepScoresV2 の帰属を追記。`NOTICE` に SR 重みは first-party、MMR と barline CNN は NotLicensed と明記 |
| 検証 | `reuse lint` Passed、surface check Passed、`materialize`/`check` Passed（143 件）、関連 pytest 99 passed |
| 未実施 | wheel・runtime fingerprint・Docker 再ビルド・smoke（`pyproject.toml` の変更で fingerprint が変わるため、適用する凍結 source で #505 G7 として実施） |

### 4.3 配布形態の別

- **ソース配布（既定）**：上記で第三者分は足りる。Ubuntu の GPL/LGPL、NVIDIA の条件、PyMuPDF の対応ソースは当方の配布義務にならない。
- **Docker image を配布する場合**（未選定）：#504 §0.8.2/§0.8.3 の Ubuntu 対応ソース、NGC/CUDA の条件と法的確認事項がそのまま残る。選ぶなら別途判定する。

## 5. 法的判断が必要な論点と必要資料

| # | 論点 | 必要な資料・事実 |
| --- | --- | --- |
| L1 | ImageNet で学習した初期化重み（特に timm 由来 EfficientNet-B0）の条件が、fine-tune した重みの配布に及ぶか | ImageNet Terms of Access の本文（今回取得不能）、timm README の該当節、torchvision の注記、試用・公開の目的（非商用評価か） |
| L2 | 楽譜スキャンを学習に使った重みの配布（日本の著作権法 30 条の 4、契約） | **オーナーが持つ事実**：各スキャンの元資料の入手経路と契約（購入・レンタル・団体所有、複製・電子化の可否）、スキャン実施者 |
| L3 | Windows 向け NVIDIA の非列挙ファイル（`ptxas.exe`、`nvperf_host.dll`、`cusolverMg64_11.dll`、`cuda.lib`、`cuda.h`）の再配布 | CUDA EULA 12.6（収集済み）、triton-windows / PyTorch がこれらを配布している根拠、必要なら NVIDIA への確認 |
| L4 | Intel OpenMP EULA と AGPL 製品フォルダ内の同梱（受領者契約での逆アセンブル禁止の付け方、Reciprocal OSS 条項） | Intel EULA（収集済み）、対象 DLL 版に対応する EULA 版 |
| L5 | NVIDIA / Intel の独自条件の部品と AGPL 結合物の同時配布（#504 §0.8.3 の継続） | AGPL §1 System Libraries、§10、各 EULA |
| L6 | cuDNN 9.10.2.21 に適用される SLA の版 | 収集した SLA は「latest」。対象版の SLA |

## 6. 技術的な解消策（実施にはオーナー承認と事前の回帰契約）

### 6.1 Windows の NVIDIA 非列挙ファイルを除く

- `nvperf_host.dll`、`cusolverMg64_11.dll`：torch の DLL（`torch_cpu`、`cusolver64_11`、`cupti64`）を調べると、`cusolverMg64_11.dll` はどこからも名前で参照されず、
  `nvperf_host.dll` は CUPTI のプロファイラ経路からだけ参照される（静的な文字列検査。`torch_cuda.dll` は ASCII のみ確認）。
  ビルダーで除外し、**Windows の GPU 実機で preflight・E2E を確認**できれば解消する。
- `ptxas.exe`、`cuda.lib`、`cuda.h`（triton-windows）：本番設定 `sr_compile_mode: reduce-overhead` の `torch.compile` が使う。
  Windows だけ SR を eager にし triton-windows を同梱しない構成にすれば、これらと TinyCC（LGPL）が消える。
  **回帰契約（事前に固定）**：(a) Linux GPU で SR x4 の出力を eager と compile で Full68 の 73 ページ比較し、byte 一致なら下流は不変。
  (b) 一致しなければ #533 §0.11.1 と同じ Full68 replay（対照比で FP 増なし、新規 FN なし、TP 減なし、小節数・番号列の全ページ一致）。
  (c) Windows 実機で GPU E2E。処理時間は記録のみ（#533 の計測で eager は 1 ページ約 8.5 秒、compile は 2 ページ目以降約 6.9 秒）。
  **今回は実行していない**：GPU を Windows の E2E 検証と共有しているため、検証中の作業を乱さない。

### 6.2 MMR / barline CNN の置換（公開配布で L1/L2 を避ける場合）

ランダム初期化、または権利が明確なデータ（DeepScoresV2、合成データ）だけでの事前学習から再学習し、学習データから
条件の確認できない楽譜スキャンを外す。どちらも認識性能が変わり得るため、**結果を見る前に**次を固定する。

| 対象 | 契約 |
| --- | --- |
| barline CNN | 現行 D27 を対照に、#522/#533 と同じ Full68 replay（保持済み x1 baseline、本番の consensus・番号付け、閾値の変更なし）で FP 増なし・新規 FN なし・TP 減なし・全ページの小節数リストと番号列が一致。閾値は VAL だけで選び、TEST・Full68 を選択に使わない（#296 の段階ゲート） |
| MMR | 現行 C1（#545）の本番出力を同じハーネスで再計算した対照に対し、Full68 の MMR 検出（ページごとの span と rest 数）と番号列が一致、または差分ごとに GT で改善・同等であること。悪化が1件でもあれば不採用 |
| 共通 | 学習データの出典・条件を記録（評価に使うスキャンは学習に使わない）。不合格なら現行モデルを維持し、§2.4 の判定のまま |

評価用のスキャンを学習から外すと、評価（Full68）と学習が同じ楽譜に依存しなくなる利点もある。一方、精度が契約を満たす保証はない。

## 7. 受領者の区分

| 区分 | 必要なもの |
| --- | --- |
| 開発者自身の Windows 機能検証（#551/#546、進行中） | 第三者への複製物の提供がないため配布義務は発生しない。継続してよい |
| 同一組織の 1〜2 人への試用（#508） | **配布にあたる。少人数でも義務は免除されない。** §3 の bundle、first-party と重みの許諾（オーナー）、§5 の判断、受領者の利用条件（評価目的、Intel DLL の条項、NVIDIA EULA と整合する条件）への受領者の同意 |
| 公開（main、release asset） | 上記に加えて L1/L2 の判断、または §6.2 の置換 |

## 8. 今回の検証と証拠

| 検証 | 結果 |
| --- | --- |
| `tests/test_issue553_portable_compliance.py`（使い捨て `pdfscore_pytest_validation:e7a2045e207c`） | 10 passed |
| `check_repository_surface.py`、ruff check / format | Passed |
| wheel 実物による擬似 manifest の照合 | error 0、blocked 5（§3） |
| #505 パッケージの隔離適用（§4.2） | reuse lint・surface・materialize・pytest 99 Passed |
| Windows 実ビルドでの `check`/`bundle` | **Not run**（Windows ビルド待ち） |
| §6.1 eager/compile の比較、§6.2 の再学習 | **Not run**（承認待ち。GPU 共有） |

非公開の証拠（git 管理外）：`logs/issue553/`（`windows-inventory/`：wheel 一覧・抽出したライセンス本文・CPython 一覧・生成スクリプト、
`upstream-terms/`、`model-lineage/`：初期化重みとの比較・lineage 記録、`compliance-private/supplemental/`：補う本文と対応ソース＋`SHA256SUMS`、
`compliance-rehearsal/`、`license-package-a757211a/`：#505 の適合版パッケージ、`validation/`）。

## 9. オーナーの判断事項

1. **Windows の NVIDIA 非列挙ファイル**：§6.1 の除外（eager SR）を進めるか、法的確認・NVIDIA への確認を取るか。
2. **MMR / barline CNN**：試用では評価目的に限った許諾で渡すか（スキャンの入手条件の確認を含む）、置換（§6.2）を先に行うか。公開配布ではどちらにするか。
3. **Intel OpenMP**：受領者条件に Intel DLL の条項を入れる形で進めるか、法的確認を取るか。
4. **first-party の許諾**：#505 の正式適用（main）と、試用者への書面の個別許諾のどちらで試用を行うか。
5. 上記の後、Windows 実ビルドの `build_manifest.json` で `portable_compliance.py check` → `bundle`、LGPL の source 取得・保持、受け渡し手順と SHA256 を確定してから、試用の Go/No-go。
