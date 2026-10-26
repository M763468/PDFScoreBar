# Issue #441 / PR #445: 通常レビュー後の3件の修正

対象は `451b42099d222847620e1584f0412f315bada443` に対する追加レビュー。
3件とも明確な変更要求として分類し、修正前のfixtureで再現した後に修正した。

## 指摘と保証する動作

| 指摘 | 修正と回帰テスト |
| --- | --- |
| [P1: nullのsource_referenceで保存できない](https://github.com/M763468/PDFScoreBar/pull/445#discussion_r4378780191) | `CheckpointStore._source_context()`は明示nullを元PDF由来の情報なしとして扱う。修正保存・checkpoint列挙/復元・通常Applyは継続できる。検証済みPDF provenanceがないため、書き込み済みPDFからの再開だけは引き続き拒否する |
| [P2: 3回目の再開で既存background.pdfと衝突](https://github.com/M763468/PDFScoreBar/pull/445#discussion_r4378780209) | checkpointからmaterializeした**新規staging内だけ**の旧background.pdfを除き、今回uploadしたPDFから作り直す。親session・保存checkpoint・過去の成功PDFは変更しない。製品のApply/番号生成/所有照合を通して4回目まで再開し、注釈累積と番号非重複、親成果物hash不変を検証 |
| [P2: 番号のないページでfont照合が失敗](https://github.com/M763468/PDFScoreBar/pull/445#discussion_r4378780221) | 所有番号streamがあるページだけで番号fontを要求する。番号なしページもcontent順序・全背景描画・画像・ページ幾何・注釈保持の検証は継続。番号あり/なしの混在PDFで注釈追加・xref再配置を受け入れ、番号なしページへの不明なcontent追加は拒否 |

回帰テストは [history](../../tests/test_review_correction_history.py) の
`test_null_source_reference_preserves_correction_save_and_apply`、
[roundtrip](../../tests/test_issue441_mobilesheets_roundtrip.py) の
`test_return_with_unnumbered_page_preserves_annotations_and_rejects_background_change` と
`test_second_resume_uses_product_result_and_selected_session_checkpoint`。
nullケースと反復ケースの下流engineはfixtureへ置換し、実際の履歴・状態・PDF生成/照合を使う。
新たなGPU実楽譜試験やMobileSheets実機試験を行ったとはしていない。

## 今回の検証

対象は上記base commitと、実装3ファイル・テスト2ファイルの差分。
`logs/issue441/pr445-additional-review/tested-code.patch` のSHA-256:
`3846a7f59141413ca0133fb206b3fcbd051d74d39b2b973a0c1a986df5455d97`。
作業ディレクトリはmanager checkoutの `.worktrees/issue441`、
Pythonはmanagerの `.venv_pdf/bin/python`（host Python 3.10、PyMuPDF 1.26.7）。
各ログは同じ `logs/issue441/pr445-additional-review/` 以下。GitHub ActionsはPRの最新headで別途確認する。

| Check | 今回の状態 | 結果・ログ |
| --- | --- | --- |
| 修正前の3回帰ケース | Failed（再現成功） | 3 failed、`reproduction.log`。null参照・既存file・番号なしfontの各例外を確認 |
| 初回の関連pytest | Blocked（部分実行） | sandboxのsocket作成禁止でHTTPケースが未実行。62 passed、3 failed/20 errorsはいずれも環境制限。`focused.log` |
| 同じ関連pytestをsandbox外で再実行 | Passed | 85 passed、exit 0、`focused-unsandboxed.log` |
| maintained fast | Passed | 122 passed、exit 0、`fast.log` |
| release/distribution | Passed | 67 passed、exit 0、`distribution.log` |
| テスト内の変数抽出後のnullケース | Passed | 1 passed、exit 0、`null-final.log`。他ケース・製品コードは85件実行後に変更なし |
| surface | Passed | exit 0、`surface.log` |
| 初回lint | Failed | 新テストの書式1箇所、`lint.log`。変数を抽出して解消 |
| 最終lint | Passed | exit 0、1143 files formatted、`lint-final.log` |
| GPU/Full68/15ページbrowser再実行/実機往復 | Not run | provenance・staging・番号なしページのartifact契約修正。数値認識・モデル・閾値・UIは変更しておらず、fixtureと関連回帰で対象境界を直接検証 |

```bash
# cwd: <manager>/.worktrees/issue441
issue441_python=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
"$issue441_python" -m pytest \
  tests/test_review_correction_history.py tests/test_issue441_mobilesheets_roundtrip.py \
  tests/test_issue441_annotated_layer.py tests/test_review_correction_application.py \
  tests/test_review_correction_server.py tests/test_review_correction_state.py -q --disable-warnings
mapfile -t issue441_fast_tests < <(sed -n 's/^FAST_TESTS ?= //p' Makefile | tr ' ' '\n')
"$issue441_python" -m pytest "${issue441_fast_tests[@]}" -q --disable-warnings
"$issue441_python" -m pytest tests/test_distribution_surface.py tests/test_release_candidate.py -q --disable-warnings
"$issue441_python" -m pytest tests/test_review_correction_history.py::test_null_source_reference_preserves_correction_save_and_apply -q
python3 tools/check_repository_surface.py
make lint
git diff --check
```

Historical evidence: [451b4209での15ページ・11回実GPU適用と228/122/101/67件](ISSUE441_FINAL_REVIEW.md)、
[fff311f2での実MobileSheets往復1例](ISSUE441_MOBILESHEETS_ROUNDTRIP.md)は前段の記録。
今回再実行した結果と混同しない。今回の反復3/4回目もsynthetic fixtureで、実機再輸出ではない。

## 対応範囲とレビュー状態

[2026-10-26のオーナー判断](https://github.com/M763468/PDFScoreBar/pull/445#issuecomment-6419204871)で、
手動配置UI・物理印刷固有設定・MobileSheets全バージョン/設定の網羅は必須要件から外れた。
検証済みannotation-only方式に限定し、PDF内の番号範囲・原譜/注釈保持・未知入力の安全拒否を維持する。
範囲のowner判断待ちは解消し、PRは既にDraft解除済み。
この判断はマージ承認ではなく、今回の3件は上記コードと回帰テストで対応した。
最新差分のレビューとCIを確認してマージ可否を判断する。マージ・Issue完了は行わない。
