# PR #445 レビュー対応: 番号サイズ・段への距離・安全な確定処理

2026-10-25。[レビュー](https://github.com/M763468/PDFScoreBar/pull/445#issuecomment-6395501007)
およびユーザーの追加要望「サイズを統一」「段へもう少し近く」に対応した。
作業ブランチとDraft PRは継続し、新しいPRは作らない。

## 今回の結果

**番号は全段・全ページで9ptへ統一。段先頭に近い安全な位置を優先する。**
段ごとのstaff高さで文字サイズを変えたり、置けない段だけ小さくしたりしない。

| 実出力 | 番号数 | 実PDFの文字サイズ | 旧配置より近い / 遠い | 距離中央値 before → after |
| --- | --- | --- | --- | --- |
| 保存状態1 | 160 | すべて9pt | 160 / 0 | 4.582 → 0.993 pt |
| 保存状態12 | 160 | すべて9pt | 160 / 0 | 4.588 → 0.993 pt |
| MMR追加修正後 | 160 | すべて9pt | 160 / 0 | 4.588 → 0.993 pt |
| 取消後 | 160 | すべて9pt | 160 / 0 | 4.588 → 0.993 pt |

各出力とも全15ページを含む。全729注釈、元画像bytes、MediaBox/CropBox、既存の濃い画素を保持。
番号列は保存済みの下流結果を再利用し、今回の変更でMMR/認識の数値計算をやり直していない。
本文に記した近接距離は、段のtop staffの左上点から数字の字形bboxまでの最短距離。
線や音符への主観的な距離を自動的に合格とした指標ではない。
同じglyph計測方法を旧配置と新配置に用い、160箇所を除外なしで比較した。

[機械可読スナップショット](issue441/evidence/typography_revision_snapshot.json)と
[11件のテスト標準出力](issue441/evidence/typography-focused-tests.txt)をGitHubから確認できる。
旧8〜10ptの記録・5テストの出力は過去証拠として残す。

## サイズと距離の変更方法

[`crop_label_layer.py`](../../tools/issue441/crop_label_layer.py)の既定値を文書全体で9ptにした。
将来利用者がサイズを変える場合も文書全体に1つの値を適用する設計とし、段ごとの縮小fallbackはない。
同じサイズで安全な空きがなければ拒否する。

以前はfontのascender/descenderを含む行高bboxを基準に置いていた。
今回は[Font.glyph_bbox公式仕様](https://github.com/pymupdf/pymupdf/blob/main/docs/font.rst)
に基づき、各数字の字形bboxとadvanceから、挿入baselineに対する実際の字形範囲を計算する。
fontの上下余白を不要な離隔として扱わない。

候補は段先頭への距離で昇順に評価し、数字を段の上か左へ置く。
余白はstaff高さで正規化した値を0.75〜1.5ptへ制限する。
CropBox内、既存annotation bbox・他の新番号と非重複、144DPIで近白色領域という条件は維持。
白塗りや注釈領域の無視で近づけてはいない。

sidecarに字形bbox・段先頭・距離を記録し、実PDFを再読込してtext spanがすべて9ptであることも
4出力で別途確認した。代表page 3/10を詳細目視、15ページを一覧で確認した。
実印刷の受入と、更新した位置の利用者最終確認は残る。

## 保存後失敗と公開の安全性（レビュー項目2）

以前の`doc.save(output)`後の`assert`検証を廃止し、次の順序にした。

1. 最終出力と同じ親directory内の一時directoryへPDFを保存。
2. 再openし、ページ幾何・注釈・既存画素・番号列・元画像bytesを**明示的な例外**で検証。
3. sidecarを一時領域へ保存し、再読込した内容とPDF digestの整合を検証。
4. 上書き不可のhard linkで検証済みsidecarを公開し、最後に検証済みPDFをcommit pointとして公開。
5. 失敗時は一時成果物と自分が作ったsidecarを除去。他のwriterの出力や過去成功結果を削除しない。

二つのファイルを同時にrenameする実装ではない。
成功結果の入口は最後に公開されるPDFで、未検証PDFを最終pathへ出さない設計。
プロセス強制終了が2つのlinkの間に起きるとsidecarだけが残る可能性があるが、成功結果ではなく、
再試行時も上書きせず拒否する。製品stateへの成功登録もPDF/sidecarの検証・確定後に行う必要がある。
その製品呼出しへの統合はcheckpoint/state統合時の残作業であり、このcommitだけで完了とはしない。

focused testは以下の11件。

- 旧番号だけの除去・更新、CropBox保持。
- 空き領域なし、不可視の白い注釈、改変PDF、改変stream digestの拒否。
- staff高さが異なっても同じ文字サイズ。実PDF spanでも検査。
- **save後の検証失敗**で最終PDF/sidecarが存在せず、原本と過去成功結果が不変。
- PDF公開処理失敗時のsidecar rollback。
- 競合writerのファイルを上書き・削除しない。
- 中断後のsidecar単独状態を成功として再利用しない。
- **`python -O`でも**保存後に幾何を破損させたcandidateを明示例外で拒否する。

## 非公開の目視比較（レビュー項目4）

新しい比較用成果物はworktree内の次の場所に保持。

```text
logs/issue441/pr445-refinement/typography-01/run-01/
  attempt_0012/annotated_numbered_uniform9.pdf
  attempt_0012/annotated_numbered_edited_uniform9.pdf
  attempt_0012/annotated_numbered_undone_uniform9.pdf
  preview/index.html
  preview/all_15_pages.png
```

`preview/index.html`は各ページについて、書き込み済み原本・旧8〜10pt配置・新9pt配置・
MMR修正後・取消後の5列を並べる。page 3/10へのリンクと全15ページの一覧があり、画像を拡大できる。
元のPDFや書き込み画像を公開PRへ添付していない。
GitHubには手法・コード・集計・テスト出力だけを掲載する。

## レビューの分類と対応状況

レビューは会話コメント1件、inline threadは0件。変更要求として扱い、質問やnitはなかった。
収集記録は`logs/issue441/pr445-refinement/review-20261025/artifacts/pr445/`。

| 指摘 | 今回の対応 / 残り |
| --- | --- |
| ユーザー: サイズ統一 | 対応済み。全段9pt、段ごとのfallbackなし、4実出力とテストで確認 |
| ユーザー: 段へ近づける | 対応済み。各160箇所がすべて近接、遠くなった箇所0。代表ページと一覧を目視 |
| R1: MobileSheets往復 | 未受入。番号付きPDFへの追記・再exportの実サンプル/実機操作はNot run。推定で成功にしない |
| R2: 不完全PDF公開 / assert | ヘルパーを修正済み。保存後失敗・競合・`-O`を検証。製品経路での利用は統合時に確認 |
| R3: checkpoint永続化・列挙・選択・成功扱い | Open。2状態の復元実験と製品機能は区別。次の製品統合範囲を下記に固定 |
| R4: 可読性・プレビュー | サイズ/距離を改善し、非公開5列比較と15ページ一覧を作成。実印刷/ユーザーの新版確認は残る |
| R5: 適用範囲・全タイプ/E2E | 既知source・独立注釈・同じgeometry・所有sidecarが現境界。旧ラスタ/flatten/未知rewriteを自動受入せず、全修正タイプとbrowser E2EはNot run |

次は、sourceとraw correctionの不変snapshot、任意checkpointの列挙/選択、新sessionへの復元、
saved/applied/current/stale、競合・中断・失敗履歴の永続化を製品側へ統合する。
過去attemptのPDF存在だけで成功apply済みと表示せず、成功記録の確証と復元可能性を別に扱う。
今回直した確定処理が成功してからstateに結果を登録し、GUI、MobileSheets往復、browser E2Eへ進む。
Draftのまま継続し、Ready/mergeや#441の受入完了へは移行しない。

## 今回の検証と再現

tested commit: `20fe8e1e4578edb87722ef51ce2bdf5002f942b6`。
image: `sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`。
managerは`/workspace:ro`、Issueログのみ別の書込mount、UID/GID 1000:1001。
今回変更したのはPDFの文字と確定処理で、番号列は`resume-02`の保持済み結果を再利用した。
MMR OCR/GPU推論を再実行したものではない。

```bash
docker run --rm --user 1000:1001 \
  -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace:ro \
  -v /home/masaki_muramatsu/ws_PDFScoreBar/.worktrees/issue441/logs/issue441:/workspace/.worktrees/issue441/logs/issue441 \
  -w /workspace/.worktrees/issue441 \
  -e PYTHONPATH=/workspace/.worktrees/issue441 -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /opt/venv_pipeline/bin/python \
  sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a \
  tools/issue441/refine_annotated_layout.py \
  --retained-run logs/issue441/annotated-resume/resume-02 \
  --pdf '/workspace/temp/issue441/exported_by_mobilesheets/Nielsen-Sym4 Vn2 書き込み.pdf' \
  --output logs/issue441/pr445-refinement/typography-01/run-01
```

再実行は未作成の出力先を指定。
同じimage・checkout・PYTHONPATHで`python -m unittest discover -s tests -p test_issue441_annotated_layer.py -v`
を実行した。証拠は`unit-02.log`、`run-01.log`、`run-01/summary.json`、`font-check.log`、
`run-01/font_check.json`、`validated-code.patch`。

| Check | 今回の状態 |
| --- | --- |
| 新しい配置・4実PDF・729注釈保持 | Passed、exit 0。各160番号で9pt、全て近接 |
| 実PDF text spanの再検査 | Passed、4出力すべて160番号・9pt |
| focused test | Passed、11件、exit 0。`-O`とsave後失敗を含む |
| 静的確認 | Passed、3 Pythonのruff/format、`git diff --check` |
| 目視 | Passed: p3/p10詳細と15ページ一覧を確認。新版の最終ユーザー受入は未実施 |
| 新しい下流MMR・上流推論 / Full68 / test-fast | Not run: 番号計算・認識経路は未変更で保持済み番号列を再利用 |
| 製品checkpoint/GUI・外部アプリ往復・実印刷 | Not run: 上記のOpen項目。今回の結果と区別 |
