# Issue #416 本番実装と残存FNの受容判断

最新のPR指摘対応・相対パスでの本番再検証は [REVIEW_422.md](REVIEW_422.md)。
本記録の `cecdd5db` 検証はCNNへ絶対パスを直接渡しており、相対パスで重複整理が省略される問題を捕捉していなかった。
元の数値と実験記録は保持し、本番呼び出しの再検証と区別する。

2026-10-15。base `develop@016e181861270f1adc753778ef71422fa51f2716`。
この記録は実装前の [修正案](PRODUCTION_FIX_PROPOSAL.md) と
[成分検証](VERIFICATION.md) に続く、本番候補の判断である。
全43件の原因・反実仮想は [初期調査](README.md) に残す。

## 採用する範囲

複数五線を包むbboxを、そのまま独立ストロークGTと比べると、FPとFNが同時に発生する。
また、長い元HOMR bboxが合意フィルタで落ちた後、同じXの上側線が下側の走査を
`existing`として抑制していた。CNN閾値の調整や再学習を原因対策としない。

`maintained_original` のdense経路で、既存のraw生成・filter・rescueが終わった後、
CNN入力だけを五線別に整える。走査seed/row_statsは従来のまま。

- StaffExtractorの元画像座標の領域を使い、各五線と2unit以上重なる五線が複数あるbboxのみ分割する。
  一つの五線にしかかからない尾部は切らない。
- 最終候補の分割に加え、元HOMRの分割片を既存の **SRまたはOMRとのIoU > 0.5** 合意へ通して追加する。
  追加片も同じ実モデル・閾値でCNN採点する。
- 採用候補の重複はX中心差<=0.1unit、vov>=0.8に限定して整理する。
  unitは本番maskから抽出した五線unitの中央値であり、評価用staff_unitsを参照しない。
  代表は番号処理と同じ `(x1,-width,y1,y2,x2)` 順。代表自身のCNNスコアを保持する。
- 物理時間境界の1.2unit統合とストローク重複整理を混同しない。別五線・二重線を一括NMSしない。
- 元候補hash、入力hash、分割元・分割先・追加片、重複代表をページ別sidecarに保存する。
  producer情報欠落やimage identity不一致は明示的エラー。五線のないページは候補を保存し、状態を記録する。

connector mask、モデル、CNN閾値、GT、matcher、MMR/OCR、補正適用、配布のサービス境界は変更しない。
配布manifestには新規本番2モジュールを含め、評価/prototypeはdevelop専用とした。
current architectureを更新。future architectureは責務・process/public API変更がなく更新不要と判断した。

## 残る7件を許容する理由

独立ストロークのFNとして **7件をそのまま残す**。物理的な時間境界の欠落とは分けて判断した。
番号が全曲で完全に正しいという意味ではなく、この限定修正の採用を妨げないという判断である。

| #415監査ID | 作品 / ページ | 元画像GT bbox | 残存原因と扱い |
| --- | --- | --- | --- |
| 3 | Sibelius / 001 | [1258,1630,1267,1738] | divisi下側の尾部付きbbox。上側の採用線が同じ物理境界を支える |
| 4 | Sibelius / 001 | [1616,1630,1627,1736] | 同上。低CNNスコアもあるが、無条件clipでは新規FPを生む |
| 9 | Sibelius / 001 | [3063,4320,3067,4423] | 二重線の独立ストローク不足 |
| 13 | Sibelius / 003 | [1892,1363,1896,1470] | 二重線の独立ストローク不足 |
| 14 | Sibelius / 003 | [2671,1363,2675,1470] | 二重線の独立ストローク不足 |
| 16 | Prokofiev Symphony1 / 004 | [2715,2481,2720,2582] | 二重線の左ストローク不足 |
| 17 | Prokofiev Symphony1 / 005 | [2377,3496,2381,3599] | 二重線の左ストローク不足 |

本番候補の実予測に各GTを一つずつ挿入するoracle検証で、小節数差0、五線所属不変を確認する。
二重線5件では小節領域も不変。divisi2件では境界の数px差は残るが、物理境界は保持される。
片側尾部の一般clipは新規FP2件、単純な列inkによる二重線分割は新規FP1件を生むため採用しない。
これらの別課題を同時に実装せず、原契約のFNとして追跡する。

## 本番候補の固定Full68検証

固定GT3567、center_anchor、vov>=0.5、X距離<=0.5評価staff unit、
CNN閾値0.4965248107910156、同じEfficientNet-B0重み。
同一の保持producer入力からraw/filter/rescueを全68ページ再生成し、元候補29612件との一致を検査。
元候補・本番候補の **全cropを同じCUDA実行で再採点** する。過去のCNN採否は流用しない。
検証器は本番の曲名引数が未指定であることも合わせ、両側を比較する。

| 指標 | 現行の再生成・再推論 | 本番候補 |
| --- | ---: | ---: |
| TP | 3535 | 3560 |
| hard FP | 11 | 0 |
| FN | 32 | 7 |
| soft重複 | 100 | 121 |
| 物理小節数 | 3287 | 3287 |

**softは21件増える**。全残差改善や全指標同等とは表現しない。
hard FP/FNのページ別悪化は0。68ページのsystem/staff/小節領域/番号は検証済み成分案と一致する。
元基準に対して67ページの幾何は同じで、Sym5/page_005は失われていた下側divisiの所属と
4小節のY領域を復旧する。単なる総小節数一致ではこの修正効果は表せない。

同じbaseからMMR supportを再生成し、実予測を使って本番の最終番号を再構築する。
68ページすべてのsupport・実最終JSONが先のfresh CUDA MMR/OCR結果と等価な場合に限り、
その認識・PDF検証を再利用する。MMR GT177: TP171/FN3/wrong3/FP0、
補正適用エラー0、ページ連続性エラー0。既知の局所GT誤り6件と独立row sample不一致5/18は維持する。
絶対番号の完全性は認定しない。PDF68ページ・行ラベル637件のpixel検証も等価性を根拠に再利用する。

## 再現情報と検証範囲

保持rootはworktree内 `logs/issue416/production-20261015/`。
元producerは `logs/issue409/full68-numbering-20261009/candidate/variant_summary.json`。
元推論commit `a65d9541777ae492137c24b6ce0f5f5692881945`、設定SHA256
`0edfdfda89ed50be6d0dafbf28fccc80840ef6330f193d19823a94f934cb2209`。

- image: `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`。
  RTX4060、container Python3.12、`/opt/venv_pipeline/bin/python`。
- CNN SHA256: `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`。
- `contract.json`: 実行前固定条件。`provenance.json`: 実source/runner/model/runtime hash。
- `validate.py`, `validation.log`, `baseline/report.json`, `candidate/report.json`, `gates.json`:
  全候補再生成・両側CUDA採点とページ別結果。
- `residuals.py`, `residual-acceptance.json`: 967保持入力hash照合、残る7件の実出力oracleと境界支持。
- `downstream.py`, `downstream-candidate/report.json`: base/support/本番最終番号の等価性。
- `attempt-explicit-score/`: 本番と異なる曲名引数で余計な幾何filterを発動させた失敗検証を保存。
  現行側にも小節欠落が出たため採用根拠から除外し、本番引数へ修正して全68を再検証した。
- `smoke.yaml`, `smoke.log`: canonical smoke設定を出力先とrun IDだけIssue rootへ変更。
  PDFからfresh render、全producer、CUDA CNN/MMR/OCR、番号、accuracy gateを実行する。
  nonroot権限によるモデル読込失敗とTriton cache失敗を別ログで保持。同一SHAのread-onlyモデルmountと
  `/tmp`のcache指定で解消し、モデル・設定の意味は変更しない。

実行の主要形:

```text
Docker: original repo -> /workspace; worktree code -> PYTHONPATH=/workspace/.worktrees/issue416
/opt/venv_pipeline/bin/python -u /workspace/.worktrees/issue416/logs/issue416/production-20261015/validate.py
../../.venv_pdf/bin/python logs/issue416/production-20261015/residuals.py
../../.venv_pdf/bin/python logs/issue416/production-20261015/downstream.py
DOCKER_IMAGE=<上記image> DOCKER_EXTRA_ARGS=<同一モデル・固定dataのRO mountsとcache指定> \
  bash scripts/docker_runtime_validation.sh --config logs/issue416/production-20261015/smoke.yaml
```

全68のSR/HOMR再推論は入力・producer変更がないため行わず、保持結果を使用した。
GUI操作の再監査は今回変更していないため実施しない。新しいデータセットへの一般化は未検証。
#410等のmain昇格条件にこの数値改善を追加しない。PRはdevelop向けで、mainへのmergeは行わない。

実施した軽量検証:

```text
../../.venv_pdf/bin/python -m pytest -q tests/test_staff_strokes.py \
  tests/test_issue255_production_detector_restoration.py tests/test_issue296_cnn_dataset_matching.py \
  tests/test_detector_orchestrator_input_contract.py tests/test_cnn_scoring_model_path.py
# PASS: 46 tests
make test-fast PYTHON=../../.venv_pdf/bin/python
# PASS: 114 tests
../../.venv_pdf/bin/python tools/check_repository_surface.py
# PASS: runtime/distribution closure and tracked test classification
../../.venv_pdf/bin/python -m pytest -q tests/test_distribution_surface.py \
  tests/test_issue100_runtime_surface.py tools/issue416/test_prototype.py
# PASS: 34 tests
ruff check <変更Python 5 files>
ruff format --check <変更Python 5 files>
# PASS
```

集計と各残存FNの実出力hashは [production_validation.json](production_validation.json) に固定する。
全ページ詳細と大きな画像・モデル・PDFはgitへ含めない。

Fresh production smokeも **PASS**。PDFからの再描画・全producer・CUDA CNN/MMR/OCR・番号処理を完了し、
固定GT85に対してTP85/hard FP0/FN0/soft0、入力PDFと描画imageのhash照合も通過した。
