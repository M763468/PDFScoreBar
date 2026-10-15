# Issue #410: 候補生成と隔離runtime・GUI検証（2026-10-15）

この候補の検証後に行った利用者受入とGUI修正は
[手動受入の指摘と修正](UX_FEEDBACK_20261015.md)に記録する。以下は元の固定候補の証拠として保持する。

[昇格内容と受入契約](PROMOTION_SCOPE.md)に基づき、固定commitからの候補生成、
新規PDF処理、実GUI補正、補正後の番号・実PDFを確認した。
完全JSON一致は差分診断として扱い、確認済みhairpin誤検出の削除は改善として採用する。

## 固定した対象

| 項目 | identity |
| --- | --- |
| 実装source | `6cff5a1f72f25e86accd89aec8e37d11d068cd69`（develop向けtopic branchのローカルcommit） |
| 比較・親main | `893f17853a6fc73d252a621e8621385e799d5bc6` |
| 生成candidate | `fedf8608ee5b095f175ac45931433069b688f20a` |
| candidate tree | `45e7ccf04f7ad47cf691d9744247b592697e0bc2` |
| 配布manifest | schema 3、SHA-256 `5011dee1d54d6c0b7a2538f98ca4219e9eba7c4e2bd0d2f2c8673776f568b397` |
| 選択 | 105ファイル + 生成provenance、合計106ファイル |
| image | `pdfscore_issue410_rc1`、固定ID `sha256:b05a4319cfd118526146aacb52b8d6a2229663672ddbf70ee7e42af725093cf1` |
| source fingerprint | `22b6a1894a90f1ffbd84d496b22e74754f60638989befa0211cdbeeac9dc2050` |
| 実行環境 | Docker Desktop、image内Python 3.12、RTX 4060、CUDA/ONNX CUDA providerをpreflightで確認 |

これは準備用topic sourceの候補であり、accepted developからの最終promotion候補ではない。
このタスクで`src/`、`configs/`、`models/`、Dockerfile、pyproject、`docker/`は変更していない。
`016e1818`とのGit比較でも数値runtimeとmodel/configの差分0を確認した。

## 実装と検証結果

| 検証 | 結果 | 証拠と範囲 |
| --- | --- | --- |
| 新release toolの回帰tests | PASS、17件 | 実Git repositoryで固定SHA、再現性、元mainだけを親にすること、作業treeの混入防止、mode、改変・欠落・未宣言依存・symlink・余分なcommitの拒否を確認 |
| release + 既存distribution tests | PASS、35件 | 17 release + 18 distribution。既存Gitなしmaterializerも維持 |
| `make test-fast` | PASS、114件 | hostの既存`.venv_pdf`を使用 |
| scoped Ruff / format、diff、local links、workflow YAML | PASS | 変更したPython、docs、CI syntax。GitHub CI実行とは区別する |
| repository-surface | PASS | 新testをvalidation_harnessに登録。105-file選択は維持 |
| independent candidateの2回生成 | PASS | 異なる出力directory/branch名でも同じcandidate commitとreport。実行後もcontent・mode・親・commit identity検査PASS |
| candidateだけからのDocker build | PASS | Git、tests、GT、agents、開発・再現toolsがimage内にないことも確認 |
| 公開preflight | PASS | CUDA device、ONNX providers、model、pinned runtime。errorsは空 |
| 公開PDF job | PASS | Prokofiev Sym1 PDFの1ページを利用者既定の300 DPIで新規実行。requested/processed 1、skipped 0、warnings 0、376.576秒 |
| 新規jobの公開review launcher | PASS（Docker内browser） | 実GUI保存→適用→PDF取得、変更後のstale状態と既存成功結果保持。span 2 / 3の2 attemptで局所加算・実PDF pixels・download一致。原譜面のGT補正ではなくmanual overrideの動作検証 |
| 保持19ページの実GUI休符確認 | PASS、対象6件 | 入力前に一覧から物理小節を選び、原譜面の印刷数字・旧値を画像に保存。count-1の3未検出を含む。英日案内を確認 |
| 6件のGUI追加・保存・適用 | PASS | Festival 5件、Sibelius 1件。フォーム/公開ボタンを使用し、補正JSONの事前投入はしていない |
| 補正の下流意味・実PDF | PASS、19ページ・962物理小節 | 6箇所の加算、全後続小節の累積差分、段頭・ページ頭・末尾next_number、PDF pixel19ページとbrowser download hashを確認。全面的な絶対番号GT認証とは異なる |
| 元成果物と自動結果の保存 | PASS | コピー元/コピー先の274 artifact hashを再確認。過去の/workspace symlink19件も正確な実在targetへhash照合して解決。upstream再推論なし |

新規job: `job-512d5af461ed4c65945376c8dd4bd9b0`。
全補正attemptで`consumed_inputs.json`と成功PDFのhashを保持した。
新規jobは`attempt_0001` / `attempt_0002`、保持2作品は各`attempt_0001`。

## 休符6件と番号の確認

| 原譜面 / JSON位置（0-based） | 自動値 → GUIで保存した印刷値 | 検証 |
| --- | --- | --- |
| Festival/001 s0m0 | 37 → 7 | 原GUI画像の7を確認、局所加算7 |
| Festival/001 s0m2 | 1 → 4 | 原GUI画像の4を確認、局所加算4 |
| Festival/002 s3m2 | 7 → 2 | boxed rehearsal 7と休符2を区別、局所加算2 |
| Festival/004 s2m2 | 1 → 3 | 原GUI画像の3を確認、局所加算3 |
| Festival/009 s0m0 | 1 → 3 | boxed rehearsal 31と休符3を区別、局所加算3 |
| Sibelius/003 s2m6 | 111 → 4 | 原GUI画像の4を確認、局所加算4 |

Festivalのページ頭は、page002で69→42、page003で118→86、page005で205→175、
page009で379→349。Sibeliusはpage004で434→327、その後も当該誤読の差分-107が伝播する。
全19ページの段頭/各小節/次ページ/終端を、原画像から読んだ6値の累積差分と照合した。
これらは保持geometryに対する補正の効果であり、既存小節線残差を含む全絶対番号の正解保証ではない。

Festival/page001は原譜面を再読すると、休符7 + 通常1 + 休符4 + 通常1の4枠で合計13。
開始1から次段は14、第2段の通常4小節後は18となる。実GUIで7と4を補正した実際のPDFにも
**1 / 14 / 18**が表示され、埋込pixel照合とPDFの表示画像でも確認した。
旧#415 sampleのbasisは同じ4項を列挙して合計12とした算術誤りを含み、13/17と食い違う。
番号を合わせるresetや小節の除外は行っていない。

旧sample/GTは変更していない。14/18を支持する新しい画像・算術・実PDF証拠を保存し、
既存sampleファイルの修正は別の明示的なGT reviewで扱う。旧sampleによる評価結果を書き換えない。
自動MMR TP171/FN3/誤読3/FP0は手動補正後の値へ置き換えず、6件の認識残差として保持する。

## 再利用した評価と未実施範囲

- Canonical 360 DPIの85/85、hard FP0/FN0/soft0は#414の受理済み保持証拠を再利用した。
  証拠は`logs/issue414/gpu-smoke-review-20261014/canonical/detector_accuracy_smoke_summary.json`。
  入力hash `48e073dd8184495b9751ad62e85a872bc93cce751ba0a8c988300f7c5ae444a6`、
  PDF hash `19ae15f01835456df08194c072be428c9b94fb51c7a1e04fdea7c0a789a50b41`。
  candidateのMMR source hashはそのsmokeで確認された
  `d7b996584f6593d26ad9f84617e20c233552120a903db577dc19a04302c4d2c7`と一致し、
  accepted developからの数値source/config/model差分も0。新規360 DPI評価の実行とは称さない。
- Fresh Full68 detector/OCRは未実施。配布/CI/tooling/docsの変更であり数値runtimeを変更せず、
  保持結果の再利用とcandidate自身の新規1ページGPU実行・19ページ補正検証を行ったため。
- 既知位置を手掛かりにしたagentのGUI検証であり、利用者の自力発見率、全68ページの網羅確認、
  長休符GTの完全性、確認作業の負担の受理は未認証。
- Sym5 IIIのmovement resetを実candidateのGUIで完了させた証拠は今回未取得。
  movement-local 1/6/11とscore-wide 567/572/577の規約・適用を別途判定する。
- #416のFP11/FN32の下流disposition、追加修正の要否と安全な手動補正可否は未確定。
- GitHub CIは未実行（ローカルのみ。push/PR作成はしていない）。

## 実行時の制約と失敗を保持した範囲

- Docker socketはsandbox内で拒否されたため、許可されたhost実行へ切り替えた。
- 過去のstaging画像symlinkが`/workspace`を向くため最初のreview package生成は失敗した。
  正確なtargetをhostで解決し、同じbytesを隔離成果物へコピーして再実行PASS。
- Docker Desktopのhostとcontainerのlocalhostが分離しており、host Chromium接続はtimeout。
  同じDocker network内の実Chromiumで検証を完了した。host browserからの直接到達をPASSとはしない。
  配布の対応platformであるLinux Docker上の最終利用者導線と区別する。
- 検証用browser imageにはheadless-shellがなく、既存のfull Chromium実行ファイルを明示した。
- 検証driverが非表示の任意理由欄を操作しようとして停止した。表示中の正式なUI操作だけで再実行した。
- 新規jobの最初のGUI applyは成功したが、検証側の証拠directory所有権でPDF保存がEACCESとなった。
  その成功attemptを保持してbrowser側userを合わせ、別spanの保存/適用/stale確認を完了した。

いずれも失敗ログを削除せず、後続成功と区別した。元のdataset/model/GTや実装の数値設定は変更していない。

## 証拠とpromotion判断

ローカル証拠root: `logs/issue410/implementation/20261015/`（元checkout、Gitではignored）。
主要な記録は`candidate-static.json` / `candidate-repeat.json`、`image-identity.txt`、
`docker-build.log`、`preflight.log`、`normal-pdf.log`、`normal-browser/browser-report.json`、
`normal-correction-semantics.json`、`retained-review/{preparation,symlink-resolution,discovery,observed-rest-counts,gui-corrections,semantic-verification}.json`。
GUI画像、downloadしたPDF、attempt/consumed inputs、検証driverと失敗ログも同rootに保持した。

**判定: main promotionは保留。** 生成・隔離runtime・既知6件の操作/下流検証は前進したが、
最終accepted developからのfreeze、Festival sampleのGT review、movement reset、
小節線残差のdisposition、全ページ確認と確認負担を含む製品受入が残る。
完全JSON一致67/68や確認済みhairpinの削除は保留理由にしない。
main/developのmerge、tag、GitHubのIssue/PR更新は行っていない。
