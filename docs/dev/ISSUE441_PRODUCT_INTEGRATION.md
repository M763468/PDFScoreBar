# Issue #441 / PR #445: 保存履歴と書き込み済みPDFの再開

保存した修正状態を画面から選び、共有された書き込み済みPDFを取り込んで、元packageとは
独立したセッションで修正・PDF生成を再開できるようにした。既定の番号は文書全体9ptで統一し、
段の近くの安全な空白へ配置する。[前段の配置比較](ISSUE441_PR445_REFINEMENT.md)は履歴として保持する。

## 操作と実装

1. 未保存の編集を保存する。「保存履歴・再開」で名前を付けて履歴を保存することもできる。
2. 一覧から再開する保存時点を選び、書き込み済みPDFを選択する。
3. 「別セッションで再開」で新しいURLを開く。元のpackage・成功結果は継承して上書きしない。
4. 書き込みを表示した楽譜上で修正し、保存・適用する。再読込・サーバー再起動後も同じURLで続けられる。

実装の入口:

- [history.py](../../tools/review_correction/history.py): 内容hash付き不変blobとcheckpoint manifest。
  保存時に4種類の修正、存在しない修正ファイル、楽章境界resolved、表示用証拠、handoff、
  source manifest、番号計算のbase、設定入力、元PDFを固定する。外部の保持済みページ依存は
  hashで照合するため、保持結果一式を持ち運べるアーカイブではない。
- [resume.py](../../tools/review_correction/resume.py): 元PDFとアップロードPDFの背景画像bytes・
  注釈非表示時の全MediaBox描画・ページ順・座標を照合。準備用directoryで全ページを検証してから
  新しいsession directoryを確定する。source画像と書き込み済み表示画像を別に保持する。
- [server.py](../../tools/review_correction/server.py) / [history.js](../../tools/review_correction/history.js):
  checkpoint一覧・保存・PDFアップロード。HTTPからホストの任意パスを指定できない。
  各リクエストのsession IDでpackageを解決し、別タブの操作先を共有変数で切り替えない。
- [application.py](../../tools/review_correction/application.py): 適用開始時のcheckpointをmaterializeし、
  その入力だけで下流を再計算。再開セッションでは既存の画像化PDF生成を使わず、
  [number_layer.py](../../src/pipeline/review/number_layer.py)で書き込み済みPDFへ番号を追加する。
- [state.py](../../tools/review_correction/state.py): 実際に検証・生成できた結果だけを成功として記録。
  running/failed/succeededを永続化し、OSのlockが残っていないrunningはinterruptedと判定する。
  過去の成功結果は後続の失敗でも保持する。PDFとsidecarは取得時にもhashを照合する。

保存と適用の競合はpackage内の非待機process lockで拒否する。別サーバーの適用中も保存できない。
保存や履歴確定が例外で失敗した場合、rawとresolvedの修正を保存前へ戻す。
プロセス強制終了による複数ファイル更新の途中停止までを単一filesystem transactionとはしない。
その場合も楽章境界のstale検査・入力hash・成功記録を通らない結果を成功扱いしない。

番号生成は検証済みsidecarを先に、PDFを最後に非上書きで公開する。保存後の全ページ検査には
`assert`を使わず、Python `-O`でも不正結果を公開しない。空白不足時はエラーとして止める。
手書き数字の推測削除、白塗り、段ごとの縮小は行わない。

## 今回の検証

コードの固定情報は[公開検証スナップショット](issue441/evidence/product_integration_snapshot.json)、
テスト出力は[回帰テスト](issue441/evidence/product-regression-tests.txt)と
[fast tests](issue441/evidence/product-fast-tests.txt)で確認できる。
基点は `1431feb2935008d93c263dcd73b8da95469637a6`。公開JSONに今回の変更ファイルのSHA-256を記録する。

実データはIssueで提供された15ページPDF（SHA-256
`c52167c534ebde75150c7c52c11f7051e864390cfa2103640f631b0644bb89c2`）と
保持job `job-5969eee679e540d282e23fb3ecdfe205` の `attempt_0012`。
元のファイルを変更せず、Issue配下の独立コピーで実行した。

| 確認 | 今回の状態 | 結果・範囲 |
| --- | --- | --- |
| focused・既存修正・UI契約・配布・runtime/handoff | Passed | 188件。履歴破損、symlink、依存変更、保存rollback、別プロセス排他、失敗・中断復旧、4種類の修正保存、session再読込、PDF/sidecar検証を含む |
| 維持されているfast test一覧 | Passed | 122件 |
| 実ブラウザー | Passed | 古い履歴の選択、PDF取り込み、別セッション、画面からのMMR編集・Save/Apply・取消、再読込、元package不変。HTTP/engine mockなし |
| 実データの番号列・注釈・9pt | Passed | baselineは保持結果と一致、編集で番号が変化、取消で全番号列が復帰。3出力とも15ページ・160番号・全9pt・729注釈・CropBox・元の濃い画素を保持 |
| サーバー再起動後の成功PDF取得 | Passed | 同じsession IDでcurrentと成功PDF hashを復元・HTTP取得 |
| 移行中のテスト | Failed・修正後再実行 | import誤記、rollback期待値、fixture形式、イベント契約の不一致。最終188件はPassed。初回ログも保持 |
| 初回HTTPテスト | Blocked後に再実行 | sandbox内でsocket作成不可。許可された外側の実行で回帰テスト完了 |
| 初回ブラウザー起動 | Blocked後に再実行 | headless-shell実体が未配置。イメージ内のChromium実体を明示して完了 |
| ホスト側からの再起動後HTTP照合 | Blocked後に別経路 | localhost接続が到達せず待機。Dockerの同一networkから保存済み出力を照合 |
| Full68・上流detector再推論 | Not run | 認識アルゴリズム・モデル・閾値を変更していない。保持済み認識を再利用 |
| 新しい番号付きPDFのMobileSheets再輸出 | Not run | 実機の再輸出データが未提供。今回の取り込み成功を往復互換性の受入としない |

回帰テストでは途中で見つかった移行テストのimport誤記、rollbackの期待値、fixture形式、
ブラウザーイベントのテスト契約を修正した。初回ログを消さず、最後の実行結果を上表へ記載した。

### 再現コマンドと環境

worktreeは `.worktrees/issue441`。ホストPythonはmanager checkoutの `.venv_pdf/bin/python`。
ローカル証拠rootは `logs/issue441/product-integration/`。公開JSONに採用ログを限定して集計する。
最終コードの実ブラウザー証拠は `browser-03/`。`baseline.pdf`、`edited.pdf`、`undone.pdf`、
各スクリーンショットと `browser-report.json` を非公開で保持する。
[番号列・再起動後HTTP照合コード](../../tools/issue441/verify_product_integration.py)と
[公開allowlist集計コード](../../tools/issue441/export_product_evidence.py)もコミットした。

```bash
/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python -m pytest \
  tests/test_review_correction_history.py tests/test_review_correction_application.py \
  tests/test_review_correction_server.py tests/test_review_correction_state.py \
  tests/test_issue441_annotated_layer.py tests/test_distribution_surface.py \
  tests/test_docker_runtime_contract.py tests/test_manual_correction_handoff.py \
  tests/test_issue396_review_ui.py tests/test_review_correction_client.py \
  tests/test_numbering_preview.py tests/test_reviewed_movement_apply.py -q --disable-warnings
mapfile -t issue441_fast_tests < <(sed -n 's/^FAST_TESTS ?= //p' Makefile | tr ' ' '\n')
/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python -m pytest "${issue441_fast_tests[@]}" -q --disable-warnings
```

実データの一時サーバーはGPUあり、image
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`、
PyMuPDF 1.26.4、UID/GID 1000:1001。runtime resolverで互換性を確認した。
manager checkoutを `/workspace:ro`、Issue441のlogsだけを同じ場所へrwでmountし、
`/workspace/.worktrees/issue441` で実行。
`PYTHONPATH=/workspace/.worktrees/issue441`、`PYTHONDONTWRITEBYTECODE=1`。
実際のMMR OCR providerを確認し、CPUのみへのfallbackがあれば検証を失敗させる。

ブラウザーimageは
`sha256:8771dc4666e7c11440bfc6a0c6b00480e9a15b8891b45f29a52d7d995f8d1492`。
`--network host --user 1000:1001 -v <worktree>:/workspace:ro -v <private-evidence>:/evidence`
と提供PDFのread-only mountを使用。次のコマンドを実行した。

```bash
PLAYWRIGHT_MODULE=/app/node_modules/playwright \
CHROMIUM_PATH=/ms-playwright/chromium-1226/chrome-linux64/chrome \
node tools/review_correction/resume_browser_acceptance.cjs \
  http://127.0.0.1:8441 /private/input.pdf /evidence
```

保存済み出力の照合と公開集計は次のとおり。前者はサーバー停止・再起動後、同一Docker mount/networkで実行した。
後者はhostで実行し、PDF/sidecarと実行コードのhash・ページ/番号/注釈count・文字サイズを再照合した。

```bash
python -m tools.issue441.verify_product_integration \
  --job /workspace/temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205 \
  --report logs/issue441/product-integration/browser-03/browser-report.json \
  --url http://127.0.0.1:8441 \
  --output logs/issue441/product-integration/actual-verification-final.json
/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python -m tools.issue441.export_product_evidence \
  --run-root logs/issue441/product-integration \
  --output-root docs/dev/issue441/evidence \
  --workspace-root /home/masaki_muramatsu/ws_PDFScoreBar
```

## 受入範囲と残件

対応済みは元背景と対応するnative注釈PDFの全ページ・同順・回転0・原点0のMediaBox。
CropBox変更とInk/Circle/Square/Stamp/FreeText/Highlightを扱う。別のPDF構造、リンク、
部分ページ、並べ替え、画像化された書き込み、他アプリで背景を再符号化したPDFは保証しない。
番号付き出力をMobileSheetsで編集・再輸出した場合のレイヤー同定・交換は引き続き未受入。
入力の背景が変わった場合に既存番号らしい数字を推測して消すことはしない。

4種類の修正はcheckpoint保存テストと既存consumerの回帰テストを通した。
今回の15ページ・実ブラウザーE2EはMMRの追加と取消。小節構築・小節線・楽章境界の全操作を
書き込み済み15ページ上で組み合わせた実機受入ではない。
空白不足の手動配置UIと、MSFを直接読み込むUIも未実装。PRはDraftを継続し、mergeしない。
非公開PDF/MSF・楽譜画像・注釈本文・raw correction・画面スクリーンショットはGitHubへ上げず、
公開資料にはコード・テスト・hash・集計結果だけを含める。
