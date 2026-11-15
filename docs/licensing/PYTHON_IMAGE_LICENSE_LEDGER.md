# Python配布物の監査台帳（#504）

対象 image `sha256:71cbccf6d7f7bba3b96989f8043e1b6b991a3d90122bfe6afda0aae82d99610a`、99件。2026-11-15 の最終分類で更新した
（repository `develop@25d0dad7ac8f` と依存定義の差分なし。再ビルドはしていない）。詳細な全メタデータ、実ファイルのパスとSHA-256、VCSのdirect_url、
同梱ライセンス本文の分類、同梱shared library、条件別の措置は、ローカル `logs/issue504/environment-audit/final-20261115/python-license-ledger-20261115.json` を参照。
2026-11-13 の台帳 `logs/issue504/environment-audit/python-license-ledger.json` は上書きせず、その状態を下表の「2026-11-13」列に残した。
index URLは参照先であり実際の取得元を証明しない。本台帳は法的助言ではない。

| 状態（2026-11-15） | 件数 | 意味 |
| --- | --- | --- |
| Confirmed | 56 | 同梱ライセンス本文が宣言と一致（または内容のないmeta-package）。ライセンス・著作権表示の保持で足りる |
| Confirmed + conditions | 24 | ライセンスは確認済み。同梱部品（LGPL、GCC例外、NVIDIA部品等）、本文の欠落、AGPLにより配布時の追加作業・条件がある |
| Proprietary terms confirmed | 14 | NVIDIA独自条件の本文と配布条項を確認（[監査 §0.8.3](THIRD_PARTY_LICENSE_AUDIT.md#ngc-container-license)） |
| Verified | 2 | 固定版の上流LICENSEと記録された改変を確認 |
| Legal review required | 2 | 非商用条件を含む同梱コードがあり法的判断が必要 |
| Not applicable | 1 | first-party |

2026-11-13 の分類（Verified 3 / Metadata only 94 / Unresolved 1 / Not applicable 1）は、インストール済みメタデータとファイル名の自動抽出だった。
2026-11-15 は各distributionの同梱ライセンス本文を読み、宣言と照合した。Unresolved だった `cuda-toolkit` は meta-package と確認した。
basicsr は最上位の Apache-2.0 を確認済み（2026-11-13 Verified）だが、非商用条件の同梱コードが見つかったため Legal review required に変更した。
「Confirmed」は配布用NOTICEの完成や配布の許可を意味しない。(b)では同梱ファイル一式の保持と補充が必要で、(c)の利用条件は別途判定する。

| package | version | 宣言（長い本文は省略） | LICENSE等 / NOTICE検出数（2026-11-13） | 2026-11-13 | 2026-11-15 | 備考 |
| --- | --- | --- | --- | --- | --- | --- |
| absl-py | 2.5.1 | Apache-2.0 | 2 / 0 | Metadata only | Confirmed |  |
| addict | 2.4.0 | UNKNOWN | 1 / 0 | Metadata only | Confirmed |  |
| basicsr | 1.4.2 | Apache License 2.0 | 1 / 0 | Verified | Legal review required | StyleGAN2由来ops（上流LICENSE-NVIDIA: Source Code License-NC）を同梱し本番importで読み込む（§0.8.5） |
| certifi | 2026.10.23 | MPL-2.0 | 1 / 0 | Metadata only | Confirmed |  |
| charset-normalizer | 3.5.2 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| cloudpickle | 3.1.2 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| coloredlogs | 15.0.1 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| colorlog | 6.12.0 | MIT License | 1 / 0 | Metadata only | Confirmed |  |
| contourpy | 1.4.0 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| cuda-bindings | 13.5.0 | Apache-2.0 | 1 / 0 | Metadata only | Confirmed |  |
| cuda-pathfinder | 1.8.6 | Apache-2.0 | 1 / 0 | Metadata only | Confirmed |  |
| cuda-toolkit | 13.0.3.0 | 未宣言 | 0 / 0 | Unresolved | Confirmed | meta-package（ソフトウェアを含まない）。条件は選択されるnvidia-* wheelに従う |
| cycler | 0.12.1 | Copyright (c) 2015, matplotlib project All rights reserved. Redistribution and use in s... | 1 / 0 | Metadata only | Confirmed |  |
| facexlib | 0.3.0 | Apache License 2.0 | 1 / 0 | Metadata only | Confirmed | METADATAはApache-2.0、同梱本文と上流はMIT。本文を正とする |
| filelock | 4.2.9 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| filterpy | 2.0.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| flatbuffers | 25.12.19 | Apache 2.0 | 0 / 0 | Metadata only | Confirmed + conditions | LICENSE同梱なし。上流 Apache-2.0。(b)で本文を補う |
| fonttools | 4.68.0 | MIT | 2 / 0 | Metadata only | Confirmed + conditions | OFL・Apache部分を含む |
| fsspec | 2026.9.0 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| future | 1.0.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| gfpgan | 1.3.8 | Apache License Version 2.0 | 1 / 0 | Metadata only | Legal review required | 同梱LICENSEにNVIDIA NC・CC BY-NC-SA 4.0部分。本番経路では未読込（§0.8.5） |
| grpcio | 1.85.1 | Apache-2.0 | 1 / 0 | Metadata only | Confirmed + conditions | MPL-2.0・BSD部分を含む |
| homr | 0.1.0 | AGPL-3.0 | 1 / 0 | Verified | Verified | 固定commitのAGPL-3.0と改変。重みは§0.8.4 |
| humanfriendly | 10.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| idna | 3.20 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| ImageIO | 2.38.1 | BSD-2-Clause | 1 / 0 | Metadata only | Confirmed |  |
| Jinja2 | 3.1.6 | License :: OSI Approved :: BSD License | 1 / 0 | Metadata only | Confirmed |  |
| joblib | 1.6.0 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| kiwisolver | 1.5.1 | ========================= The Kiwi licensing terms ========================= Kiwi is li... | 1 / 0 | Metadata only | Confirmed |  |
| lazy-loader | 0.6 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| llvmlite | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | 2 / 0 | Metadata only | Confirmed + conditions | LLVM（Apache-2.0 WITH LLVM-exception）同梱 |
| lmdb | 3.0.0 | OLDAP-2.8 | 1 / 0 | Metadata only | Confirmed |  |
| Markdown | 3.11.3 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| MarkupSafe | 3.0.4 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| matplotlib | 3.10.6 | License agreement for matplotlib versions 1.3.0 and later =============================... | 3 / 0 | Metadata only | Confirmed + conditions | 同梱フォントのOFL等を含む |
| mpmath | 1.3.0 | BSD | 1 / 0 | Metadata only | Confirmed |  |
| narwhals | 2.28.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| networkx | 3.7 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| numba | 0.68.1 | BSD | 2 / 0 | Metadata only | Confirmed + conditions | 第三者通知を同梱 |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 20 / 0 | Metadata only | Confirmed + conditions | libgfortran（GPL-3+GCC例外）、libquadmath（LGPL-2.1+）、OpenBLAS同梱 |
| nvidia-cublas | 13.1.1.3 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cuda-cccl | 13.3.5.0.6 | LicenseRef-NVIDIA-Proprietary | 2 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA（Attachment A未列挙、§2.3の解釈要） |
| nvidia-cuda-cupti | 13.0.85 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cuda-nvrtc | 13.0.88 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cuda-runtime | 13.0.96 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cudnn-cu13 | 9.24.0.43 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | NVIDIA SDK License Agreement |
| nvidia-cufft | 12.0.0.61 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cufile | 1.15.1.6 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA（Attachment A未列挙、§2.3の解釈要） |
| nvidia-curand | 10.4.0.35 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cusolver | 12.0.4.66 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cusparse | 12.6.3.3 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA |
| nvidia-cusparselt-cu13 | 0.8.1 | NVIDIA Proprietary Software | 2 / 0 | Metadata only | Proprietary terms confirmed | NVIDIA SDK License Agreement（nvidia/cusparselt/LICENSE.txt） |
| nvidia-nccl-cu13 | 2.30.7 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Confirmed | BSD-3-Clause |
| nvidia-nvjitlink | 13.5.37 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA（Attachment A未列挙、§2.3の解釈要） |
| nvidia-nvshmem-cu13 | 3.4.5 | LicenseRef-NVIDIA-Proprietary | 1 / 0 | Metadata only | Proprietary terms confirmed | CUDA Toolkit EULA（Attachment A未列挙、§2.3の解釈要） |
| nvidia-nvtx | 13.0.85 | Apache 2.0 | 1 / 0 | Metadata only | Confirmed | Apache-2.0 WITH LLVM-exception |
| omegaconf | 2.4.0 | License :: OSI Approved :: BSD License | 2 / 0 | Metadata only | Confirmed |  |
| onnxruntime-gpu | 1.24.4 | MIT License | 1 / 1 | Metadata only | Confirmed + conditions | ThirdPartyNotices.txt（325 KB）を保持 |
| opencv-python | 4.11.0.86 | Apache 2.0 | 5 / 0 | Metadata only | Confirmed + conditions | Qt5（LGPL-3）、FFmpeg（LGPL-2.1+）、OpenSSL 1.1等34 lib同梱。headless版と二重導入 |
| opencv-python-headless | 4.14.0.94 | Apache 2.0 | 5 / 0 | Metadata only | Confirmed + conditions | FFmpeg（LGPL-2.1+）、OpenSSL 1.1.1k等16 lib同梱 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | 5 / 0 | Metadata only | Confirmed |  |
| pdfscore-pipeline | 0.1.0 | 未宣言 | 0 / 0 | Not applicable | Not applicable | first-party（#505） |
| pillow | 12.3.0 | MIT-CMU | 1 / 0 | Metadata only | Confirmed + conditions | libjpeg/libpng/libtiff/FreeType/HarfBuzz等18 lib同梱 |
| pip | 26.3 | MIT | 44 / 0 | Metadata only | Confirmed + conditions | vendored 42ファイル。build tool |
| platformdirs | 4.14.5 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| protobuf | 7.36.2 | 3-Clause BSD License | 1 / 0 | Metadata only | Confirmed |  |
| psutil | 7.2.2 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| pyclipper | 1.4.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| PyMuPDF | 1.26.4 | Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License | 1 / 0 | Metadata only | Confirmed + conditions | COPYINGは1行の表示のみ。AGPL全文とMuPDF同梱部品の通知を(b)で補う |
| pyparsing | 3.3.3 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| pypdfium2 | 5.15.1 | BSD-3-Clause, Apache-2.0, dependency licenses | 37 / 0 | Metadata only | Confirmed + conditions | PDFium・依存の37ファイル（CC-BY-4.0、GCC例外等）。現行sourceは直接未使用 |
| python-dateutil | 4.0.0 | BSD-3-Clause | 2 / 0 | Metadata only | Confirmed |  |
| PyYAML | 6.0.3 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| rapidocr | 3.10.0 | Apache-2.0 | 2 / 0 | Metadata only | Confirmed + conditions | PP-OCRv6 ONNXモデル同梱（PaddleOCR Apache-2.0、学習データ未追跡） |
| rapidocr-onnxruntime | 1.4.4 | Apache-2.0 | 0 / 0 | Metadata only | Confirmed + conditions | LICENSE同梱なし。上流 Apache-2.0。PP-OCRv4 ONNXモデル同梱（PaddleOCR Apache-2.0、学習データ未追跡） |
| realesrgan | 0.3.0 | BSD-3-Clause License | 1 / 0 | Verified | Verified | 固定commitのBSD-3-Clause。重みはDF2K学習（§0.8.4） |
| requests | 2.34.2 | Apache-2.0 | 1 / 1 | Metadata only | Confirmed |  |
| scikit-image | 0.26.0 | Files: * Copyright: 2009-2022 the scikit-image team License: BSD-3-Clause Files: doc/so... | 1 / 0 | Metadata only | Confirmed |  |
| scikit-learn | 1.9.1 | BSD-3-Clause | 3 / 0 | Metadata only | Confirmed + conditions | libgomp（GPL-3+GCC例外）同梱 |
| scipy | 1.18.1 | Copyright (c) 2001-2002 Enthought, Inc. 2003, SciPy Developers. All rights reserved. Re... | 5 / 0 | Metadata only | Confirmed + conditions | libgfortran（GPL-3+GCC例外）、libquadmath（LGPL-2.1+）、OpenBLAS同梱 |
| setuptools | 84.2.1 | MIT | 17 / 2 | Metadata only | Confirmed + conditions | vendored autocommand（LGPL-3.0）。build tool |
| shapely | 2.2.0 | BSD-3-Clause | 2 / 0 | Metadata only | Confirmed + conditions | GEOS（LGPL-2.1）同梱 |
| six | 1.17.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| sympy | 1.14.0 | BSD | 3 / 0 | Metadata only | Confirmed |  |
| tb-nightly | 2.21.0a20251023 | Apache 2.0 | 1 / 0 | Metadata only | Confirmed |  |
| tensorboard-data-server | 0.7.2 | Apache 2.0 | 0 / 0 | Metadata only | Confirmed + conditions | LICENSE同梱なし。上流 Apache-2.0。(b)で本文を補う |
| threadpoolctl | 3.8.0 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| tifffile | 2026.10.15 | BSD-3-Clause | 1 / 0 | Metadata only | Confirmed |  |
| torch | 2.14.0 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL... | 90 / 0 | Metadata only | Confirmed + conditions | 同梱の第三者ライセンス90ファイルを保持 |
| torchvision | 0.29.0 | BSD | 1 / 0 | Metadata only | Confirmed + conditions | NVIDIA libcudart/libnvjpeg（CUDA EULA）とlibjpeg/libpng/WebP/zlib同梱。LICENSEはBSD部分のみ |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | 1 / 0 | Metadata only | Confirmed |  |
| triton | 3.8.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| types-Pillow | 10.2.0.20240822 | Apache-2.0 | 0 / 0 | Metadata only | Confirmed + conditions | LICENSE同梱なし。METADATA Apache-2.0（typeshed）。runtime不要の型スタブ |
| typing_extensions | 4.16.0 | PSF-2.0 | 1 / 0 | Metadata only | Confirmed |  |
| tzdata | 2026.6 | Apache-2.0 | 2 / 0 | Metadata only | Confirmed |  |
| urllib3 | 2.8.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| Werkzeug | 3.1.9 | BSD-3-Clause | 2 / 0 | Metadata only | Confirmed |  |
| wheel | 0.48.0 | MIT | 1 / 0 | Metadata only | Confirmed |  |
| yapf | 0.43.0 | Apache License Version 2.0, January 2004 http://www.apache.org/licenses/ TERMS AND COND... | 3 / 0 | Metadata only | Confirmed |  |

導入元の証拠: HOMRおよびReal-ESRGANはVCS `direct_url.json` に固定commitを記録。他は一部editableを除き取得インデックスが記録されないため未確定。
詳細と配布形態ごとの義務は[本監査](THIRD_PARTY_LICENSE_AUDIT.md) §0.8（[最終調査](THIRD_PARTY_LICENSE_AUDIT.md#final-20261115)）。
