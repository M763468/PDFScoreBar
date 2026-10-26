# Issue #441: MobileSheets利用を踏まえた方式比較

2026-10-25。
[追加レビュー](https://github.com/M763468/PDFScoreBar/issues/441#issuecomment-6370428439)
への対応。[初回記録](ISSUE441_PHASE0.md)の注釈保持PoCと履歴監査の結果は維持する。
「初回方式では焼き込みを拒否した」という結果を、将来の対応を排除する仕様判断にはしない。
今回も製品コード・認識アルゴリズム・GT・閾値は変更していない。

**実サンプル受領後の追記:** ユーザー提供のMSF/PDFを使った
[実出力確認](ISSUE441_MOBILESHEETS_SAMPLE.md)を実施した。
以下の「実出力未取得/Not run」は本比較時点の履歴であり、現在の確認状況は追記先を参照。
実機操作・OS/版/設定・Swap Fileは引き続き未確認。

## 実機・実出力と資料の区別

MobileSheetsのOS・版・書き出し設定は未取得であり、実機、当該アプリがexportしたPDF、
Swap Fileの実操作、アプリ上の表示・印刷・再exportは **Not run**。
manager checkoutの`temp/`・`tmp/`内を確認したが、MobileSheets出力と識別できるファイルは
見つかっていない。名称が不明なPDFを当該アプリのサンプルだと推定しない。
個人の楽譜・PDF・correction JSONは公開しない。

以下は2026-10-25に読み直した開発元資料であり、今回の実機確認ではない。

- [2025-01-13開発元回答](https://www.zubersoft.com/mobilesheets/forum/thread-12714.html):
  `Export iOS compatible annotations`が無効ならPDF注釈を追加し、有効なら
  レンダリング画像から新PDFを作るとの説明。MobileSheets利用＝常に焼き込みとは扱わない。
- [2026-08-01と08-18の開発元回答](https://zubersoft.com/mobilesheets/forum/printthread.php?tid=15556):
  Androidの注釈付きexportの案内がある一方、注釈欠落の報告に対しPDFライブラリの修正を
  含む更新予定の説明もある。利用者の版で修正済みとは確認できていない。
- [2024-02-01開発元回答](https://www.zubersoft.com/mobilesheets/forum/thread-11028.html):
  Swap Fileで注釈を保持してファイル交換する案内。
- [2025-05-10開発元回答](https://www.zubersoft.com/mobilesheets/forum/thread-13010-page-2.html):
  PDFへ埋め込んでいないMobileSheets内部の注釈が条件。
- [寸法に関する開発元回答](https://www.zubersoft.com/mobilesheets/forum/thread-6811.html):
  注釈は元ファイルのページ寸法に依存し、交換先寸法が異なる場合は位置に影響する。

初回Issue本文の外部アプリ個別の互換性調査はOutという境界に対し、追加レビューで依頼された
公式資料の確認と少数fixtureの方式比較だけを実施した。アプリ専用実装・互換性保証へは広げない。

## 比較と推奨

操作数は未実装GUIを含む**概念上の手順**であり、実機で測ったタップ数ではない。
コストは相対的な設計見積もりで、測定した工数ではない。

| 方式 | コスト・安全性 | 旧ジョブとの関係 | 利用者の流れ・判定 |
| --- | --- | --- | --- |
| A: 注釈付きexport→背景交換 | PDF部分は中。既知背景と寸法が一致した独立注釈を保持。背景不一致・未知の注釈は拒否 | 不変snapshot・clean source・背景の出所が検証できれば候補。旧寸法は別判定 | export→checkpoint選択→upload/照合→編集/生成→再import。**#441の主経路候補**。MobileSheets実exportでの成立は未確認 |
| B: clean PDF再生成→Swap File | PDFScoreBarのPDF移植部分は小。内部注釈を移植しない。寸法・ページ対応が必須 | checkpointからclean結果を生成する点は共通。旧寸法を保つ出力が別途必要 | checkpoint選択→編集/生成→Swap File。**実用上簡潔な併設候補**。実機未確認、書き込み済みPDF再入力という現受入を自動的に満たさない |
| C: 新出力の番号を独立要素化 | 中〜大。Stream/OCGは成立したがrewrite/flattenで識別が失われる。注釈方式の単純な削除・再追加は表示不一致 | 過去の番号込みJPEGを自動変換する方式ではない。新出力に将来の利点 | 将来Aの識別・交換を補助。**今Issueの必須変更から保留**。注釈化だけで常に交換可能とはしない |
| D: 旧番号の局所修正 | 大。ROI内の書き込み/JPEG差分/不可視の重複を安全に判断する必要 | 旧ラスタを救済できる可能性はあるが、現データで安全な成功判定は未確立 | upload→照合/拒否→編集/生成。**条件付きPoCのみ、一般入力の成功経路は保留** |
| 補助: marker/metadata/sidecar | 小〜中。生成元・ページ・番号配置の照合を補助するが消去・書き込み保持そのものは実現しない | 過去データに存在しない情報は作れない。retained identityを利用 | PDF内ID＋外部manifest/digestを併用する案。再exportで失われ得る情報だけに依存しない |

推奨は **Aを#441の主経路候補とし、Bを利用者向けの代替導線候補として併設できる設計**。
ただしBによって「書き込み済みPDFの再入力」を受入から外す決定は行わない。
Aの背景検証に失敗した入力を、黙ってBへ切り替えたり、clean結果だけを成功として返したりしない。
PDF入力を保持して理由を表示し、Bは利用者が明示的に選ぶ操作とする。
MobileSheetsに元の内部注釈が残っていない場合、Bで復元できるとは案内しない。

C/D/補助情報の全方式を今Issueで実装する必要はない。今回の比較から、Cは将来の出力形式の
改善候補、Dは制約の強い救済研究として保留し、checkpoint・再開導線を優先する。
焼き込みの一般対応を恒久的に排除する仕様は確定していない。

## focused PoCの結果

コード: [`tools/issue441/method_comparison.py`](../../tools/issue441/method_comparison.py)。
初回`phase0_probe.py`を再利用し、すべて人工fixtureで実行した。
新規ページは300×400 pt、背景画像は600×800 px。ペンの線、半透明Highlight、
FreeTextの練習メモを作成し、ペン・Highlightを番号領域に重ねた。
これはMobileSheetsが生成したオブジェクトを再現したという意味ではない。

### A: 背景交換

3種類の注釈を持つ入力で、注釈外観・座標・メタデータを保持し、新番号背景と全体一致した。
寸法変更は拒否し、拒否出力を作らず、入力digestも不変。正しい寸法が一致する通常経路のfixture。
物理印刷・MobileSheets表示は未確認。

### C: 独立Stream / OCG / FreeText番号

- StreamとOCG: 番号専用のcontentを識別して12→42へ交換できた。
  利用者の注釈signatureと、期待する新PDFの全ページ描画が一致した。
- FreeText番号: 番号だけを削除・再追加する単純方式は **Failed**。
  利用者注釈のsignatureが同じでも重なり順が変わり、Highlightとの合成後表示は期待値と不一致。
  signature一致だけでは表示保持の証拠にならない。番号annotationにPrintフラグを付けたが、
  実印刷の受入は未実施。重なり順を保つ更新方法は将来検討であり、今回の失敗を取り消さない。
- 全方式: 画像へflattenすると独立番号のidentityが失われた。Stream/OCGでは
  `save(clean=True)`によるrewriteでも表示は同じままcontentの識別markerを失い、拒否した。
  これはPyMuPDFでの特定操作であり、MobileSheetsが同じrewriteをするという推定ではない。
- PDF metadataだけを消したfixtureは表示が不変だった。別のcontent markerはこの保存では残る。
  marker/metadataの存在だけでは出所・編集可能性・書き込み保持を証明できない。
  sidecarにjob/checkpoint/result ID、page mapping、番号描画領域、artifact hashを残し、
  PDF内情報の欠落を検出する補助にする。sidecarがあっても消失した注釈や画素は復元されない。

### D: 既知領域だけの局所修正

旧番号・新番号の両方を含む既知ROIを、cleanな新番号画像で置換するfixtureを作成した。
領域外の赤い書き込みを画素単位で保持した成功例は、**生成時に非重複と分かるlossless fixture限定**。
`label_bbox`だけでhalo・実際のフォント描画・新旧の配置差をすべて覆えるとは仮定していない。
製品化時には各描画の支持領域と座標変換が必要。

可視の重複とJPEG再符号化はROI内画素差分を検出して拒否した。
閾値を緩めてJPEG差分を手書きと区別できたことにはしない。
ROIの画素一致だけでは黒い旧番号に隠れた黒い書き込みを検出できないため、
非重複の別証拠がない入力は一致していても拒否する。
fixtureのground truthを利用者の「重なっていない」チェックボックスで代用する設計ではない。
**一般ラスタ入力の安全な非重複判定は未確立**であり、任意の焼き込み入力を受け入れる結果ではない。

## 正常寸法とレガシー寸法の別判定

元720×936 ptと旧出力3000×3900 ptの差は、旧生成物のレガシー互換性問題。
新規入力が毎回異なる寸法になるという意味ではない。正常寸法のAとは別の評価とする。

| 方針 | 今回の判定 |
| --- | --- |
| 旧生成PDFの寸法を保持して更新 | 初回15ページ背景交換で成立。既存の座標を保持する互換経路として候補。元PDFの紙寸法を回復したとは扱わない。Bの交換先も既存MobileSheetsの参照寸法と合わせる必要 |
| 旧出力を元寸法へ明示変換 | 3000×3900→720×936、原点0、CropBox=MediaBox、rotation=0、Inkのみのsynthetic fixtureで0.24倍変換が成立。頂点・線幅を変換し、同じ描画解像度で背景＋Inkの全画素が一致 |
| crop/rotation/縦横別倍率/他注釈 | 単純スケール対象から拒否。一般的な変換を実装済みとはしない。実15ページimport・MobileSheets内部注釈の変換は未実施 |

明示変換PoCは`show_pdf_page`で背景をコピーし、対応を確認したInkだけを再構築した。
そのAPIで注釈まで自動コピーされるとは扱わない。Highlight/FreeText/画像stamp等を黙って捨てない。
旧寸法保持と明示変換は別の選択としてprovenanceに記録し、正常化を自動で選ばない。

## checkpoint / 状態復元をPDF方式と独立して進める境界

PDF方式の最終選定や実機入手を、checkpoint/state部分の着手条件にはしない。
最初の実装commitでは初回設計どおり、保存済みraw修正の不変snapshot、選択一覧、
元packageを変更しない新packageへの状態復元を扱える。

- checkpointは修正状態の出所を表し、PDF annotation方式やMobileSheets設定を必須schemaにしない。
  入力背景のresult identityや再開PDFは別のresume contextとして関連付ける。
- 旧attemptの復元可能性と成功applyの証明を区別し、成功結果がないsnapshotも「保存状態」として
  明示的に扱う。上書きされた未apply保存履歴を作らない。
- 2つ以上のcheckpointを独立packageへ復元し、MMR/小節構成/小節線/movementの変更と取消、
  Save、既存authoritative downstream applyへ渡すfocused testを優先する。
- PDFなしの状態復元ができても、#441のPDF再入力・保持・GUI受入全体を完了とはしない。
  A/Bどちらの再生成経路でも、同じcheckpointと新結果の対応を使えるようにする。

今回の変更は依頼された小規模な追加調査までで、上記の製品実装は未着手。
次の実装をPDFの未解決条件だけで停止する方針にはしない。1本のFeature PRを基本に継続し、
C/Dのための追加PRやサブIssueは作らない。

## 検証記録

base: `b679a6dc80d3b57497348f5511ed68b1f41bb1d3` + 今回の独立PoC。
実行ファイルのSHA-256は`run-05/summary.json`内の`probe_sha256`に保存。
今回の値は`02ca9c9fc35cdba2322b11a88103cb7a897bb6e4635c858a529084114db87bb3`。
環境: `pdfscore_pipeline_pytest_dev`、image
`sha256:5311cf22ab0198c3384ada62101f195b0bacf6d2079574167a0edb3f66854005`、
PyMuPDF 1.26.4、UID/GID 1000:1001。manager bindは`/workspace`、
実行worktreeは`/workspace/.worktrees/issue441`。個人データは入力せず人工fixtureのみ。

```bash
docker exec --user 1000:1001 \
  -w /workspace/.worktrees/issue441 \
  -e PYTHONPATH=/workspace/.worktrees/issue441 \
  pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python \
  tools/issue441/method_comparison.py \
  --output logs/issue441/phase0/method-comparison/run-05
```

新しい実行は未作成の出力先を指定する。
ログ・PDF・PNGはignored `logs/issue441/phase0/method-comparison/` 内だけに保持。
スクリプトのexit 0は比較手続の完了を意味し、Cの番号注釈候補を成功へ変更する意味ではない。

| チェック | 今回の状態 / 証拠 |
| --- | --- |
| A、C Stream/OCG、Dの条件付きfixture、制約付き旧寸法変換 | Passed: run-05、exit 0、`run-05/summary.json`。AのPNGも目視確認 |
| Cの番号注釈の削除・再追加 | **Failed**: run-03で全体描画不一致。run-05でもfailedとして記録。利用者の注釈signature一致では不足 |
| rewrite / flatten / metadata削除、Dの不確実入力、旧寸法変換の制約外入力 | Passed: 検出・拒否・能力境界を確認。成功対応の証拠ではない |
| 初期harness | Failed: run-01は利用者FreeTextもtext抽出されることを考慮しないassert。run-02はAnnotの親Page参照の寿命で例外。修正後もログを保持 |
| 静的検証 | Passed: `ruff check tools/issue441/method_comparison.py`、`git diff --check` |
| MobileSheets実出力(a)/(b)、Swap File(c)、OS/版/設定、実印刷・再export | Not run: サンプル・実機が未入手。synthetic成功から互換性を主張しない |
| 旧15ページの再推論・新checkpoint/GUI受入 | Not run: 追加の方式比較範囲外。旧15ページの初回結果は過去証拠として維持し、今回再実行と混同しない |
| GPU smoke / Full68 / test-fast | Not run: 独立PoCと記録だけで製品経路は変更なし。モデル・実データ推論を行っていない |

owner判断が必要なのは、Bを現受入の代替として採用する場合、焼き込みの製品対応範囲を
確定する場合、旧寸法保持を元の紙寸法保持と別の互換受入にする場合。
本調査では従来の受入条件を変更していない。これらと独立したcheckpoint/state復元は先行可能。
