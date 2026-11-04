# Issue #441 / PR #445: 通常レビュー後の3件の修正

## develop統合後の再検証（2026-10-27）

作業head `c67a92958a7b81be51466370349156ee1ce7d61a` に、develop
`a25b06baed50e303fefcda52d0ee9f0651f2ad05`（PR #451）を通常mergeした。
競合は `docs/MINIMAL_MAINLINE_SURFACE.md` の配布件数1か所のみ。
両ブランチのmanifest選定を残し、再計算した **114 tracked files / src 87 files** へ解消した。
自動統合されたruntime fingerprint対象にもIssue441のlegacy/number layerを保持し、
両方の元manifestのruntime entriesが欠けていないことを確認した。
detector・launcher・追加モデル選択テストは取り込み元developと同一で、独自改変はない。

検証対象は上記headと、統合差分
`logs/issue441/develop-integration/integrated.patch`（SHA-256
`136cb379a94cf33471c59082004fa3491a124f957af7c61cdd09efcb79f89e6d`）。
以下は今回再実行した結果で、下のc67a9295以前の履歴と区別する。

| Check | 今回の状態 | 結果・ログ（`logs/issue441/develop-integration/`以下） |
| --- | --- | --- |
| Issue441回帰・runtime/配布・develop追加テスト | Blocked（hostの1件） | pytest表示は276 passed / 1 failed、exit 1。モデル選択1件でultralytics未導入。`regression.log`。残りの276件は成功 |
| モデル選択一式を既存検証containerで実行 | Passed | 31 passed、exit 0、`model-selection-container.log`。上記の実行不能1件も含む。host結果との重複30件を含み、合計277件の対象ケースを両環境でカバー |
| maintained fast + engine追加2モジュール | Passed | 145 passed、exit 0、`fast-engine.log`。CI engine gate全7モジュール・101件もこの集合内で実行 |
| surface | Passed | 97 runtime patterns、exit 0、`surface.log` |
| lint/format | Passed | 1147 files、exit 0、`lint.log` |
| Makefile・shell・diff | Passed | `make check-makefile`（`makefile.log`）、`bash -n scripts/docker_runtime_validation.sh`、`git diff --cached --check`、各exit 0 |
| GPU推論・Full68・15ページbrowser・実機往復 | Not run | 手動競合解消は配布件数だけ。developの認識/runtime変更をそのまま取り込み、モデル・閾値・認識ロジックの追加変更はない。既存の実楽譜/GPU証拠は今回の再実行扱いにしない |

host cwdは `.worktrees/issue441`、Pythonはmanagerの `.venv_pdf/bin/python`。
HTTPテストはsocketを利用できるsandbox外で実行した。
モデル選択の再実行先は既存 `pdfscore_pipeline_pytest_dev`、image
`sha256:5311cf22ab0198c3384ada62101f195b0bacf6d2079574167a0edb3f66854005`。
managerの実mount `/workspace` と作業treeの可視性を確認し、UID/GID 1000:1001、
cwd/PYTHONPATH `/workspace/.worktrees/issue441`、`PYTHONDONTWRITEBYTECODE=1`、
`/opt/venv_pipeline/bin/python`（pytest 8.4.2、ultralytics 8.3.239）を使用した。
環境・依存関係を変更せず、既存containerも停止/削除していない。

```bash
issue441_python=/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python
"$issue441_python" -m pytest \
  tests/test_issue441_mobilesheets_roundtrip.py tests/test_review_correction_history.py \
  tests/test_review_correction_application.py tests/test_review_correction_server.py \
  tests/test_review_correction_state.py tests/test_issue441_annotated_layer.py \
  tests/test_distribution_surface.py tests/test_docker_runtime_contract.py \
  tests/test_manual_correction_handoff.py tests/test_issue396_review_ui.py \
  tests/test_review_correction_client.py tests/test_numbering_preview.py \
  tests/test_reviewed_movement_apply.py tests/test_release_candidate.py \
  tests/test_experiment_model_selection.py tests/test_issue329_model_artifact_contract.py \
  tests/test_cnn_scoring_model_path.py -q --disable-warnings
docker exec -u 1000:1001 -w /workspace/.worktrees/issue441 \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/workspace/.worktrees/issue441 \
  pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python -m pytest \
  tests/test_experiment_model_selection.py -q --disable-warnings
mapfile -t issue441_fast_tests < <(sed -n 's/^FAST_TESTS ?= //p' Makefile | tr ' ' '\n')
"$issue441_python" -m pytest "${issue441_fast_tests[@]}" \
  tests/test_corrected_final_output.py tests/test_final_pdf_page_size.py -q --disable-warnings
```

merge commitの最終SHA・GitHub Actionsと競合解消状態はPRの最新記録へ追記する。
developへのマージ・Issue完了は実行しない。

## c67a9295での追加レビュー対応の記録

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
