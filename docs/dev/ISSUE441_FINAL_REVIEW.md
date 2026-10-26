# Issue #441 / PR #445: 最終レビュー指摘の対応

追記: [通常レビュー後の3件の修正・今回の検証](ISSUE441_ADDITIONAL_REVIEW.md)を参照。
以下は451b4209時点の履歴。ownerによる範囲確定・Draft解除はその後のPR記録を正とする。

対象レビューは [fff311f2に対するレビュー](https://github.com/M763468/PDFScoreBar/pull/445#pullrequestreview-5644080686)。
CI分類エラーを修正し、旧jobの履歴をGUIから取り込む導線と、再開セッションから再び再開する経路を追加した。
事前に作ったcheckpointを使わず、実旧jobのattempt 1/12を選択するブラウザー受入、
4種類の追加・保存・適用・取消、製品結果へのsynthetic注釈追加後の2回目再開を完了した。

[公開スナップショット](issue441/evidence/final_review_snapshot.json)に入力固定条件・実行コードhash・
11出力のhash/集計・全ゲートを記録する。画像・注釈本文・correction JSONは含めない。

## 指摘への対応

| 指摘 | 対応 |
| --- | --- |
| Repository surfaceのCI失敗 | `number_layer.py`をruntime sourceに分類。新旧の3テストをmaintained contractへ分類。legacy adapterを配布対象へ追加し、現在の113 files / src 86 filesへsummaryを整合。PoC/検証runnerはdevelop-only validationとして明示 |
| 旧attemptのGUI選択 | 「旧バージョンの保存済み入力」一覧と検証付き取り込みを追加。旧jobの12件を一覧し、1/12を取り込んで再開。元source identity・correction identity・consumed identityを再現して照合。PDFがあることだけでは成功扱いしない |
| 反復往復 | session内のcheckpointから別セッションへ再開可能に変更。registryと所有番号検索は生成元rootへ束ね、親sessionの成功PDF/sidecarを使う。追加注釈と過去成功を保持し、異なる旧checkpointを明示選択 |
| 4種類のGUI受入 | 各種類で画面操作による追加・保存・実consumer適用・取消を検証。小節線とforce_measureの同一ページ同時変更は既存の安全拒否を維持し、独立ケースで受入 |
| 目視フィードバック | 1の位置は非重複を優先。8→9はテスト用変化であり正解承認ではない。12/41/42は印刷された練習番号として背景保持対象。1003/1011等は目視依存にせず自動境界検査 |

### 旧履歴を信用する条件

[legacy.py](../../tools/review_correction/legacy.py)はpackage内の`application_runs/attempt_*`だけを対象にする。
既存handoffと保存snapshotのページ構成・元artifact bytesを比較し、保存時のsource identityを
元handoff bytes・source artifact hashes・retained manifest bytesから再現する。
correction identityとconsumed identityも検証する。source_manifestだけを旧runtimeの絶対パスから
現在の同一retained layoutへ対応付け、独立stagingへコピーして不変checkpointを作る。
原snapshot・consumed record・過去PDFは変更しない。

imported checkpointには元attempt・元identity・consumed/handoff/manifestのhashを記録する。
そのcheckpoint自体の現在のidentityと、元記録のidentityを混同しない。
入力の検証成功は旧PDFの適用成功認定ではなく、再開後のApplyで初めて新しい成功結果を記録する。
検証できない履歴は理由付きで使用不可として表示する。

### 2回目の再開

[resume.py](../../tools/review_correction/resume.py)はcheckpointの保存元packageと、所有番号の証拠を探す
生成元packageを別々に受け取る。新sessionは生成元rootのregistry直下に確定し、元sessionと状態を共有しない。
コピーされた既存resume artifactsを更新できるようにし、元入力と番号除去後の背景を引き続き別々に保存する。
取り込んだPDFの所有番号160個を検証・除去し、追加されたnative注釈を含めて再生成する。

### ページから番号を切らない保証

配置候補は数字字形のink bboxと余白がCropBox内にある場合だけ採用し、場所がなければエラーにする。
さらに保存後に再openしたPDFでも、全番号bboxの有限性とvisible CropBox包含を明示例外で検査する。
字形計測に使ったHelvetica-Bold/WinAnsiと実際の番号font resourceも照合し、
既存PDFが同名aliasを別フォントへ結び付けていた場合も、未検証の出力を公開しない。
`1003`・`1011`・`1234567890`を左上の境界近くへ置くfixtureで、字形bbox包含・完全な文字列・
ページ端への非接触を確認。外に出たbboxを保存後validatorへ渡すケースも拒否する。
今回の全11出力・各160番号を最終validatorで再照合し、全て包含した。

## 今回の検証結果

固定条件はprivate `logs/issue441/pr445-final-review/plan.json` と公開snapshotのproducer_plan。
入力は既存15ページnative注釈PDF（SHA-256 `c52167c534ebde75150c7c52c11f7051e864390cfa2103640f631b0644bb89c2`）、
元job `job-5969eee679e540d282e23fb3ecdfe205` の保存済みattempt 1/12。
旧jobは通常の内容コピーを使って独立したdirectory treeへ複製し、元はread-only mountで保持した。
旧アプリの状態file/lockはコピーせず、保存済み入力の検証だけで取り込む。

| 確認 | 今回の状態 | 結果・証拠 |
| --- | --- | --- |
| 関連pytest + release | Passed | 228件。[標準出力](issue441/evidence/final-review-regression-tests.txt) |
| maintained fast tests | Passed | 122件。[標準出力](issue441/evidence/final-review-fast-tests.txt) |
| Actionsと同じengine contract gate | Passed | 101件。[標準出力](issue441/evidence/final-review-engine-contract.txt) |
| 最終surface / release / distribution | Passed | surface成功、release/distribution 67件。新しいsourceを除外して通していない |
| make lint / Makefile参照 | Passed | `make lint`と`make check-makefile`。初回uv cacheのread-only Blockedはsandbox外実行で解消 |
| 旧履歴のGUI受入 | Passed | 12件を一覧。1/12を別々に取り込み、correction identity・全15ページの番号列が元の保持結果と一致。旧成功扱いを継承しない |
| MMR | Passed | first measure 1→2、1ページ2段目8→9、取消で8。全ページの番号列も復帰 |
| 小節構成 | Passed（下記範囲） | 既に計数されているinterval 0へforce_measureを明示保存。consumerのapplied override flagを確認。番号列は不変というidempotent操作と、その取消を確認 |
| 小節線 | Passed | 第1段の内部小節線を除去しphysical measures 7→6、次段8→7。取消で全番号列復帰 |
| 楽章境界 | Passed | 第2段の前に境界を追加し次段8→1。取消で全番号列復帰 |
| 2回目の再開 | Passed（synthetic） | 実製品結果へFreeTextを1件追加してannotation-only再輸出。親sessionの旧checkpointを選び、元correction identityを復元。注釈729→730、active番号streamは160個で二重化なし |
| 拒否時の保持・再起動 | Passed | 回転を変えた再入力は400で拒否。成功PDFは不変。新serverでも同じ第2session/current/result hashを復元 |
| 印刷物/他export設定/手動配置UI/Full68 | Not run | 下記の境界判断参照。実機での2回目MobileSheets再輸出は未実施で、syntheticと区別 |

4種類のうち、小節構成は除外intervalを新たに救済する実楽譜例ではなく、現行GUIで選べる既存intervalへの
明示forceとconsumer入力の検証。全ての操作の組合せや、全小節番号の音楽的正確性を証明したものではない。
上流の認識アルゴリズム・モデル・閾値を変えていないため、Full68/上流再推論は実行していない。
MMR OCRの実providerは全11適用でCUDAを含むことを確認し、fallbackを代用しなかった。

全画像を再生成する推論は、保存後CropBox検査の追加だけのためには繰り返していない。
GUIで得た出力を保持し、CropBox検査を加えた`_validate_saved_output()`で全11出力を再open・再採点した。
その後のfont resource条件も同じ出力hashに対して別途確認した。
最終の追加検査はfocused testsと関連228件の最終差分でも実行した。

初回copy案のhardlinkは自動承認レビューで元inode共有の危険を指摘され、実行せず通常copyへ変更した。
再起動照合runnerの初回は変数参照の誤りでFailedとなり、修正後に保存済み出力を使って成功した。
どちらも推論や受入条件を変更する理由にはしていない。失敗/Blockedログはprivate rootに保持する。

## 実行と再現

実行root: `logs/issue441/pr445-final-review/`。コード基点は `fff311f2`。
現行差分のsource hashは公開snapshot、実行対象patchはprivate `validated.patch`。
作業cwdは `.worktrees/issue441`、host Pythonはmanager checkoutの`.venv_pdf/bin/python`。

実GPU imageは `sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`。
UID/GID 1000:1001、managerを`/workspace:ro`、Issue441 logsだけを同位置rwでmount。
`/workspace/.worktrees/issue441`をcwd/PYTHONPATHに設定し、`PYTHONDONTWRITEBYTECODE=1`。
runtime resolverで互換性を確認した。認識factoryのwrapperは本物のfactoryを呼び、実providerを取得して
CUDAがなければ失敗するだけで、入力・model・閾値の置換はしていない。

新checkpointを作成していない旧jobのコピーを、標準serverで開く:

```bash
python -m tools.review_correction.server \
  --handoff logs/issue441/pr445-final-review/legacy-job/job-5969eee679e540d282e23fb3ecdfe205/review/manual_correction_input.json \
  --port 8441
```

[実ブラウザーrunner](../../tools/review_correction/continuation_browser_acceptance.cjs)を次の形で実行。
ブラウザーimageは `sha256:8771dc4666e7c11440bfc6a0c6b00480e9a15b8891b45f29a52d7d995f8d1492`、
同一host network、source ro・evidence rw・native注釈PDFを`/private/input.pdf:ro`へmount。

```bash
PLAYWRIGHT_MODULE=/app/node_modules/playwright \
CHROMIUM_PATH=/ms-playwright/chromium-1226/chrome-linux64/chrome \
node tools/review_correction/continuation_browser_acceptance.cjs \
  http://127.0.0.1:8441 /private/input.pdf /evidence
```

runnerが`ready-for-return.json`を保存したら、そこで指定された実結果を開き、1ページ目に
FreeText「synthetic round two」を追加、`garbage=4, deflate=True`で再輸出した。
回転90度の拒否fixtureも同じbytesから別に作り、完成したPDFをatomic renameでrunnerへ渡した。
これはMobileSheets実機操作の模倣fixtureであり、2回目の実機試験とは記録していない。

[独立照合コード](../../tools/issue441/verify_remaining_review.py):

```bash
python -m tools.issue441.verify_remaining_review \
  --root logs/issue441/pr445-final-review \
  --job logs/issue441/pr445-final-review/legacy-job/job-5969eee679e540d282e23fb3ecdfe205 \
  --output logs/issue441/pr445-final-review/verified.json
# serverを停止・再起動後、既に検証した全出力hashも確認してHTTP復元だけを追加
python -m tools.issue441.verify_remaining_review \
  --root logs/issue441/pr445-final-review \
  --job logs/issue441/pr445-final-review/legacy-job/job-5969eee679e540d282e23fb3ecdfe205 \
  --output logs/issue441/pr445-final-review/verified.json --url http://127.0.0.1:8441 --restart-only
```

ローカル回帰はPR本文のexact pytestリスト（前段の198件の組合せに既存release testsと今回のfocused casesを追加）。
採用ログは`regression-final-02.log`、`fast-final.log`、`engine-contract-final.log`、`distribution-final.log`、
`surface-final.log`、`lint-final-02.log`、`browser-01.log`、`verify-01.log`、`verify-font-restart.log`。
Actions最終headの結果はPR checksとPRコメントに記録し、このローカル実行とは区別する。

## 受入範囲とマージ判断

Issue本体は、特定保存状態からの再開、修正継承、書き込み保持、整合しない入力の安全な拒否を要求している。
今回この経路を実データ・旧履歴・反復fixture・4種類の代表GUI操作で検証できた。
限定的な目視承認を、全番号の正確性や印刷品質の承認として扱わない。

手動配置UI、実印刷品質、外部ソフト全設定の互換性は本PRの必須条件から分け、後続扱いとするのが妥当と判断する。
根拠はIssueが不一致時の明示拒否を許し、外部書出し仕様調査・新規注釈編集・認識精度変更をOutとしているため。
空白不足時は失敗を表示し、元の成功結果を保持する。対応していない機能を完了扱いにはしない。

技術的には、この限定scopeで通常レビューへ進める根拠が揃った。最終CI結果とownerの範囲判断・承認は
PRの最新記録で確認する。既存レビューはapproveではないため、これを自動的なマージ承認とはしない。
マージは実行しない。PDF/MSF・楽譜画像・raw correctionをGitHubへ追加しない。
