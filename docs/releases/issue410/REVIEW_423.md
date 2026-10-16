# PR #423: レビュー修正とdevelop統合確認

2026-10-16。[PR #423](https://github.com/M763468/PDFScoreBar/pull/423)の
`4386bb61`に対する2件のinline指摘とowner reviewの同内容を、明確な修正要求として対応した。
併せて、別branchから統合された#422と合同のtreeで検証した。

## 修正した契約

- [P1: pinned sourceとtool identity](https://github.com/M763468/PDFScoreBar/pull/423#discussion_r4295448843)。
  実行中のgenerator/checkerを、固定source commitの対応するGit blobsとbyte比較する。
  不一致やsource側toolの欠落はcreate/checkの前に拒否し、provenance hashは固定blobsから取得する。
  別checkoutのHEAD・配布ファイルが異なってもtool bytesが同一なら同じ候補を再現できる。
  generator/checkerそれぞれについて、未commitのtool変更と、別checkoutでcommitされたtool変更の
  create/check拒否を検証した。配布sourceの未commit変更を取り込まない既存契約も維持する。
- [P2: 複数ページのmanual movement保存先](https://github.com/M763468/PDFScoreBar/pull/423#discussion_r4295448854)。
  全ページのmovement review出力を1つの共有pathに限定する。handoff検証とapply consumerの双方で
  異なるpathを拒否する。evidenceの有無、明示的`correction_outputs`とdirectory指定の両方を検証した。
  他の補正はページ別出力を使ってもよい。共有movement出力を使う2ページで、保存・別ページの追加・
  一方の削除・保存済みbytesの再検証まで通し、他ページのresetが保持されることを確認した。
  既存の候補付きexporterのエラーメッセージ契約も維持する。

## developとの整合性

| 項目 | identity / 結果 |
| --- | --- |
| 統合したdevelop | `6ef2ff3b21a3b244f4d2a0bd8908a30fc3399fcb`（PR #422 merge） |
| topicへの統合commit | `5caa4bfc`。競合なし。develop/main自体へのmergeはしていない |
| 修正・検証source | `47d2135211194f9310cb9bbb82e138a354c8248d` |
| 新manifest | schema 3、SHA-256 `fb8c8f32580c85122110e2d9a2dcad9ac103d0815b64a953b8a6c75450f86fa9` |
| 配布選択 | **107ファイル**、生成provenance込み108ファイル |
| 準備candidate | `aaefd8d75f0fc27d6d227ebfdb889e015738f641` |
| candidate tree | `4ca2729ad9ae38f221e810af755d571cda5bee1a` |
| frozen main parent | `893f17853a6fc73d252a621e8621385e799d5bc6` |

#422の追加2モジュール（`src/common/barline_strokes.py`、`src/pipeline/steps/staff_strokes.py`）を
含め、選択path集合は最新developと一致する。#423のrelease test分類も保持している。
追加2モジュール、`cnn_scoring.py`、`dense_orchestrator.py`の4本はdevelopのblobsとbyte一致し、
config/modelにもdevelopからの差分はない。
従来の105-file候補とそのhashは過去の準備snapshotとして保持し、新たな配布identityを記録した。

## 検証結果

| 検証 | 結果 |
| --- | --- |
| release/distribution、handoff、review client/server/application/state、movement apply/review/export、#422 staff-stroke対象tests | **166 PASS**、`targeted-tests.log` |
| `make test-fast PYTHON=.../.venv_pdf/bin/python` | **114 PASS**、`test-fast.log` |
| repository surface | PASS、95 runtime patterns、`surface.log` |
| scoped Ruff check/format、`git diff --check` | PASS |
| 固定source/mainから独立Git候補を2回生成 | PASS、同一candidate commit/report/provenance |
| distribution dependency/reference/content checker | PASS、`distribution-check.log` |
| develop祖先・配布path・#422 source/hash・config/model・candidate tree検査 | PASS、`integration-verification.json` |
| 配布対象外の旧mainファイル | 874ファイルがcandidate tracked treeに残らないことを確認 |

再現コマンド（新しい出力directoryを使う）:

```bash
python3 tools/release_candidate.py create /tmp/pdfscorebar-issue410-review-repeat \
  --source-commit 47d2135211194f9310cb9bbb82e138a354c8248d \
  --main-commit 893f17853a6fc73d252a621e8621385e799d5bc6 \
  --branch release/issue410-review-repeat
python3 tools/materialize_distribution.py check \
  /tmp/pdfscorebar-issue410-review-repeat --git-checkout
```

生成tool bytesが異なるcheckoutでこのコマンドを実行した場合は拒否する。
再現時は固定sourceのtoolを使う。本記録を追加した後の変更は文書のみであり、
GitHub CIはpush後のPR HEADに対して別途確認する。

## 証拠・失敗・未実施範囲

ローカル保持rootは`logs/issue410/pr-review/20261016/`。
スキルで取得した本文/reviews/全inlineコメント/差分は`artifacts/pr423/`、
候補2回の記録は`candidate-{a,b}.{json,log}`、合同treeの検証器は`verify-integration.py`に保持した。
元の利用者補正・PDF・データ・モデルは変更していない。

最初の対象suiteは165 PASS / 1 FAILで、handoffが早期に拒否するようになった結果、
既存exporterの期待するエラー文面に一致しなかった。従来の文面を維持して166 PASSを確認した。
最初の統合検証器もmanifestのtest分類をtop-levelとして参照して停止したが、実際の
`test_module_groups`を読むよう修正し全検査を完了した。両方の初回ログを別名で保持した。

新しいFull68推論、GPU smoke、Docker build、実browser/PDFの数値再評価は今回は行っていない。
最新developとの差分はrelease tooling、handoff/保存・消費契約、既存UI改善と文書であり、
#422の数値実装・config/modelを変更していない。合同treeでは該当unit/consumerテストと
独立候補の配布検査を実施し、#422の受理済み数値検証はそのsourceに紐づけたまま保持する。

今回の候補はtopic sourceからのPhase A準備で、`release_accepted=false`。
#423を受理したthen-current developからの最終freeze、候補自身のDocker/GPU/PDF/GUI/semantic gates、
既知残差・正式な手動受入とmain昇格の明示承認はPhase Bに残る。
