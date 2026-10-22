# Issue #441: 保存済み状態からのレビュー再開 — Phase 0 判定

2026-10-23。対象は [Issue #441](https://github.com/M763468/PDFScoreBar/issues/441) と
[最新の作業方針](https://github.com/M763468/PDFScoreBar/issues/441#issuecomment-6347513064)。
`develop` の `9ccd57fbf93ac70bac0ee3a85cfd9ef676c88254` から
`feature/issue441-resume-review` / `.worktrees/issue441` を作成した。
本記録は設計・PoCの結果であり、再開機能を実装・受入済みとするものではない。

## 技術判定

**PDF注釈が独立して残り、背景とページ座標が既知の生成結果から変わっていないPDFは、
背景画像の交換によって書き込みを保持しながら番号を差し替えられる。**
注釈が旧番号に重なるfixtureでも外観・座標・内容を保持できた。
旧番号を白塗りしたり、入力PDF全体を再ラスタ化してから番号を重ねたりする方式は採用しない。

**書き込みがページ画像・本文に焼き込まれた入力は、この方式の対象外として明示的に拒否する。**
重なりがなくても現PoCでは拒否する。背景差分を手書きと推定して移植する処理は採用しない。
特に、黒い旧番号の上に黒い書き込みをした場合、書き込みの有無で同じ最終画素が得られる。
この情報欠落は旧PDF・新PDFの画素差分だけでは復元できない。
一般の焼き込みPDFから「書き込み消失ゼロ」を保証する機能は成立を確認できていない。

この制約を利用者に表示し、独立したPDF注釈を保持した入力を案内することが必要。
焼き込みPDFも成功経路に含めるという解釈では、親Issueの受入を妨げる未解決条件である。
Issueで許容された「安全に保全できない入力の明示的拒否」を用いる場合でも、対応範囲を
GUI・ガイド・受入条件に明記する必要がある。親Issueの全完了条件を満たしたとは扱わない。

## 現行の履歴・状態契約

- `tools/review_correction/server.py:ReviewPackage.record_correction` はページ別の編集を
  correction type別のJSONへatomic replacementする。保存操作ごとの不変履歴は作らない。
  現存する保存済み状態は復元候補になるが、上書きされた過去の未apply保存は復元不能。
- `tools/review_correction/application.py:CorrectionApplication._run` は各
  `application_runs/attempt_XXXX/input_review/` に宣言済みsource/correctionをコピーし、
  `consumed_inputs.json` にsource/corrections identityを記録する。
  downstream applyに伴うcanonicalファイルもsnapshot内に生成されるため、
  rawの宣言済みcorrectionと生成済みcanonical overrideを混同して復元しない。
- `tools/review_correction/state.py` のschema v1が永続化する成功結果は
  `last_successful_result` の1件だけ。過去attemptにPDFがあることだけで、成功確定や
  `finish_apply` 時点の整合性確認を通過したとは断定できない。
  failed/stale applyでも途中成果物が残る可能性がある。
- `apply_error` とpending編集はメモリ上の状態。再起動後のfailed/applying履歴を
  現schemaがすべて保持しているとは扱わない。
- `capture_identity` はhandoffとmanifestの内容も含む。snapshotのhandoffはmanifestを
  絶対パスへ書き換えるため、snapshotから再計算したsource identityを元のidentityと
  単純比較する移行はできない。補正前の記録値を保持し、移行後のidentityを別に記録する。

## 指定された15ページ結果の棚卸し

入力（読み取り専用）:
`temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205`。
生成元は `result.json` 上 `cc28994aaa146365c395f624ec481add5c2c9173`。

| 観測 | 今回の結果 |
| --- | --- |
| attempt | `attempt_0001`〜`attempt_0012` の12件にconsumed inputs / input snapshot / PDFが存在 |
| 修正の識別 | 12件すべてcorrections identityが異なる。宣言済みraw correctionから再計算した値は12件ともconsumed inputsと一致 |
| 異なる選択例 | attempt 1: MMR 14件 / barline 5件、attempt 12: MMR 22件 / barline 26件 |
| 成功の確証 | 現存するlast-success metadataが指すのはattempt 12。PDFのSHA-256と一致 |
| source移行 | snapshotが `/results/...` を参照。現在のmountは `/workspace/temp/...`。移設後source identityは12件とも元記録と不一致 |
| ページ画像 | 生成済みPDFは各ページ1枚の番号込み画像。独立した番号テキストはない |
| 物理寸法 | 保持済み元PDFは720×936 pt、旧生成PDFは3000×3900 pt。handoffに`page_size_points`がない |

元PDF SHA-256: `944fadcc68ea69e3b97897cd1e9fd3dd2ecd1ba467f426e480ed9e62be46d360`。
attempt 1 PDF: `90e29a300cbc633bbd57617708cf3e4dd569feb05f664d96f1a3ecd18d68c19d`。
attempt 12 PDF: `14255a0023beda229f9562b61cfaf0ffa421f9043743b7639a7de8ca97d42b38`。

この旧データは履歴の実例として有効だが、そのまま新実装の正常移行fixtureとはしない。
既存の誤寸法を黙って720×936へ直すと注釈の座標契約も変わる。
元PDFの検証済み寸法への明示的な座標変換を別途検証するか、寸法不整合として拒否する。
元の15ページ結果、修正状態、attempt、PDFは変更していない。

## 採用する実装境界（提案、未実装）

### 不変checkpointと再開セッション

既存handoff/correction schema v1は意味を変えず、独立した
`review_checkpoint` schema v1を追加する。
以下を不変snapshotと対応付ける。

- checkpoint ID、元package/job ID、作成時刻、`saved` / `applied` の区別。
- 元のsource/corrections identity、handoff/manifest/raw correction/declared artifactの
  package相対パス・SHA-256・欠落ファイルの明示。保持sourceが必要な下流入力も検証対象。
- appliedの場合は成功確定記録と結果PDFの相対パス・SHA-256。
  今後のattemptには`preparing/running/succeeded/failed/interrupted`を永続化し、
  再起動後に未完了を成功として列挙しない。
- ページ順序・source page index・画像寸法・PDF MediaBox/CropBox/rotation・
  座標変換、元PDFのdigest。UIは1-based表示、consumerの内部indexは既存契約を維持。

将来のSaveはsnapshot確定と現在stateの更新を一貫して行う必要がある。
失敗途中のcheckpointを一覧へ公開しない。applyは確定したcheckpointから実行し、
競合Save/Applyが別の内容を消費しないようlockとidentity照合を用いる。

旧schemaの読み取りは維持する。現在の保存JSONは「現在の保存状態」として明示snapshot化可能。
旧attemptは完全性とcorrections identityを検証し、元identityを保存したまま新checkpointへ
importする。過去成功の証明がないattemptは「成功apply済み」と表示しない。
`/results/...` の再配置は指定された保持job root内の固定prefix対応とdigest照合で行い、
basename探索や任意パス読み込みで不足ファイルを補わない。復元不能な保存履歴は表示しない。

再開は必ず新packageへ行い、元のstate/correction/attempt/成功PDFを上書きしない。
新packageのstateを元の`current`としてコピーせず、選択checkpointから復元した
`recorded/not_applied`を初期状態にし、新applyの成功後に新しい`current`へ遷移させる。

### 入力PDFと番号の差し替え

**選択checkpointと、入力PDFの背景の生成元は別のidentity**として保持する。
たとえばattempt 1のPDFに書き込んだ入力から、attempt 12の修正状態を選択してよい。
checkpoint選択だけで背景の出所を決めない。

新sessionのprovenanceには、選択checkpoint ID/digest、入力PDF digest、背景の
生成結果ID/digest、検証したページ対応/座標変換、継承後のcorrections identity、
新attempt/最終PDF digestを記録する。

受入候補は検証済み背景・独立注釈を持つPDF。ページ数/順序/サイズ/回転/切り抜き、
画像オブジェクトと配置、背景contentの不変性を確認する。
documentのバイト一致のみには依存しない。
判別不能なrewrite、本文への追記、画像変更、共有画像xref、未知の注釈/フォーム構造、
出力時に注釈の表示が保てない構造は理由を示して拒否する。
PoCのguardは構造が限定されたfixture用であり、任意PDFの検証器として公開しない。

保持済み認識・幾何をauthoritative applyで再計算し、保持したclean source画像から
新しい番号付き背景を生成する。入力PDFのページ画像だけを差し替えて注釈を残す。
PyMuPDFの`replace_image`はdocument全体への置換なので共有xrefを許可しない。
生成後に背景全体が期待する新出力と一致すること、注釈オブジェクト/外観/位置と
物理寸法を検証してから成果物を公開する。失敗時の部分出力を成功結果へ登録しない。

### GUIと実装の積み上げ

以前のjob → checkpoint一覧（保存/成功/検証不能を区別）→ PDFアップロード →
背景対応と整合性結果 → 新packageでレビュー → Save/Apply → 表示/ダウンロード。
HTTP APIへホストの任意パスを渡せる設計にしない。既知のjob registry、package内ID、
サイズ制限付きuploadを使い、symlink・path traversal・不完全入力を拒否する。

まず1本のFeature PRを基本とし、(1) checkpoint/旧履歴import、(2)入力照合/PDF交換、
(3)GUI/ガイド、(4)focused/E2E受入をレビュー可能なcommitとして積む。
現時点でサブIssueや工程ごとのPRを増やさない。
焼き込みPDFの一般復元や旧誤寸法の自動正規化は未解決であり、対応が必要なら
独立した技術課題として判断する。親Issueの条件を暗黙に緩和しない。

## 再現と検証

PoC: [`tools/issue441/phase0_probe.py`](../../tools/issue441/phase0_probe.py)。
今回実行したコードのSHA-256は
`ac2c5d0b5d501caacd0e5f923cbf97c5814be7844d9b762a029f6950cfd08f51`。
tested targetは上記base commitにこのPoCを追加したdiffで、製品sourceは未変更。
実データは外部の保持物であり、リポジトリには追加しない。
通常のpipeline検証コンテナ（immutable image
`sha256:5311cf22ab0198c3384ada62101f195b0bacf6d2079574167a0edb3f66854005`）、
PyMuPDF 1.26.4、manager checkoutを`/workspace`にmountした環境で実行。
PoCはUID/GID `1000:1001`。auditだけは旧stateファイルの権限によりcontainer rootで
読み取り、stdoutをホスト側の利用者所有ログへ保存した。

以下の作業ディレクトリはホストの `.worktrees/issue441`。

```bash
docker exec --user 1000:1001 \
  -w /workspace/.worktrees/issue441 \
  -e PYTHONPATH=/workspace/.worktrees/issue441 \
  pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python \
  tools/issue441/phase0_probe.py \
  --output logs/issue441/phase0/probe-02 \
  --source /workspace/temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205
```

出力先は存在しないディレクトリを指定する。監査は同じ呼び出しの`--user`を外し、
`--output ...`を`--audit-only`へ置換する。これは既存ファイルの読取専用処理。

| 検証 | 今回の状態 / 証拠 |
| --- | --- |
| 現行状態/適用/出力契約 | Passed: 同じdocker execのinterpreterで `-m pytest tests/test_review_correction_state.py tests/test_review_correction_application.py tests/test_corrected_final_output.py -q`。34 passed、exit 0。製品sourceはbaseから変更なし |
| 注釈保持のsynthetic PoC | Passed: 重なる/離れたInk注釈の外観・座標・内容を保持。全背景描画が新出力と一致。`logs/issue441/phase0/probe-02/summary.json` |
| 拒否fixture 8種 | Passed: 焼き込み重なり/非重なり、回転、crop、寸法、ページ数、別内容、native本文追記。出力未公開、入力digest不変 |
| 15ページPoC | Passed: attempt 1由来背景に独立注釈を追加し、attempt 12の背景へ交換。全15ページの背景一致・注釈保持・生成済みPDF寸法保持・元PDF digest不変。ただし旧PDFの誤物理寸法を修正する試験ではない |
| 旧履歴audit | Passed: 12件のraw corrections identity照合。`logs/issue441/phase0/audit-01.json`。source identity不一致と寸法不整合も記録。再開成功を意味しない |
| 静的確認 | Passed: `ruff check tools/issue441/phase0_probe.py`、`git diff --check` |
| 初回環境probe | Blocked後解消: hostにfitzがなく、既存共有コンテナは停止中。コンテナ起動後に上記を実行。旧stateのhost読取はPermission deniedで、auditをcontainer rootへ切替 |
| 新checkpoint復元/編集/再apply・MMR/movement後続番号 | Not run: Phase 1未実装。今回のPoCは保存PDFの背景交換とraw履歴照合のみ |
| ブラウザE2E/GUI/download | Not run: 新GUI未実装。Phase 1で2つ以上のcheckpoint、再起動、競合、不完全入力、stale/failed、過去成果物保持も検証する |
| GPU smoke / Full68推論 / test-fast | Not run: Phase 0の独立PoCと設計のみ。製品経路・検出器・モデル・閾値を変更していない。保持済み結果の下流検証を実施 |

新製品機能の動作確認や親Issueの受入は残っている。今回のPoCは焼き込み入力の一般対応、
任意PDFの安全検証、旧寸法の補正、再開GUIの成立を証明しない。
