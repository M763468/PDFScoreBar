# PR #422 指摘対応と本番経路の再検証

最新は末尾の「追加inline対応（round 3）」と [review_round3_validation.json](review_round3_validation.json)。
以下の初回指摘対応とその検証記録も保持する。

2026-10-15。対象は `cecdd5db42dda72b7e909e675f35a616acfe8dfe` への2件のinline review。
両方を明確な修正要求と分類し、同じPRで対応する。

## 指摘と修正

- [P1: 画像キーの不一致](https://github.com/M763468/PDFScoreBar/pull/422#discussion_r4283755678)
  inventory/unit mapは絶対パスだが、本番CNNの`images`には相対パスが来る。
  map lookupが失敗し、重複整理とそのsidecarが静かに省略されていた。
  作成側・参照側の両方を`Path.resolve()`のidentityへ統一した。
  絶対・相対・symlinkの3通りでpublic batch scoringを実行し、採用bboxと抑制先sidecarを検証する。
- [P2: unit未推定の有効な五線](https://github.com/M763468/PDFScoreBar/pull/422#discussion_r4283755692)
  `StaffExtractor`は単線打楽器等を`unit_size=None`のまま保持する。
  これを`StaffRegion`へ渡すと`math.isfinite(None)`で停止していた。
  一つでもunit未推定の五線があるページは元候補をbyte単位で保持し、正規化・重複整理を省略する。
  `no_staff_unit_size`、全五線数・未推定五線数を監査sidecarへ記録する。
  既知の五線だけで分割すると未知声部を捨て得るため、混在ページもページ全体を保持する。
  正のunitを捏造したり閾値を調整したりしない。
  実StaffExtractorが単線maskをNoneで返すケースと、既知/未知unit混在のcontrolを追加した。

## 前回の検証で捕捉できなかった理由

前回Full68は`_score_directory`へ絶対パスとunitを直接渡していたため、
成分・幾何・下流への結果は有効だが、public batchでの相対パスlookupは検証できていなかった。
前回fresh smokeは相対パスを通ったものの、対象ページに抑制すべき重複がなく、GT85の精度gateだけでは
重複整理の省略を検出できなかった。前回smokeの重複整理sidecarは0件である。
[前回記録](production_validation.json) は上書きせず残し、今回の再検証と区別する。

## 再検証契約

`logs/issue416/review-422-20261015/contract.json` を実行前に保存した。
旧Full68のGT3567、center_anchor、vov=.5、X距離=.5評価staff unit、
CNN閾値.4965248107910156、モデルとCUDA imageを維持する。
本番にGT/staff_unitsを持ち込まない。

- 同じ保持producer/raw/filter/rescue出力から新adapterを全68ページ再実行し、
  正規化済み全候補が前回と一致することを検査する。
- **相対パスのimagesを本番`DetectorOrchestrator._run_cnn_scoring`へ渡す**。
  全候補をCUDA再推論し、68/68ページの重複整理sidecarを必須にする。
- `git show cecdd5db:src/pipeline/steps/cnn_scoring.py` の実sourceも保存し、
  同じ正規化済み候補・相対images・絶対unit mapでparent public batchを実行する。
  実sourceのhashを前回provenanceと照合し、同じモデルで両側を比較する。
- 修正後の予測・番号baseが前回の採用候補と全68で一致し、小節数3287、
  TP3560/FP0/FN7/soft121を保つことをgateにする。
  unit未推定ページ数も数え、今回の固定68では0件であることを確認する。
- fresh PDF/GPU accuracy smokeも再実行し、GT85の精度だけでなく実際の重複整理sidecarを検査する。

## 結果

完了した数値とruntime/source/log hashは [review_validation.json](review_validation.json) に固定する。

| 実行 | TP | hard FP | FN | soft | 重複整理sidecar |
| --- | ---: | ---: | ---: | ---: | ---: |
| parent `cecdd5db` の相対パスpublic batch | 3560 | 0 | 7 | 257 | 0/68 |
| 修正後の相対パス本番呼び出し | 3560 | 0 | 7 | 121 | 68/68 |

修正後の全予測・全番号baseは前回採用候補と一致する。
したがって、前回の全68 support/実最終番号の等価性、fresh CUDA MMR/OCR、PDF68ページ/637行ラベルの
pixel検証は引き続き有効である。小節数3287、残存FN7件の受容判断、既知のMMR誤り6件と
row sample不一致5/18を維持する。softは元の修正前基準100より21件多いままである。

- fresh PDF/GPU accuracy smoke: PASS。GT85/TP85/hard FP0/FN0/soft0、重複整理sidecar 1/1を確認。
- 967保持入力hashと全68ページの正規化入力hashの同一性: PASS。
- 対象pytest: 52 PASS（前回46件に今回の回帰6件を追加）。
- `make test-fast PYTHON=../../.venv_pdf/bin/python`: 114 PASS。
- `tools/check_repository_surface.py`: PASS。
- 変更Python 3ファイルのRuff check/format: PASS。

## Provenanceと省略した検証

保持root: worktree内 `logs/issue416/review-422-20261015/`。

- `github/`: pr-refinementで取得したPR本文・reviews・会話・全inlineコメント・差分。
- `contract.json`, `provenance.json`, `validate_relative.py`, `parent_cnn_scoring.py`:
  固定条件、parent/候補source hash、実行器、比較対象の実source。
- `parent_relative/`, `candidate/`, `validation.log`, `gates.json`:
  全ページCNN出力・候補・番号base・正規化/抑制sidecarと一致検証。
- `smoke.yaml`, `smoke.log`, `smoke/`: fresh PDFからの全producer/GPU/番号/accuracyゲート。
- `targeted-tests.log`, `test-fast.log`, `surface.log`: 軽量検証。

実行は前回と同じ固定image
`sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`、
同じdigest検証済みCNNのread-only mount、nonrootと`/tmp`のTriton/Inductor cacheを使用する。
Full68ではoriginal repoを`/workspace`、worktreeを`PYTHONPATH`先頭、cwdをoriginal repoへ設定し、
相対dataパスと本番の呼び出しをそのまま使う。

```text
/opt/venv_pipeline/bin/python -u /workspace/.worktrees/issue416/logs/issue416/review-422-20261015/validate_relative.py
DOCKER_IMAGE=<上記image> DOCKER_EXTRA_ARGS=<固定data/modelのRO mountsとcache指定> \
  bash scripts/docker_runtime_validation.sh --config logs/issue416/review-422-20261015/smoke.yaml
```

Full68のSR/HOMR再推論とraw/filter/rescueの再生成は、当該source/config/入力に変更がなく、
保持出力をそのまま使えるため省略。新adapterとCNNは全68で実行する。
新しい実percussion資料の精度は未検証で、P2は有効な単線maskと混在controlによる互換性検証に限る。
GUI/公開API/process/依存関係は変更なし。current architectureの省略条件を追記し、future architectureは更新不要。
今回の数値改善を#410等のmain昇格条件には追加しない。


## 追加inline対応（round 2）

対象commitは`43a8b7fdefe293231f77d338ee8e3662ab5431d3`。
2026-10-15の追加2件を具体的な修正要求と分類し、対応した。

- [P1: composite stemのprobe identity](https://github.com/M763468/PDFScoreBar/pull/422#discussion_r4284449671):
  inventoryは`images/OtherScore_page_001.png`を論理ラベル`OtherScore/page_001`へ分けるが、
  実際のprobe rescueは画像の親/stemから`eval2_images_OtherScore_page_001`へ出力する。
  adapterもproducerと同じ`build_probe_run_id(image)`を使い、論理ラベルからディレクトリを組み立てない。
  以前のcomposite testはadapterが期待するtargetを手で作っていたため問題を隠していた。
  実inventory writer→実probe rescue→adapter→本番CNN呼び出しへ置き換え、絶対/相対画像で確認する。
  合成testのCNNモデルだけは固定陽性モデルへ差し替え、探索・パス接続・監査出力を検査する。
- [P2: 空候補の監査](https://github.com/M763468/PDFScoreBar/pull/422#discussion_r4284449683):
  通常採点、空候補、有効cropなしを共通writerへ集約した。
  dedup有効なら空でも`{unit_size: ..., suppressed: []}`を上書きし、無効なら古いsidecarを除去する。
  以前の監査結果がある同じrun_dirで再実行する4通りのcontrolを追加した。

固定条件は`logs/issue416/review-422-round2-20261015/contract.json`に実行前記録。
GT3567、matcher、staff-unit tolerance、CNN閾値、モデルとimageは変更しない。
保持raw/filter/rescueとproducerはそのまま使い、全68ページでadapterと相対imagesの本番CNNをCUDA再実行する。
全正規化候補・予測・番号base・sidecar数を既存の採用候補と比較する。

- 対象pytest **57 PASS**、`make test-fast` **114 PASS**。
- Ruff check/formatとrepository surface **PASS**。
- fresh PDF/GPU accuracy smoke **PASS**: GT85/TP85/hard FP0/FN0/soft0、重複整理sidecar 1/1。
- Full68 **TP3560/FP0/FN7/soft121**、物理小節数 **3287**、重複整理sidecar **68/68**。
  全予測・番号baseが以前の採用候補と一致し、967保持入力hashと68ページの入力identityも同一。
- したがってMMR/support/実最終番号とPDFの既存等価性・pixel検証を再利用する。
  残るFN7件の受容判断と既知のMMR課題を変更しない。

保持rootはworktree内`logs/issue416/review-422-round2-20261015/`。
`github/`, `contract.json`, `provenance.json`, `validate_relative.py`, `candidate/report.json`,
`gates.json`, `input-equivalence.json`, `smoke.yaml`, `smoke.log`と軽量test logsを保持。
今回比較のparentは前回検証済みの保持出力であり、parentモデルの再推論は行っていない。
新規CNN候補と本番CNNは全68で実行し、producer/SR/HOMRとraw/filter/rescueの全68再生成は変更がなく省略した。
前回から継承したcontractのparent比較は、この有効な保持baselineとの比較である。
future architectureは責務/process/public API変更がなく更新不要。#410等のmain昇格条件を追加しない。


## 追加inline対応（round 3）

2026-10-16。[P2: symlink入力のsupport identity](https://github.com/M763468/PDFScoreBar/pull/422#discussion_r4284824551)
を修正要求として対応した。検証対象は `b51c9f6f17de05785e7dfcde8aafa197d58a2f70`。

inventoryの画像パスは絶対化しつつsymlinkを保持し、probe/rescue/adapter/CNNが同じ親/stemを使う。
一方、supportの保存先は元の画像パスを使うin-process producerと、画像を解決してから動く
source-page workerで異なる。adapterは元パスと解決後パスの既知の2か所だけを確認し、
同じ解決先をまとめた結果が一意であること、completed/current HOMR実行済みであること、
payloadの画像identityが一致することを要求する。異なるresultが両方に存在する場合は停止する。

最初の候補 `82ef0e1f` はinventoryだけを修正したため、fresh symlink smokeで失敗した。
SRは`current_support/images/...`へ出力されたが、ページworkerのsupport結果は
`current_support/actual_images/.../result.json`にあり、adapterがalias側だけを探して停止した。
この失敗をPASSとして扱わず、`smoke.log`、`smoke/`、`attempt-inventory-only-contract.json`
に保持した。最終候補の検証は新しいrun IDと`smoke-fixed/`で実行する。

- 実inventory writer→inventory reader→実probe rescue→adapter→本番CNN呼び出しを検査する。
  絶対/相対、通常/ディレクトリsymlink/ファイルsymlink、元/解決後supportの12通り。
  合成テストのCNNのみ固定陽性CPUモデルに置換する。
- supportなし・異なるresultが2個・同じresultへのsymlinkの3 controlを追加する。
  元の画像identity不一致controlも継続する。修正前のinventoryでは追加directory test 2件が失敗することを確認した。
- 対象pytest **70 PASS**、`make test-fast` **114 PASS**、Ruff check/format、repository surface、diff check **PASS**。
- 固定Full68を別名ディレクトリsymlink経由で本番inventory writerとadapterへ渡し、
  全cropを同じ固定CUDA modelで再推論する。**TP3560/FP0/FN7/soft121、小節数3287**。
  全68ページで正規化候補・予測・番号baseが既存の採用候補と一致し、sidecar **68/68**。
  normalizationの6入力のhash値も全ページ一致し、保持入力 **967 hash**も一致する。
- 最終候補のfresh PDF/GPU smokeは、実`inputs/images`を`actual_images`へのsymlinkとして事前作成し、
  空のtargetへfresh renderして全producer、raw/filter/rescue、CNN、MMR、番号処理を実行する。
  **GT85/TP85/hard FP0/FN0/soft0、sidecar 1/1**。inventoryのalias保持とworkerのresolved supportも確認する。

固定GT/matcher/tolerance/CNN閾値/model/imageと元の受容条件は変更しない。
Full68のSR/HOMRおよびraw/filter/rescue再生成は、入力・producerに変更がなく、保持候補と
6入力hashが等しいため省略した。新inventory/adapter/CNNは全68で実行し、
fresh smokeでは全producerを新規実行した。全予測・番号baseの厳密な一致に基づき、既存の
all68 MMR/final numbering/PDF検証を再利用する。残FN7、既知のMMR6件・row sample不一致5件の
扱いを変更しない。新たなmain昇格条件は追加しない。

保持rootはworktree内`logs/issue416/review-422-round3-20261016/`。
`contract.json`、`provenance.json`、`validate_symlink.py`、`candidate/report.json`、`gates.json`、
`retained-inputs.json`、`smoke-fixed.yaml`、`smoke-fixed.log`、`smoke-fixed/`とtest logsを保持。
実行環境とモデルのread-only mountはround 2と同じ固定digest。Full68はoriginal repoを
`/workspace`へ、active worktreeを`PYTHONPATH`へ設定する。smokeはactive worktreeを`/workspace`へmountする。

```text
/opt/venv_pipeline/bin/python -u /workspace/.worktrees/issue416/logs/issue416/review-422-round3-20261016/validate_symlink.py
DOCKER_IMAGE=<round 2と同じ固定image> DOCKER_EXTRA_ARGS=<同じdata/model RO mountsとcache指定> \
  bash scripts/docker_runtime_validation.sh --config logs/issue416/review-422-round3-20261016/smoke-fixed.yaml
```

sourceと実行commitの対応は記録生成時に`git show <reviewed_commit>:<path>`のSHA-256でも検査する。
process/責務/public API変更がないためfuture architectureの更新は不要。
