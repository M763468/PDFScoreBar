# Issue #416 小節線残差の原因・修正可能性・下流影響の調査

最新の本番実装・残存FNの受容判断は [IMPLEMENTATION.md](IMPLEMENTATION.md)。
以下は実装前の調査記録として保持する。

追加のGPU・MMR/OCR・最終番号/PDF検証が完了した。最新の判断は
[本番修正案](PRODUCTION_FIX_PROPOSAL.md) と [追加検証記録](VERIFICATION.md) を参照。
以下は初期調査の結果・当時の未検証項目として保持する。

2026-10-15、`develop@016e181861270f1adc753778ef71422fa51f2716` から
`investigation/issue416-barline-causes` を作成。これは精度改善の準備調査であり、
本番修正や受理済み評価契約の変更ではない。#416 の数値改善を #410 の main 昇格条件に追加しない。
既知の下流リスクと release の受容判断は、数値改善の採否と分けて扱う。

## 結論

43残差を43個の小節数誤りとして扱う根拠はない。全件を一件ずつ挿入/削除する
反実仮想 replay で、小節数の差は **43/43件で0**。10 affected pages の全残差補正と
全ストロークGTによる oracle replay でも各ページの小節数は変わらなかった。
ただし **小節数の一致だけでは五線の所属・小節領域の正しさを保証しない**。

- Sym5/page_005 の下側divisi五線 `[193,1619,3466,1793]` は検出されているが、
  採用小節線がなく、上側と結合せず空systemとしてシリアライズから落ちる。
  ID26/27/28/29 のいずれか一つを補うと上側と結合し、4小節のY領域が下側まで復帰する。
  ページ総数34は変わらない。MMR support/review の対象領域へ影響し得る実際の幾何不具合。
- FPを無条件に削除するのも危険。Sym5/page_021 の ID38 の長いbboxだけを削除すると、
  下側五線 `[236,3396,3512,3580]` の唯一の採用境界支持を失い、5小節の下側領域が消える。
  ページ総数50は変わらない。接続線の意味は、五線別ストローク表現への正規化後も保持する必要がある。
- 単独反実仮想で17/43件はbbox/所属が変わり、そのうち5件（26,27,28,29,38）は
  シリアライズされる五線の所属も変わる。他の変化は境界の数px程度の差を含む。
- 二重線5件は1対1のGTストローク割当不足。番号処理は1.2unitのX重複整理と
  1unit未満の区間除外を行い、一つの時間境界として数える。この5件の不足ストロークを
  補っても小節数・小節bboxは変わらない。GTは独立ストローク方針のまま保持する。

これらは固定入力の因果診断であり、全曲の絶対番号、すべての物理境界の完全性、
変更後MMR/OCR・最終PDFの正しさを認定する結果ではない。

## 維持した原評価契約と再現

原推論: `a65d9541777ae492137c24b6ce0f5f5692881945`、5作品68ページ。
設定 SHA-256: `0edfdfda89ed50be6d0dafbf28fccc80840ef6330f193d19823a94f934cb2209`。
原Docker image: `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`。
matcherは `center_anchor`、vov>=0.5、X距離<=0.5staff unit。
CNN閾値 `0.4965248107910156`、EfficientNet-B0、NMS無効。
モデル SHA-256: `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`。

保持出力を全68ページ再採点し、GT3567/候補29612/予測3646/TP3535/FP11/FN32
（旧FN_det27/FN_cnn5）、soft100を再現。
現行番号コードで全68ページの retained `numbering_base.json` と **system/staff/小節bbox/番号の完全一致**を確認。
物理小節総数3287。元画像68件のhash、既存#415証拠のhash、消費入力hashを検証し、
処理後にも変更不存在を再確認した。#413の固定入力manifestに含まれる消費入力も照合。

## 候補欠落9件の原因はproducerの完全不在ではない

9件全てに元HOMRの局所bboxがある。ただし最初から複数五線/connectorを包むため、
下側の五線別GTとのstrong matchは0。これは最初に観測できるストローク粒度の不一致。
その後、同じXにSR/OMRの支持があっても長さが違うため、padding付きIoU>0.5の
[合意フィルタ](../../src/pipeline/steps/hybrid_consensus.py)で棄却される。
「元画像に線がない」「モデルが位置を完全に見失った」「後段CNNが棄却した」ではない。

| ID | ページ | 元HOMR bbox | 最大SR IoU | 最大OMR IoU |
| --- | --- | --- | ---: | ---: |
| 21 | Sym5/page_005 | [1065, 3013, 1066, 3438] | 0.250445 | 0.379645 |
| 26 | Sym5/page_005 | [1154, 1343, 1155, 1768] | 0.257541 | 0.381515 |
| 27 | Sym5/page_005 | [1921, 1344, 1922, 1769] | 0.232290 | 0.493007 |
| 29 | Sym5/page_005 | [3454, 1349, 3455, 1774] | 0.244060 | 0.000000 |
| 32 | Sym5/page_018 | [805, 3773, 806, 4146] | 0.292876 | 0.381088 |
| 35 | Sym5/page_018 | [2433, 3776, 2434, 4151] | 0.296588 | 0.493078 |
| 37 | Sym5/page_018 | [3487, 3778, 3488, 4151] | 0.263113 | 0.000000 |
| 39 | Sym5/page_021 | [1088, 3113, 1089, 3538] | 0.262181 | 0.493885 |
| 43 | Sym5/page_021 | [3501, 3100, 3502, 3523] | 0.263403 | 0.000000 |
| 43 | Sym5/page_021 | [3504, 3215, 3505, 3523] | 0.307588 | 0.000000 |

全9件はgeneration/rescue両段で `status=existing`。局所ink ratioは
0.9484〜1.0000で濃さ不足ではない。両段の候補出力を再生成し、保持JSONと完全一致した。

[ExistingBarlines.has_existing](../../src/pipeline/probe_detector/existing.py) は
scan band内に中心Yがあり、同じX±4pxに既存bboxがあれば抑制する。
今回の `scan_existing_min_vertical_iou=0` では、上側だけのbboxで
上下を包むbandの走査が抑制される。上側bboxは残るが、下側bboxは作られない。
「局所候補なし」は **元HOMRの粒度不一致 → 合意棄却 → 上側候補による再走査抑制**の複合原因。
4pxは既存コードの値を記録したもので、新規thresholdは追加していない。

## 長い候補18件とCNN score

18件全て、元HOMRにも独立した下側strokeのstrong matchがない。
保持候補が長いまま復帰し、11件はCNN採用済みだがvov不一致、7件はvov不一致かつ低score。
そのためCNN閾値を下げるだけでは18件を修復できない。

[canonical crop](../../src/pipeline/steps/cnn_scoring.py) はbbox中心Yを使い、
高さを最大256pxに制限する。292〜425pxの接続bboxでは入力が五線間に寄る。
元候補とmask由来の五線別候補を、同じ重み・preprocessing・X recenter・閾値でCPU再推論した。
低score7件の五線別候補はすべて0.99998以上となり採用側へ変わる。
この陽性局所実験は形状/crop原因を支持するが、再学習不要を一般証明するものではない。

| ID | 元保持score | 五線別crop score（CPU） |
| --- | ---: | ---: |
| 4 | 0.034258 | 0.999998 |
| 8 | 0.410970 | 0.999982 |
| 23 | 0.406045 | 1.000000 |
| 24 | 0.311534 | 1.000000 |
| 28 | 0.050910 | 1.000000 |
| 40 | 0.430974 | 1.000000 |
| 42 | 0.092684 | 1.000000 |

元候補のCPU scoreと元GPU保持scoreの最大差は0.005589。調べた18候補の採否は全件一致。
同じ重みでも元GPU scoreのbitwise再現とは主張しない。CPUを明示し、モデルhashは検証済み。

## 二重線5件のfirst-loss

ID9/13/14は元HOMRから2本を1bboxで包む。ID16/17は右stroke付近の1bboxがあり、
左strokeの独立候補がない。どの段でも2つの独立候補としては復帰しない。
高scoreの採用予測が1対1matcherで別GTへ割当され、旧FN_cnn5として計上される。
ID16/17ではvov優先により右側のbboxが左GTへ割当され、右GTのFNとして見える。
CNN棄却ではなく、観測可能な最初の不足は元HOMR出力のストローク個数/粒度。
segmentation mask生成とCC/mergeのどちらが発端かは今回分離していない。

## 改善の成分実験（本番非適用）

全件をGTから生成するoracleと、GTを生成に使わない成分候補は分けた。
以下2実験の定義を実行前に各contract JSONへ保存。matcher/GT/CNN閾値/モデルは固定。

1. **採用後の幾何分割**: 採用bboxが2五線以上に各2unit以上交差したら、
   maskから抽出した五線bboxでYをclipして置換。CNN判断を変更せず、scoreを新cropへ流用する主張もしない。
2. **候補正規化+同じCNN**: 全保持候補へ同じclipを適用し、元HOMRのclip片のうち
   既存SR/OMRとのIoU>0.5合意を満たす片もseedに追加。新bbox392件だけ同じCNNをCPUで実推論。
   既存bboxは元scoreを維持。既存staff overlap filterを通す。原pipelineのHOMR/SR/走査全体を
   rerunした実装候補ではなく、保持出力への成分置換/追加実験。

| 全68ページ | 原保持 | 採用後分割 | 候補正規化+CNN |
| --- | ---: | ---: | ---: |
| GT | 3567 | 3567 | 3567 |
| 候補 | 29612 | 29612（未変更） | 29859 |
| 予測 | 3646 | 3669 | 3817 |
| TP | 3535 | 3542 | 3560 |
| hard FP | 11 | 0 | 0 |
| FN | 32 | 25 | 7 |
| 旧FN_det / FN_cnn | 27 / 5 | 未再定義 | 2 / 5 |
| soft（原matcherのduplicate/repeat_like） | 100 | 127 | 257 |
| 小節総数 | 3287 | 3287 | 3287 |

採用後分割では全68ページのgrouping/count/bboxが元出力と一致し、抜けた五線は復帰しない。
候補正規化+CNNでは68ページとも小節数不変、67ページは五線所属/小節bboxも完全一致。
Sym5/page_005だけ、上記の下側五線が4小節領域へ復帰する。
ページ別TP減少、FP増加、FN増加は0。ただし **softは157増加**し、独立strokeの重複表現が増える。
原matcherがsoftをhard FPへ数えないことを明示し、指標改善を全出力品質の保証に使わない。

残るFN7は二重線5とSibelius/page_001のID3/4。
ID3/4の候補はY=1445..1737、上側五線との交差が5pxだけで、分割ルールの
「2五線に各2unit以上」から外れる。下側cropは高scoreだが、一般規則でそのcropを
生成できていない。connectorから1五線までの部分bboxの正規化が別の必要条件。
ここを結果後にthreshold調整して既存実験のpassへ変えることはしていない。

変更後のMMR/OCR再推論、認識結果の新幾何への適用、レビューUI、最終PDF、GPU full pathは未検証。
プロダクションの改善として受理するには、focused実装ごとのこれらの関連gateが必要。

## 全43件の下流対応

IDは既存#409/#415監査と共通。FP=予測index、FN=GT index。全件のimage/GT/pred/candidate/
producer/SR/OMR/CNN/matcher/hash、局所対応とbboxは保持JSONにある。
表の「領域」は単独oracle補正後の小節bbox/五線所属、最終列は成分候補で元残差が残るか。
全件の小節数差は0で、FN補正はGT strokeを直接挿入した原因診断。モデルの達成精度ではない。

| ID | 元bucket | 原因（診断） | score/page | index | 単独補正の領域 | 成分候補で残存 |
| --- | --- | --- | --- | ---: | --- | --- |
| 1 | FP | 接続bbox重複 | Sibelius/page_001 | 22 | 一致 | いいえ |
| 2 | FN_det | 長いbbox・採用 | Sibelius/page_001 | 16 | 一致 | いいえ |
| 3 | FN_det | 長いbbox・採用 | Sibelius/page_001 | 17 | 境界bbox変更 | はい |
| 4 | FN_det | 長いbbox・低score | Sibelius/page_001 | 18 | 境界bbox変更 | はい |
| 5 | FN_det | 長いbbox・採用 | Sibelius/page_001 | 19 | 境界bbox変更 | いいえ |
| 6 | FN_det | 長いbbox・採用 | Sibelius/page_001 | 20 | 境界bbox変更 | いいえ |
| 7 | FN_det | 長いbbox・採用 | Sibelius/page_001 | 21 | 一致 | いいえ |
| 8 | FN_det | 長いbbox・低score | Sibelius/page_001 | 22 | 一致 | いいえ |
| 9 | FN_cnn | 二重stroke不足 | Sibelius/page_001 | 36 | 一致 | はい |
| 10 | FP | 接続bbox重複 | Sibelius/page_002 | 51 | 一致 | いいえ |
| 11 | FP | 接続bbox重複 | Sibelius/page_002 | 76 | 一致 | いいえ |
| 12 | FP | 接続bbox重複 | Sibelius/page_003 | 17 | 一致 | いいえ |
| 13 | FN_cnn | 二重stroke不足 | Sibelius/page_003 | 4 | 一致 | はい |
| 14 | FN_cnn | 二重stroke不足 | Sibelius/page_003 | 7 | 一致 | はい |
| 15 | FP | 接続bbox重複 | Sibelius/page_004 | 14 | 一致 | いいえ |
| 16 | FN_cnn | 二重stroke不足 | Prok1/page_004 | 31 | 一致 | はい |
| 17 | FN_cnn | 二重stroke不足 | Prok1/page_005 | 41 | 一致 | はい |
| 18 | FP | 接続bbox重複 | Sym5/page_003 | 38 | 一致 | いいえ |
| 19 | FP | 接続bbox重複 | Sym5/page_005 | 12 | 一致 | いいえ |
| 20 | FP | 接続bbox重複 | Sym5/page_005 | 29 | 一致 | いいえ |
| 21 | FN_det | 合意棄却+existing抑制 | Sym5/page_005 | 22 | 境界bbox変更 | いいえ |
| 22 | FN_det | 長いbbox・採用 | Sym5/page_005 | 23 | 境界bbox変更 | いいえ |
| 23 | FN_det | 長いbbox・低score | Sym5/page_005 | 24 | 境界bbox変更 | いいえ |
| 24 | FN_det | 長いbbox・低score | Sym5/page_005 | 25 | 一致 | いいえ |
| 25 | FN_det | 長いbbox・採用 | Sym5/page_005 | 26 | 境界bbox変更 | いいえ |
| 26 | FN_det | 合意棄却+existing抑制 | Sym5/page_005 | 40 | 五線所属変更 | いいえ |
| 27 | FN_det | 合意棄却+existing抑制 | Sym5/page_005 | 41 | 五線所属変更 | いいえ |
| 28 | FN_det | 長いbbox・低score | Sym5/page_005 | 42 | 五線所属変更 | いいえ |
| 29 | FN_det | 合意棄却+existing抑制 | Sym5/page_005 | 43 | 五線所属変更 | いいえ |
| 30 | FP | 接続bbox重複 | Sym5/page_018 | 15 | 一致 | いいえ |
| 31 | FP | 接続bbox重複 | Sym5/page_018 | 32 | 一致 | いいえ |
| 32 | FN_det | 合意棄却+existing抑制 | Sym5/page_018 | 6 | 境界bbox変更 | いいえ |
| 33 | FN_det | 長いbbox・採用 | Sym5/page_018 | 7 | 一致 | いいえ |
| 34 | FN_det | 長いbbox・採用 | Sym5/page_018 | 8 | 一致 | いいえ |
| 35 | FN_det | 合意棄却+existing抑制 | Sym5/page_018 | 9 | 一致 | いいえ |
| 36 | FN_det | 長いbbox・採用 | Sym5/page_018 | 10 | 境界bbox変更 | いいえ |
| 37 | FN_det | 合意棄却+existing抑制 | Sym5/page_018 | 11 | 境界bbox変更 | いいえ |
| 38 | FP | 接続bbox重複 | Sym5/page_021 | 27 | 五線所属変更 | いいえ |
| 39 | FN_det | 合意棄却+existing抑制 | Sym5/page_021 | 46 | 一致 | いいえ |
| 40 | FN_det | 長いbbox・低score | Sym5/page_021 | 47 | 境界bbox変更 | いいえ |
| 41 | FN_det | 長いbbox・採用 | Sym5/page_021 | 48 | 一致 | いいえ |
| 42 | FN_det | 長いbbox・低score | Sym5/page_021 | 49 | 一致 | いいえ |
| 43 | FN_det | 合意棄却+existing抑制 | Sym5/page_021 | 50 | 一致 | いいえ |

## focused修正への分割案

- **五線別strokeとconnectorの表現正規化**: 合意前/候補生成後/CNN入力の責務を整理し、
  複数五線bboxと1五線+connectorの両方に対応する。connector情報を失わず、同じstrokeの
  重複片を整理する。固定Full68で旧指標全部、soft増加、下流所属/bbox、MMR/最終番号を検証。
  本調査の成分実験はこの修正の実現可能性を支持するが、本番実装としては受理していない。
- **走査抑制のY被覆契約**: 上側1五線のbboxだけで下側/上下band全体の救済を抑制しない。
  resolution-normalizedな被覆条件にする。通常の同一stroke抑制、同じXの別五線、
  divisi/connectorの反例と原Full68を固定し、候補膨張や新FPを報告する。CNN閾値変更は不要。
- **double/end/repeatの独立stroke抽出**: ID9/13/14の2本1bboxとID16/17の左stroke不足を
  producer内で分ける。五線spaceを基準にする。GTの独立stroke契約と、番号処理で
  1物理時間境界へまとめる契約を両方検証。CNN再学習やmatcher変更を初手にしない。

これは修正範囲/受入条件の提案。外部Issueの新規作成、Issue本文/コメント更新、PR作成、
commit/push/mergeは今回行っていない。GT修正として除外した案件は0。

## 再現・保持成果物と検証結果

このworktreeの `logs/issue416/causal-audit-20261015/` にまとめて保持（ignored、GitHub添付ではない）。
入力rootは元checkout `/home/masaki_muramatsu/ws_PDFScoreBar`、コードrootは本worktree。
これらのスクリプトは `__file__` から両者を特定するローカル調査用で、fresh-clone用CLIではない。
同じ元データ/保持出力がない環境では実行できない。

元checkoutからの実行コマンド（いずれもexit 0、ログは同root）:

```bash
.venv_pdf/bin/python -u .worktrees/issue416/logs/issue416/causal-audit-20261015/investigate.py
.venv_pdf/bin/python .worktrees/issue416/logs/issue416/causal-audit-20261015/probe_trace.py
.venv_pdf/bin/python .worktrees/issue416/logs/issue416/causal-audit-20261015/crop_experiment.py
.venv_pdf/bin/python -u .worktrees/issue416/logs/issue416/causal-audit-20261015/component_experiment.py
.venv_pdf/bin/python .worktrees/issue416/logs/issue416/causal-audit-20261015/record_findings.py
```

- `contract.json`, `component-contract.json`: 実行前の実験定義/契約/モデル/runtime。
- `input_sha256.json`（599入力）, `component-input-sha256.json`（967入力）: 消費入力のhash。
- `run.log`, `results.json`: 原指標/68ページexact replay/採用後分割/全残差・全GT oracle。
- `residuals.json`: 初期自動trace。`adjudicated-residuals.json` がfirst-observable problemと
  複数段の原因連鎖を裁定した最終記録であり、初期自動ラベルを原因確定と扱わない。
- `probe-trace.log/json`: 3ページのgeneration/rescue exact replay、9件の局所判断。
- `crop-experiment.log/json`: 27 FN_det位置の局所CNN/合意正規化。18元候補のCPU採否比較。
- `component-experiment.log`, `component-results.json`, `component-output/`: 68ページ全件の
  成分候補/score origin/予測/geometry/指標、CPU新crop392件。
- `record_findings.py`: この記録と最終43件裁定の生成。
- CPU環境: host `.venv_pdf`、Python 3.10.12、OpenCV 4.11.0、torch 2.7.1+cu126、
  inference deviceを明示的にCPUへ固定。重みは共有model cacheからhash検証して読み取り。
- 原画像/既存監査hash照合、68ページmetrics/exact geometry、3ページraw/rescue再現、
  component全68ページ、局所CNN、script compile、相互成果物整合性/相対リンク/whitespace check: pass。
- trace収集スクリプトの初回はdebug callback差し替え先とNone band処理で失敗した。
  調査scriptだけ修正し、上記3ページの保持出力完全一致を通して最終証拠を採用した。
- GPU smoke/full inference、MMR/OCR/最終PDF再生成、`make test-fast`: 未実施。
  production source/config/model/GTは未変更、実行経路はCPUの成分診断/retained replayであるため。
  runtime変更のvalidationをpassしたとは報告しない。番号意味の追加検証はfocused実装時に必要。
