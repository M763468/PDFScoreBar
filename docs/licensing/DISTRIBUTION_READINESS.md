# 配布候補ごとの権利・通知・対応ソースの判定（#553）

[#553](https://github.com/M763468/PDFScoreBar/issues/553) の記録。原文は日本語（正本）。英語版は未作成。
判定日 **2026-11-23**、Windows受入・試用ビルド限定の許諾を反映 **2026-11-25**。

> **法的助言ではない。** ライセンス本文・上流の表示・実物（wheel、checkpoint、データ）から確認した事実と、
> それに基づく分類を記録する。「法的判断が必要」とした論点は推測で埋めず、§5 に必要資料とともに示す。
> この文書自体はライセンスを付与しない。試用ビルド限定の許諾本文は compliance bundle 内の `LICENSE` / `FIRST_PARTY_NOTICE.md` にある。リポジトリ全体の LICENSE 公開は別判断（#505）。

前提として再利用した記録：[#504 監査](THIRD_PARTY_LICENSE_AUDIT.md) §0.8–§0.11（Linux image の Python・OS・NVIDIA、
HOMR、BasicSR/GFPGAN の除去、SR 重みの first-party 化）、[#505](REPOSITORY_LICENSE_OPTIONS.md)（first-party は
AGPL-3.0-or-later を採用済み。2026-11-24に試用ビルド限定で許諾済み、リポジトリへの正式適用は未実施）。これらを再調査せず、**配布物ごとに未確認だった事実**だけを追加で確認した。

## 0. 判定の対象

| 配布候補 | 固定値 | 当方が渡すもの |
| --- | --- | --- |
| **Windows 限定試用**（#508、同一組織の 1〜2 人） | portable source `33836ac5eaf3af70eecfc5c56710148d8822bf89`、build manifest SHA-256 `1173dfb44654f25ee2f7b3a3b99e60a22a57e67cc10756055e0540fa84a00e90`（PR #555。旧 `b1425154` から `app/` は不変） | フォルダ一式：`app/`（main 最小配布 135 件 + provenance）、`launcher/`、CPython と第三者 wheel（ネイティブ DLL を含む。**triton-windows と §3 の除外ファイルを除く**）、barline CNN 重み、DejaVu フォント |
| 同上・**受領者が初回セットアップで直接取得** | `PDFScoreBar.cmd setup` | `triton-windows==3.8.0.post29`（PyPI から受領者のフォルダ内へ。NVIDIA `ptxas.exe`・`cuda.h`・`cuda.lib` と TinyCC を含む） |
| **main 最小配布**（#550 rc1） | source `a757211a9e02e5b3c9626db6a188227dbcd1738b`、candidate `9bb4f416…` | **ソースのみ**（manifest 選定 135 件。MMR 重みと first-party SR 重みを含む）。第三者部品・HOMR・NVIDIA は受領者の `docker build` が上流から取得。barline CNN は GitHub release asset から取得 |

Docker image の配布は選定されていない（§4.3）。

## 1. 結論

| 配布候補 | 判定 | 理由（詳細は §3・§4） |
| --- | --- | --- |
| **Windows 限定試用** | **GO-ready**（試用GOの正式判断・受領者同意・受渡しは#508で管理）。固定manifestの最終照合はerror 0 / blocked 0 / `handoff_ready=true`、Windows実機受入Passed | NVIDIA 非列挙ファイルは非同梱に変更。MMR・barline CNN は現行 checkpoint を維持し、出典・条件をNOTICEに記録（§2）。学習用楽譜画像・PDF・学習用切り抜きは配布しない。両モデルに固有の明示的な配布禁止条項は今回特定されておらず、独立したブロッカーとはしない。2026-11-24に本試用ビルドに限定してfirst-party AGPL-3.0-or-laterを許諾済み（#505） |
| **main 最小配布** | **判断待ち**（#505 正式適用） | 第三者バイナリは配布しない。MMR重み・barline CNN release assetの出典と学習条件を記録し、現行モデルを維持する。必要な第三者通知と対応ソースの準備は§4。モデル固有の禁止条項が新たに確認された場合のみ追加対応する |

Windows試用ビルドは技術・complianceゲートを通過し、**オーナーの#508試用GO判断と受領者の条件同意・受渡しだけが残る**。`main`昇格、リポジトリ全体へのLICENSE公開、tag/releaseは未実施。今後は#550で`main`昇格と同時にライセンスを適用する方針（オーナー指示2026-11-25）で、これらを今回の試用許諾と混同しない。

## 2. モデル重みの lineage と判断

**今回のモデル重みの配布方針（2026-11-24）：** 学習に用いた楽譜PDF・ページ画像・切り抜きは配布しない（オーナー確認）。MMR / barline CNN は本人によるfine-tune済みcheckpointを現行のまま使用する。初期化重みの元と利用上の注意、DeepScoresV2の帰属はNOTICEへ反映し、確認されていない禁止を推定してモデル置換・再学習を配布前提にしない。この分類は第三者が保有する権利を消滅させる判断ではなく、**試用ビルドについては#505でfirst-party部分の許諾が実際に適用済み**であり、mainへの一般的なLICENSE公開は将来の別作業である。

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
| EfficientNet-B0 `IMAGENET1K_V1`（timm の作者が学習、torchvision が移植） | timm README：「ImageNet は非商用の研究目的に限り公開された。……ImageNet で学習した私のモデルは研究目的で、**元のデータセットのライセンスが重みに適用されると想定すべき**。商用製品で使う場合は法的助言を」 | 注意書きは尊重して出典を表示する。ただし、PDFScoreBar のfine-tune後checkpointに具体的に適用される再配布禁止条項は本調査では特定されていない。注意書きだけで配布禁止・再学習必須とはしない。具体的な拘束条件が判明した場合に限り用途別に再評価する |
| ImageNet の利用条件本文 | 公式サイト（image-net.org）にこの環境から接続できず、今回は本文を取得していない | 確認できた範囲ではfine-tune後checkpointの配布禁止を特定できていない。未取得という事実だけを自動ブロッカーにしない |

自前で学習したことは、初期化重みと学習データの条件を消さない。一方、ImageNet の画像そのものは重みに含まれず、当方は
ImageNet データセットの利用契約の当事者でもない。**事前学習重みの利用だけを理由に違反・再学習必須とは判断しない。**

### 2.3 楽譜・GT の条件

- 学習に使ったのは楽譜ページの切り抜き（入力）と first-party のラベル。**配布物に学習用の楽譜PDF・ページ画像・切り抜き・学習用GTは含めない**。配布する重みは分類器であり、楽譜画像を復元する用途ではない。
- 作曲者の没年：Prokofiev 1953、Sibelius 1957、Shostakovich 1975。日本では Shostakovich の作品は保護期間中。
- 日本の著作権法30条の4には、非享受目的の情報解析のための著作物利用に関する規定がある（ただし例外あり）。学習元に具体的な契約制限がある場合はその内容を個別確認する。**入手履歴が残っていないという事実だけで、完成した分類器の配布禁止や再学習必須とは扱わない**（§5）。
- DeepScoresV2（CC BY 4.0）は商用を含め利用可。帰属表示を compliance bundle と `THIRD_PARTY_NOTICES.md` 案に入れた。

### 2.4 モデル別の判定

| 重み | 試用（同一組織・評価目的） | 公開配布（main の source・release asset） |
| --- | --- | --- |
| SR x4 | **cleared**（first-party。#505 適用で AGPL） | 同左 |
| HOMR SegNet 308 | **cleared_with_notice**（AGPL、DeepScoresV2 帰属） | 受領者が取得（当方は配布しない） |
| PP-OCR ONNX | **cleared_with_notice**（Apache-2.0、MODEL_LICENSES.md を同梱） | 受領者が取得 |
| MMR | **cleared_with_notice**（モデル固有の禁止条件は未特定、現行重み維持）。ResNet18初期重み・first-party学習・楽譜非同梱を表示。**試用ビルドでは#505の2026-11-24付許諾が適用済み。main公開には別途適用** | 同左。上流の具体的な拘束条件が新たに判明した場合のみ対象を特定して再評価 |
| barline CNN | **cleared_with_notice**（モデル固有の禁止条件は未特定、現行D27重み維持）。EfficientNet-B0/timmの注意事項とDeepScoresV2のCC BY 4.0帰属を表示。**試用ビルドでは#505の2026-11-24付許諾が適用済み。main公開には別途適用** | 同左。注意書きは保持するが、明示的な不適合がない限り置換を配布前提としない |

なお MMR 重みは 2026-01-12 から公開リポジトリに、barline CNN は GitHub release に、ライセンス表示なし（＝許諾なし）で既に置かれている。
これらの過去の公開だけでは許諾の根拠にならなかったが、今回の試用ビルドには2026-11-24付のfirst-party許諾を別途適用済み（#505）。

### 2.5 オーナーに確認していただく事項（楽譜スキャン）

以下は過去の学習記録を補完するための任意の確認事項。**S1〜S4の完全復元を配布GOの必須条件としない**。具体的な複写禁止契約・第三者権利侵害等を示す事実が判明した場合だけ、その対象について対応する。

| # | 確認事項 | 対象 |
| --- | --- | --- |
| S1 | evaluation2 の 5 曲（Shostakovich「祝典序曲」「交響曲5番」、Sibelius「ヴァイオリン協奏曲」、Prokofiev「交響曲1番」「交響曲5番」、いずれもヴィオラ・パート）の紙の楽譜の入手経路：購入／出版社・代理店からのレンタル／所属団体の所有／図書館等 | MMR、barline CNN |
| S2 | 入手時の契約・注意書きで、複写・スキャン・電子化・社外持ち出しが禁止または制限されていたか（レンタル譜は複製禁止の条件が多い） | 同上 |
| S3 | スキャンを行った人・機器（PDF の producer は KONICA MINOLTA、RICOH の複合機と tiff2pdf）と、その目的（個人の練習用か、団体の業務か） | 同上 |
| S4 | 旧 `data/evaluation/pdfs/target.pdf`（MMR の学習に 1 ページ使用）の出典 | MMR |
| S5 | 試用の目的が商用か非商用の評価か（ImageNet 由来の初期化重みの扱いに関係。§2.2） | MMR、barline CNN |

上記は出典情報の補完用であり、過去の履歴不明だけを理由に現行モデルを差し替えない。**実際に適用される具体的な禁止条項・契約違反が特定された場合**に、該当する行為・ファイル・条項を示して対応を判断する（代替策は§6.2）。

## 3. Windows 限定試用：構成物ごとの判定

**根拠の範囲**：`tools/windows_portable/requirements-cu126.txt` の固定版に対応する **win_amd64 wheel 57 件**（中身は HTTP range で一覧化し、
ライセンス・通知ファイルと DLL の版情報を実物から取得）、python-build-standalone `cpython-3.12.12+20251209`（実ビルド `win553` の `python/BUILD` で確認、`pip==25.3` 同梱、`python/LICENSE.txt` は `20260211` と SHA-256 一致）、および実ビルド `win553`（source `b1425154`、manifest `eb256330…`、25,490 ファイル）の実 dist-info / metadata / ライセンス本文（`setuptools==84.2.1`、`homr==0.1.0`、`pip==25.3` を含む）。
Linux image の #504 台帳は流用していない。新候補 SHA（`33836ac5…`）の実機受入後に、最終フォルダで `check` → `bundle` を行う（§8）。

**配布方式（#553、2026-11-24）**：`torch.compile`/Triton は維持し、当方の再配布の根拠が確認できない物は渡さない。

| 区分 | 対象 | 方法 |
| --- | --- | --- |
| **受領者が直接取得** | `triton-windows==3.8.0.post29`（MIT。NVIDIA `ptxas.exe`・`cuda.h`・`cuda.lib`、TinyCC を含む） | `PDFScoreBar.cmd setup` が PyPI から受領者のフォルダの `addons\` にダウンロード・インストール（`tools/windows_portable/user_setup.py`。PR #552 の上に積んだ topic branch `feat/issue553-portable-user-setup`）。triton-windows の README は CUDA ツールチェーンと TinyCC の同梱を述べるが、NVIDIA ファイルの再配布の根拠は示していない。当方は再ホストしない |
| **ビルドで除外**（使わない） | `torch\lib\nvperf_host.dll`（Nsight Perf SDK）、`torch\lib\cusolverMg64_11.dll`、`cv2\opencv_videoio_ffmpeg4110_64.dll`・`…4140_64.dll`（FFmpeg、LGPL-2.1） | torch の DLL はどれも前 2 者を推論で読み込まない（CUPTI のプロファイラ経路だけが `nvperf_host` を参照）。FFmpeg は `cv2.VideoCapture`/`VideoWriter` 用で、PDFScoreBar と HOMR は動画を使わない。**Windows 実機の GPU 動作で確認する** |
| **提供者が同梱** | 下表の残り | 通知・本文・対応ソースを compliance bundle に入れる |

Attachment A に名前がないことは「再配布禁止」を意味しない。ただし当方が再配布してよい根拠を EULA から示せないため、**問い合わせではなく配布方式で**解消した。

最終照合結果（`win553f_build_manifest.json`、25,490ファイル、source `33836ac5`、manifest `1173dfb4…`）：**error 0 / blocked 0 / `handoff_ready=true`**（オーナーによる当該ビルド限定許諾を適用後）。このgrantは正確なmanifest SHA-256に結び付け、別ビルドへ自動転用しない。旧 `win553`（`b1425154`）の許諾前照合はerror 0 / blocked 1であり、履歴である。
履歴：旧判定（モデル再分類前・模擬 manifest 24,564 ファイル）は error 0 / blocked 3、旧構成（`93e2c2b2` 相当）は「同梱してはならない物を含む」として 6 件ブロック。

| 構成物 | 条件 | 判定 | 根拠・残作業 |
| --- | --- | --- | --- |
| PDFScoreBar（`app/`、`launcher/`、SR 重み、`pdfscorebar_addons.pth`） | AGPL-3.0-or-later（2026-11-24、manifest `1173dfb4…`の試用ビルド限定） | **cleared_with_notice** | #505でオーナーが許諾済み。`LICENSE`・`FIRST_PARTY_NOTICE.md`・対応ソースを隣接bundleに同梱。mainの正式適用は別途 #550 とともに進める |
| MMR / barline CNN 重み | §2 | **cleared_with_notice**（モデル固有の再配布禁止は未特定） | First-party重みとしての出典・ImageNet初期化・DeepScoresV2帰属・学習用楽譜非同梱を通知。対象試用ビルド限定のfirst-party許諾は#505で適用済み |
| CPython 3.12.12（`python-build-standalone` `20251209`；OpenSSL、SQLite、libffi、Tcl/Tk、`vcruntime140*.dll`） | PSF-2.0 ほか。`python/LICENSE.txt` に同梱物と Microsoft Distributable Code の条件 | cleared_with_notice | 同梱の `LICENSE.txt` を保持 |
| Microsoft VC++ ランタイム（`msvcp140*`、`vcomp140`、`vcruntime140*`） | Visual Studio Distributable Code | cleared_with_notice | 未改変、Windows 上でのみ使用 |
| 一般の Python パッケージ（49 件。CPython 同梱の `pip 25.3` を含む） | MIT/BSD/Apache-2.0/PSF/MPL-2.0 | cleared_with_notice | dist-info の本文を bundle にコピー |
| `setuptools 84.2.1`（`torch==2.14.0+cu126` の実行時依存 `setuptools>=77.0.3` により PyPI から導入） | MIT（`_vendor` に MIT / Apache-2.0 / BSD-2-Clause / `autocommand 2.2.2` LGPL-3.0、`config/**/NOTICE` に `fastjsonschema` BSD-3-Clause・`validate-pyproject` MPL-2.0、ランチャー `cli/gui*.exe` は MIT） | cleared_with_notice | dist-info・`_vendor` の LICENSE 本文と `setuptools/config/**/NOTICE` を bundle にコピー。`autocommand` は未改変の pure-Python ソースのまま同梱されており、LGPL-3.0 が組み込む GPL-3.0 本文（`common/GPL-3.0.txt`）を補う |
| flatbuffers、rapidocr-onnxruntime、types-Pillow | Apache-2.0（wheel に本文なし） | cleared_with_notice | Apache-2.0 本文を補う（収集済み） |
| PyMuPDF 1.26.4 / MuPDF | AGPL-3.0 | cleared_with_notice | AGPL 全文、**対応ソース**：PyMuPDF sdist（`be13a066…`）と MuPDF 1.26.7 source（`52014fce…`）を収集済み |
| HOMR `457e7c65`（導入版 `0.1.0`、`POETRY_DYNAMIC_VERSIONING_BYPASS=0.1.0`、ビルド時に改変） | AGPL-3.0 | cleared_with_notice | 上流 source（`41511b37…`）＋ `app/docker/patch_homr_onnx_provider.py`（改変）＋ `init_homr_segnet.py` |
| NVIDIA CUDA 12.6 DLL（cudart、cuBLAS/cuBLASLt、cuFFT/cuFFTW、cuRAND、cuSOLVER、cuSPARSE、NVRTC、nvJitLink、CUPTI、NVTX、nvJPEG） | CUDA EULA 12.6 **Attachment A に Windows 版が列挙** | cleared_with_notice | §1.1.2（実質的な追加機能、アプリ経由のみ、EULA と整合する受領条件、不遵守の通知）。EULA 本文を補う。受領条件は下書き済み（`RECIPIENT_TERMS.md`） |
| NVIDIA cuDNN 9.10.2.21 | cuDNN SLA：runtime `.dll` は再配布可 | cleared_with_notice | SLA 本文（最新版）を補う |
| Intel OpenMP（`libiomp5md.dll` FileVersion 20260213、`libiompstubs5md.dll`） | Intel EULA for Developer Tools（2024-08）§2.1.D：製品の一部としての再配布を許可。受領者条件で逆アセンブル禁止を課す。§3.1(x) Reciprocal OSS 化の禁止 | cleared_with_notice | 受領者条件に Intel DLL 限定の条項を入れる（下書き済み）。DLL は torch（BSD）の依存で AGPL の作品に組み込まず再許諾しない。**残る点**：torch 同梱 build に対応する EULA 版の表示がない。必要なら同じ FileVersion・同サイズの `intel-openmp==2026.1.0` を setup で受領者に取得させる代替がある |
| torch / torchvision 同梱の libuv、zlib 1.2.3、libjpeg-turbo、libpng、libwebp | MIT / Zlib / IJG・BSD / libpng / BSD | cleared_with_notice | 上流の本文を補う（収集済み） |
| ONNX Runtime GPU 1.24.4 | MIT ＋ `ThirdPartyNotices.txt` | cleared_with_notice | TensorRT は同梱しない |
| DejaVu Sans Bold | Bitstream Vera / DejaVu | cleared_with_notice | `COPYRIGHT.fonts-dejavu-core` を隣に同梱 |
| triton-windows、`nvperf_host.dll`、`cusolverMg64_11.dll`、FFmpeg DLL | — | **exclude**（同梱しない） | 実ビルドに残っていれば照合ツールが blocked にする |

LGPL のバイナリ（TinyCC、FFmpeg）を当方は渡さなくなったため、LGPL の書面の申し出は不要になった。`setuptools` 同梱の `autocommand 2.2.2`（LGPL-3.0）は未改変の Python ソースコード（`.py`）のままフォルダ内に含まれており、LGPL-3.0 本文と組み込み先の GPL-3.0 本文を compliance bundle に添付する。

### 3.1 compliance bundle の方式

`app/`（main と同一の 135 件）や `verify --full` の対象を変えないため、**portable フォルダの外に隣接する bundle** とした。

- 判定データ：[`windows_portable_components.json`](windows_portable_components.json)。ライセンスは**配布物の版ごと**に審査し、個々の wheel・DLL の SHA-256 には依存しない（モデル重みとフォントは、版の取り違え・破損を防ぐため bytes を照合する）。`recipient_acquired` に受領者が取得する物を記録する。
- 検査・生成：`tools/licensing/portable_compliance.py`
  - `check <folder>/runtime/build_manifest.json`：審査済みの規則に当たらない配布物・DLL/EXE/PYD・モデル・フォント、モデル/フォントの bytes の差は **error（exit 2）**。cleared でない構成物、同梱してはならない物（`exclude`）、**版が審査時と違う配布物（ライセンスの再審査が必要）**、補う本文が未収集のものは **blocked（exit 1）**。互換版への更新でファイルの hash を登録し直す必要はない。
  - `bundle <folder> <隣の新ディレクトリ> --supplemental-dir <非公開資料>`：フォルダ内のライセンス本文（manifest の hash を照合してコピー）、補う本文・対応ソース・受領者条件、生成した `THIRD_PARTY_NOTICES.md`（受領者が取得する物の節を含む）・`SOURCE.md`、`build_manifest.json` の SHA-256 と tree digest に結び付けた `COMPLIANCE_REPORT.json`、`SHA256SUMS`。フォルダ内への出力は拒否する。

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

| # | 論点 | 状態・必要な資料 |
| --- | --- | --- |
| L1 | ImageNet 由来の初期化重み（特にtimm由来EfficientNet-B0） | READMEの利用上の注意をNOTICEで明示。対象checkpointへの具体的な禁止条項は未特定。注意書きや元データの条件が存在する可能性だけで配布をブロックしない。適用可能な拘束条件が判明した場合のみ再判定 |
| L2 | 楽譜スキャンを学習に使った重みの配布（日本の著作権法30条の4、契約） | **楽譜スキャン・学習用切り抜きは非同梱**。著作権法上の情報解析と個別契約は別の論点。具体的な不適合は未確認であり、過去の入手履歴未記録だけでモデル配布をブロックしない |
| L3 | Windows 向け NVIDIA の非列挙ファイルの再配布 | **配布方式で解消**（同梱しない）。受領者が PyPI から得る際の条件は受領者と配布元の間の問題として案内する |
| L4 | Intel OpenMP EULA と AGPL 製品フォルダ内の同梱 | 受領者条件で対応（§3）。対象 build の EULA 版は残る。代替あり |
| L5 | NVIDIA / Intel の独自条件の部品と AGPL 結合物の同時配布（#504 §0.8.3 の継続） | 受領者条件は NVIDIA/Intel のライブラリだけを対象にし、first-party と AGPL 部品には制限を加えない形で下書きした |
| L6 | cuDNN 9.10.2.21 に適用される SLA の版 | 収集した SLA は最新版。版ごとの差は未確認 |

## 6. 技術的な解消策

### 6.1 Windows の NVIDIA 非列挙ファイル（実装済み、Windows 実機確認待ち）

- 採用：triton-windows を受領者が初回セットアップで PyPI から取得（`torch.compile`/Triton は維持）、`nvperf_host.dll`・`cusolverMg64_11.dll`・FFmpeg プラグインはビルドで除外。
- 比較した案：(a) 対象 5 ファイルだけを wheel から取り出して置く案は、torch/triton の正規パッケージ構成から外れ、版の更新や修復が独自処理になる。(b) 公式パッケージ（triton-windows wheel）を丸ごと受領者がインストールする案は、通常の pip で検証・修復でき、ダウンロード 51 MB・展開 150 MB と軽い。**(b) を採用**。torch の 2 DLL は使わないため、取得させずに除外した（必要と判明すれば `nvidia-cusolver-cu12` / `nvidia-cuda-cupti-cu12` を setup で取得させる代替がある）。
- 第二案（この方式が成立しない場合のみ）：Windows だけ SR を eager にして triton を使わない。回帰契約（事前固定）：Linux GPU で eager と compile の SR 出力を Full68 の 73 ページで比較し、差があれば #533 §0.11.1 と同じ Full68 replay（FP 増なし、新規 FN なし、小節数・番号列の全ページ一致）。

### 6.2 MMR / barline CNN の置換（具体的な不適合が判明した場合だけの予備案）

現行のMMR・barline CNNは維持し、**権利の懸念だけで再学習を開始しない**。対象checkpointに適用される具体的な禁止条件が確認され、NOTICEや正規の利用条件の遵守では解決できない場合のみ、この置換手順を検討する。置換が必要となったときは、ランダム初期化または使用条件を満たす事前学習重み・データから学習し、評価基準を事前に固定する。

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
| 同一組織の 1〜2 人への試用（#508） | GNU GPL上、同一法人の内部利用か別の権利主体への提供かでconveyingの扱いが異なる。第三者の独自EULAは別途確認し、実際の配布形態に合わせて§3の通知・対応ソース、first-party許諾、受領者条件を適用する |
| 公開（main、release asset） | #505の正式な許諾適用、必要なNOTICE/対応ソース、配布物の実査。特定のモデルについて実際に拘束する禁止条件が確認された場合のみ§6.2等の対応を追加 |

## 8. 今回の検証と証拠

| 検証 | 結果 |
| --- | --- |
| 照合ツールと判定データのテスト（`tests/test_issue533_license_reduction.py` の #553 節） | Passed |
| 実 Windows ビルド manifest（`win553_build_manifest.json`、`eb256330…`、旧 source `b1425154`）での `portable_compliance.py check` | **error 0、blocked 1**（`pdfscorebar-first-party` #505 のみ、モデル固有 blocked 0、18 components、`handoff_ready=false`）。履歴：旧判定（`adf75cfe`）では error 1（`setuptools==84.2.1`）・blocked 3（`homr==0.1.0`、`pip==25.3`、`pdfscorebar-first-party`）、旧模擬 manifest は error 0・blocked 3 |
| 実 triton-windows 3.8.0.post29 wheel（PyPI、`937ba2ee…`）の取得・展開 | 必要 5 ファイルが存在（Linux 上で win_amd64 wheel を `--target` 展開） |
| setup の動作（portable 側 PR のテスト） | download/install/記録、再実行で再取得しない、wheel-dir、失敗・中断からの復旧、改ざん・版ずれ、移設 |
| #505 パッケージの隔離適用（§4.2） | reuse lint・surface・materialize・pytest 99 Passed（2026-11-23） |
| Windows実機受入（`33836ac5…`）と最終クリーンフォルダ照合 | **Passed**。5項目すべて合格（#553 comment 7130471211）。25,490ファイルのSHA-256一致・余剰0・欠落0・`verify --full`問題0（#553） |
| 最終manifest `1173dfb4…` のコンプライアンス照合・許諾・bundle | **Passed（2026-11-24の証拠）**。18 components、error 0 / blocked 0、`handoff_ready=true`、bundle 406ファイルの`SHA256SUMS`一致（PR #554 `de52307f`、#553 comment 7134015081）。本PRで追加する試用ガイドを収録したbundleの**再生成とSHA256SUMS照合は未実施** |

非公開の証拠（git 管理外）：`logs/issue553/`（`windows-inventory/`、`upstream-terms/`、`model-lineage/`、`compliance-private/supplemental/`（補う本文、対応ソース、`terms/RECIPIENT_TERMS.md` の下書き、`SHA256SUMS`）、
`compliance-rehearsal/`、`portable-setup/`、`license-package-a757211a/`、`validation/`）。

試用者向けの暫定手順は [Windows版限定試用ガイド](../windows_portable/TRIAL_GUIDE.md) に記す（日本語正本）。配布時には`portable_compliance.py bundle`が隣接bundleに`TRIAL_GUIDE.md`として収録する。既存のWindows portable本体とmanifestは変更しない。

## 9. オーナー判断と今後の作業（2026-11-25）

1. **試用ビルドの権利条件は適用済み**：#505のオーナー承認（2026-11-24）により案Aを適用。受領者名・期限を記載しない受領者条件も承認済み。対象は固定manifest `1173dfb4…` のWindows試用ビルドだけ。
2. **試用GO判断は#508で別途行う**：同意取得後にクリーンなフォルダ、compliance bundle、manifest SHAファイルを受け渡し、利用中のフィードバックは#508から個別Issueへ振り分ける。
3. **本PRのガイド・判定ツール修正**：日本語試用ガイドをbundleに追加し、first-party許諾を正確なmanifest SHAに限定する。新bundleの生成とfocusedテストはマージ前に検証する。
4. **mainへの昇格**：#550で別途進め、昇格と同時にリポジトリ全体のfirst-party LICENSEを適用する。試用ビルド限定のgrantをmain全体への公開許諾とみなさない。
