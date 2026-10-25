# Issue #441 / PR #445: MobileSheetsで追記・再輸出した番号付きPDFの再開

利用者が番号付きbaselineをMobileSheetsへ取り込み、「test」を書き込んで再輸出した
15ページPDFを使い、旧番号だけを取り除いて修正を再開する経路を製品へ追加した。
**入力の全820注釈を保持し、旧番号160個を交換して全段9ptで再生成できた。**
今回の実データはannotation-onlyの往復1例であり、MobileSheetsの全バージョン・全出力設定の
互換性を意味しない。OS/アプリのバージョンと書出し設定は不明、PDFのProducer/Creatorも空だった。

## 観測結果と固定した受入条件

基点commitは `705a4a288b560f1da531f2394dcacfc2c96491f1`。今回の実行コードhashと
結果は[公開スナップショット](issue441/evidence/mobilesheets_roundtrip_snapshot.json)に固定した。
元の共有ファイル、保持job、過去の生成結果は変更していない。

| 項目 | 取り込み前のbaseline | 提供された再輸出PDF |
| --- | --- | --- |
| SHA-256 | `afcd28ea19e7f3b3d96d5c5c04d3a8095bef37cec42da4aa27db843ea230e59a` | `77018813d3c7e9d16aa51eef234c92af7069bb797fdeb0e043324a3791f83574` |
| ページ / 番号 | 15 / 160 | 15 / 160 |
| 注釈 | 729 | 820（Ink 795、Circle 10、Stamp 15） |
| xref | sidecarの元の参照番号 | 所有番号の160参照すべてが変更 |
| 各ページのcontent streamの順序・展開後bytes | 基準 | 全15ページで一致 |
| 所有番号のstream hash・識別マーカー | 基準 | 全160個で一致 |
| 全MediaBoxの注釈を除く144 DPI描画 | 基準 | 全15ページで完全一致 |

注釈増分91件は1ページ目。手書きの「test」を目視で確認した。
テキスト検索で得られる文字列ではないため、抽出テキストに「test」があることを受入条件にせず、
入力注釈の属性・座標・vertices・appearance描画の保持と、非公開画像の目視で確認した。

受入条件は新しい実験のplan.jsonに実行前に固定した:
15ページ、旧番号160個の照合・除去、入力の全820注釈保持、番号160個・全9pt、CropBox保持、
非所有の元の濃い画素（144 DPIでRGBいずれかが250未満）保持、二重番号なし、
baseline番号列の保持結果との一致、MMR編集で番号が変わること、取消で全番号列が戻ること、
再起動後の同一成功PDFと3試行の履歴保持。保持済み認識は元jobのattempt_0012を使用した。

## 製品への組み込み

[番号レイヤー](../../src/pipeline/review/number_layer.py)の `strip_returned_layer()` と
[再開処理](../../tools/review_correction/resume.py)の `prepare_pdf()` を追加した。

1. 元背景だけのnative注釈PDFは従来の検証を続ける。
2. 番号付きPDFの場合、生成元packageとその再開セッション内の**成功記録で裏付けられた**
   PDF/sidecarを探す。両方のhashを成功記録と照合する。HTTPから候補の任意パスは渡せない。
3. 元xref値で削除対象を決めず、保持済みsidecarのcontent順序に対応する新xrefを調べる。
   完全なcontent列・所有streamのhash/marker・番号フォントの辞書・背景画像bytes・注釈を除く144 DPIの全ページ描画を照合する。
   番号フォントは現行出力のsimple Type1辞書の4keyに限定し、見かけが同じでも辞書の追加・変更は拒否する。
4. 照合できた所有番号の参照だけをページcontentから外す。注釈には触れない。
   除去後の背景描画が保持された元PDFへ完全に戻ることを確認する。
5. 一時PDFに保存し、再open後も全注釈の属性/appearance・CropBox・全描画が一致してから
   正規化した背景を確定する。途中失敗では公開セッションを残さない。
6. 元の再輸出bytesを `resume/input.pdf`、旧番号だけ除いた背景を `resume/background.pdf` として
   別々に保持する。両hashと所有確認の証拠をhandoffに記録し、state identityにも両方を含める。
7. 画面には旧番号を除いた書き込み済み背景を表示し、適用時はその背景へ新番号を追加する。
   生の入力hash・除去個数も成功結果へ記録する。新出力の公開・成功登録・取得時hash検査は従来どおり。

PDF全体のhash一致を緩めて入力全体を信用したわけではない。直接のsidecar再適用に対する
従来の厳密hash検査も変更していない。**実際の成功記録との対応を証明できたannotation-onlyの
再輸出だけ**に、独立した正規化経路を加えた。
markerが付いているだけのPDF、stream変更、font resource変更（未使用keyの追加を含む）、回転、信頼できる生成結果がない入力は拒否する。

生成したレビューpackageとその履歴・成功PDF/sidecarを残し、そのレビューから取り込む必要がある。
別packageへの任意パス指定、私有データの自動探索、番号らしい数字のOCR推測削除は実装していない。

## 今回の検証

| チェック | 状態 | 結果 |
| --- | --- | --- |
| 回帰・API・配布・UI・番号レイヤー | Passed | 198件。[標準出力](issue441/evidence/roundtrip-regression-tests.txt) |
| maintained fast tests | Passed | 122件。[標準出力](issue441/evidence/roundtrip-fast-tests.txt) |
| 新規8ケース | Passed | xref再配置後の交換、追加FreeText保持、content/marker/rotation/resource改変拒否、marker単独拒否、製品sessionと背景identity |
| 実ブラウザー | Passed | 提供PDFをuploadし、古い履歴選択→再開→MMR追加修正→Save/Apply→PDF取得→取消→reload。mockなし |
| 3出力 | Passed | 各15ページ・160番号・全9pt・全820注釈・CropBox・非所有の濃い画素を保持。activeな番号streamは160個で二重化なし |
| 番号列・再起動 | Passed | baselineは保持結果と一致、編集で変化、取消で全番号列復帰。再起動後のPDF hash・3試行履歴一致 |
| 目視 | Passed（今回の範囲） | 1ページ目の「test」と追加書き込み、番号を非公開プレビューで確認 |
| 初回focused/実データprobe | Failed→修正 | fixtureにxref再配置が起きていなかった点と、content参照変更後のpage再読込不足を修正。判定の閾値・入力は変えていない |
| 初回回帰 | Failed→修正 | 196件成功・1件失敗はエラー文言の互換性。背景不一致の説明を保持して198件成功 |
| 他バージョン/設定・flatten/rewrite・全修正タイプ組合せ・手動配置・実印刷 | Not run | 今回のnative注釈1例を超える受入にはしない |
| 上流再推論・canonical detector smoke・Full68 | Not run | 認識アルゴリズム/モデル/閾値を変えていない。保持済み認識を使い、下流MMR OCRのみ実GPUで再計算 |

実MMR OCRは3回とも `text_rec=['CUDAExecutionProvider','CPUExecutionProvider']`。
CPUのみへのfallbackは受入不可とするチェックで検証した。
証拠抽出段階で注釈を入力PDFと直接再照合する処理も実行し、推論は再実行していない。
過去のNot run・失敗記録はその時点の履歴として残す。

## 再現と非公開成果物

実験runner: [mobilesheets_roundtrip_acceptance.py](../../tools/issue441/mobilesheets_roundtrip_acceptance.py)。
実ブラウザー: [resume_browser_acceptance.cjs](../../tools/review_correction/resume_browser_acceptance.cjs)。
番号列・再起動の照合: [verify_product_integration.py](../../tools/issue441/verify_product_integration.py)。

作業cwdは `.worktrees/issue441`。証拠rootは `logs/issue441/mobilesheets-roundtrip/`。
ホストPythonはmanager checkoutの `.venv_pdf/bin/python`。
GPU imageは `sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`、
PyMuPDF 1.26.4、UID/GID 1000:1001。runtime resolverで環境の互換性を確認した。
managerを `/workspace:ro`、Issue441のlogsだけを同一パスへrwでmountし、
`/workspace/.worktrees/issue441` で `PYTHONPATH` を同じworktreeに設定して実行した。

```bash
python -m tools.issue441.mobilesheets_roundtrip_acceptance prepare \
  --root logs/issue441/mobilesheets-roundtrip \
  --job /workspace/temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205 \
  --pdf '/workspace/temp/issue441/exported_by_mobilesheets/baseline edited.pdf' \
  --seed-report logs/issue441/product-integration/browser-04/browser-report.json
python -m tools.issue441.mobilesheets_roundtrip_acceptance serve \
  --root logs/issue441/mobilesheets-roundtrip --port 8441
```

prepareには `PDFSCOREBAR_SOURCE_COMMIT=705a4a288b560f1da531f2394dcacfc2c96491f1` を指定。
元の成功journal・PDF・sidecarを照合して独立コピーへ移し、元のresult identityを保持した
importとして記録した。新しい適用成功を捏造したものではなく、再開元の所有証拠を保持するためのコピー。

browser runnerは `sha256:8771dc4666e7c11440bfc6a0c6b00480e9a15b8891b45f29a52d7d995f8d1492`、
`--network host`、source read-only・evidence rw・提供PDFを `/private/input.pdf:ro` へmount。

```bash
PLAYWRIGHT_MODULE=/app/node_modules/playwright \
CHROMIUM_PATH=/ms-playwright/chromium-1226/chrome-linux64/chrome \
node tools/review_correction/resume_browser_acceptance.cjs \
  http://127.0.0.1:8441 /private/input.pdf /evidence
# サーバーを停止・再起動した後に、同じmount/networkで照合
python -m tools.issue441.verify_product_integration \
  --job /workspace/temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205 \
  --report logs/issue441/mobilesheets-roundtrip/browser-02/browser-report.json \
  --url http://127.0.0.1:8441 --output logs/issue441/mobilesheets-roundtrip/verification-final.json
python -m tools.issue441.mobilesheets_roundtrip_acceptance export \
  --root logs/issue441/mobilesheets-roundtrip --output docs/dev/issue441/evidence
```

回帰テストは次の組合せ。採用ログは `regression-final-03.log`、`fast-final-02.log`、
`browser-02.log`、`verify-restart-final.log`、`export-final.log`。初回失敗ログも同じrootに保持。

```bash
/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python -m pytest \
  tests/test_issue441_mobilesheets_roundtrip.py tests/test_review_correction_history.py \
  tests/test_review_correction_application.py tests/test_review_correction_server.py \
  tests/test_review_correction_state.py tests/test_issue441_annotated_layer.py \
  tests/test_distribution_surface.py tests/test_docker_runtime_contract.py \
  tests/test_manual_correction_handoff.py tests/test_issue396_review_ui.py \
  tests/test_review_correction_client.py tests/test_numbering_preview.py \
  tests/test_reviewed_movement_apply.py -q --disable-warnings
mapfile -t issue441_fast_tests < <(sed -n 's/^FAST_TESTS ?= //p' Makefile | tr ' ' '\n')
/home/masaki_muramatsu/ws_PDFScoreBar/.venv_pdf/bin/python -m pytest "${issue441_fast_tests[@]}" -q --disable-warnings
```

私有成果物は `browser-02/{baseline,edited,undone}.pdf`、画面PNGと `preview/index.html`。
PDF/MSF・楽譜画像・注釈本文・raw correctionはGitHubへ添付していない。
GitHubには実装・テスト・検証コード・入力/出力hashと集計だけを公開する。
Draft PRを維持し、他の未受入項目やIssue全体の完了を宣言しない。
