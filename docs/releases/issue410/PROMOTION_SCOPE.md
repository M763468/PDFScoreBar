# Issue #410: 初回main昇格の内容と受入契約

[#410](https://github.com/M763468/PDFScoreBar/issues/410)の配布・昇格作業に使う、
関連Issueの統合内容、証拠の適用範囲、release受入契約の記録。
2026-10-15にGitHubのIssue/PR、source、manifest、Git refsを照合した。
本記録は初回昇格の準備であり、候補のrelease受入やmain更新の完了記録ではない。
実装後の固定candidate・GPU/PDF/実GUI/補正後の検証は[2026-10-15検証記録](VALIDATION_20261015.md)を参照する。
その後の利用者の手動受入、番号規約とGUI改善は[手動受入の指摘と修正](UX_FEEDBACK_20261015.md)を参照する。

## 昇格元と配布対象

| 項目 | 確認したidentity / 意味 |
| --- | --- |
| develop | `016e181861270f1adc753778ef71422fa51f2716`、PR #420統合済み |
| 現main / default branch | `893f17853a6fc73d252a621e8621385e799d5bc6`、2026-05-31のPR #174統合時点。現在の製品配布とは異なる |
| 配布manifest | [MINIMAL_MAINLINE_SURFACE.json](../../MINIMAL_MAINLINE_SURFACE.json)、schema 3 |
| 現在の選択 | runtime 93 + support 11 + metadata 1 = **105ファイル**。生成provenanceを加えた出力は106ファイル |
| #409の受理済み配布 | PR #412 / `4194a7371a2b4d4d324f52bfa23e3adac225fbd1`、104ファイル |
| #409以降の選択追加 | `src/measure_numbering/clipped_end.py`（#218 / PR #417）。選択からの削除なし |

配布対象はmanifestの`runtime_bundle_patterns`、`distribution_support_patterns`、
`distribution_metadata_patterns`の和集合に限定する。mainとの差分全体を移す運用にはしない。
開発用tests、GT、評価・再現tools、agents、内部docs、実験結果はdevelopに保持する。
この昇格記録自体もdevelop側の資料であり、配布対象へ追加しない。

今回確認したconfig/modelは#409時点からbyte不変。ただし番号・幾何・MMR sourceは変更されている。
config/model不変だけを理由に旧配布候補の検証を現候補の合格証拠にはしない。

## 取り込まれた変更と関連Issueの引継ぎ

| Issue / PR | 現在の統合状態 | mainへ出す変更・引き継ぐ判断 |
| --- | --- | --- |
| [#409](https://github.com/M763468/PDFScoreBar/issues/409) / [#412](https://github.com/M763468/PDFScoreBar/pull/412) | Issue CLOSED、PR統合済み | 最小配布manifest、materializer、Docker/PDF/review/apply、英日UI、failure contracts。104-file隔離受入は歴史的baselineとして保持 |
| [#413](https://github.com/M763468/PDFScoreBar/issues/413) / [#418](https://github.com/M763468/PDFScoreBar/pull/418) | Issue CLOSED、`9183de380591878b1a2751d5975373035f10079c`で統合済み | 空段を含む内部Pageとcompact JSONの段identityを一致させる。保持Full68の認識→適用不一致104→0。認識改善とは区別する |
| [#415](https://github.com/M763468/PDFScoreBar/issues/415) / [#419](https://github.com/M763468/PDFScoreBar/pull/419) | Issue CLOSED、`28dc0bbabf9bb968155080d233f25e1ce92bcc9f`で統合済み | GT provenance、独立番号サンプル、適用/局所加算/連続性/JSON-PDF監査。検証整備の完了であり、全番号の正解認証ではない |
| [#218](https://github.com/M763468/PDFScoreBar/issues/218) / [#417](https://github.com/M763468/PDFScoreBar/pull/417) | Issue CLOSED、`0f3e1cc8078304047621b26107ce530199a28ecb`で統合済み | 実3div/4div、声部保持・共有境界の修復、reduced-line staff保護、右端小節の回復。空のhairpin誤検出1件の削除を改善として採用（次節） |
| [#414](https://github.com/M763468/PDFScoreBar/issues/414) / [#420](https://github.com/M763468/PDFScoreBar/pull/420) | PR統合済み、Issueは確認時OPEN | staff同票OCRの裏付けによる79→4回復、全小節確認と英日案内。固定Full68の自動MMRはTP171/FN3/誤読3/FP0。残存6件は実candidateのGUI受入へ引継ぎ |
| [#416](https://github.com/M763468/PDFScoreBar/issues/416) | Issue OPEN、診断を引継ぎ | 小節線FP11/FN32。43残差は43個の番号誤りを意味しない。下流影響・手動補正の安全性をrelease側で判断する |
| [#421](https://github.com/M763468/PDFScoreBar/issues/421) | Issue OPEN、#218から独立したfollow-up | 残存55件の偽譜表候補を安全に識別し、実在する少線譜表を保護する。全55件の削除を昇格条件にしない。完全JSON一致を音楽的正確性の必須条件にしない方針も明記済み |

#410本文の「#218 low priority」や#414の「merge待ち」は、上表の最新GitHub/Git状態を優先する。
#414の認識残差、#416の小節線残差に対する追加アルゴリズム調整を配布変更に混ぜない。

## 完全JSON一致の扱いと改善の採用

**2026-10-15のユーザー指示に基づく#410の受入契約:** 完全JSON一致をmain昇格の必須条件にしない。
sourceに根拠のある改善は、音楽的な番号付けと必要なconsumer契約の非回帰を確認して採用する。

#417は、受理済み#413 baselineとの比較で、番号付き段・小節構成・最終番号が68/68一致し、
新しい番号付き段・空診断領域の追加は0だった。完全JSONの差分はSibelius Viola/page_009の
**原画像で確認した空のhairpin誤検出1件の削除**だけであり、この削除は改善として受け入れる。
空診断情報の件数が減ることは明記するが、この差分を昇格のblockerにはしない。

旧契約での「完全JSON一致67/68 FAIL」は比較結果として残す。
旧実験のPASSへ書き換えず、今回のpromotionでは次の基準を適用する。

- 番号付き物理段・小節のidentity、構成、休符加算、段頭/ページ間の番号が、期待する意味的契約を満たす。
- 意図した正誤修復による番号の変更は、原画像・旧新出力・下流影響で正当化する。
  #413の補正適用修正や#414の79→4回復も旧番号との一致を要求しない。
- 改善を主張する診断差分は、source画像と差分位置を記録し、利用者・consumerへの影響を確認する。
  今回のhairpin削除の受理を、任意の将来の差分や未確認の領域削除への包括的受理にはしない。
- per-page/combined/final PDFの内容、補正優先順位、schemaとprovenanceの契約を維持する。

完全JSON一致は差分を発見する参考検査として使う。改善と回帰の判断は上記契約で行う。
根拠: [#218完了記録](https://github.com/M763468/PDFScoreBar/issues/218#issuecomment-6156199031)、
[実譜面検証](../../refactors/issue218_real_divisi_validation.md)、
[#421の受入・評価原則](https://github.com/M763468/PDFScoreBar/issues/421)。

## releaseを止める条件と参考指標

| 項目 | promotionでの位置づけ | 現在ある証拠 / 新候補で必要な証拠 |
| --- | --- | --- |
| 正確な選択・dependency/reference/content hash・provenance | 必須gate | 固定SHAから独立Git candidateを2回生成、同じcommitとclean-checkout検査PASS。最終accepted developのfreezeは別途必要 |
| Docker build/install、canonical GPU preflight、通常PDF | 必須gate | 今回candidateでDocker build、GPU preflight、新規1ページPDFと公開review launcherを検証PASS。host browserの直接到達には環境制約あり |
| compact system identity、manual優先、page rebasing、連続性、PDF整合 | 必須gate | #413/#415の決定的testsと保持replayを再利用し、新candidateのsource identitiesと結び付ける |
| canonical 360 DPI smoke | 対象scopeの回帰gate | 85/85、hard FP0/FN0/soft0。今回は数値source/config/modelがaccepted developと同じため#414の保持証拠をidentity照合付きで再利用。新規360 DPI評価とは区別する |
| #218幾何 | 対象scopeの回帰gate | 元six-input topology、80/80 interval/番号、19/19 system数、3/3 MMR、reduced-line保護を維持。確認済みhairpin削除は採用 |
| MMR残存6件の実GUI発見・保存・適用 | 初回release必須gate | 補正前の原GUI画像、6件のフォーム操作/保存/適用/PDF取得を確認。既知位置を手掛かりにしたagent検証であり、利用者の自力発見や全ページ確認の認証は残る |
| 補正後の局所加算・後続段頭/次ページ・実PDF独立照合 | 初回release必須gate | 6加算、19ページ962物理小節の下流差分、実PDF pixel19ページ、download一致を確認。全絶対番号のGT認証ではない |
| Festival anchor、Sym5 III reset、小節線残差のdisposition | 初回release必須gate | 後述の未裁定を解消し、残る限界と安全な補正可否を明示する |
| 人手確認の負担とリスクのaccept/hold | 初回release必須判断 | 見落とし、読めない数字、誤/欠小節線、未指定resetを含めて記録する。未決定 |
| Full68自動MMR TP171/FN3/誤読3/FP0、小節線TP3535/FP11/FN32 | 品質の報告値と比較元 | 手動補正後の結果にすり替えない。各変更の回帰契約は維持し、昇格時に既知限界を明記する |
| 旧68/68番号一致、PDF/JSON 68ページ・637ラベル一致 | 過去の非回帰/consumer整合の証拠 | 譜面上の正しさの代用にはしない |
| #417完全JSON一致67/68 | 差分診断の参考値 | 確認済みの空hairpin削除であり、昇格blockerにしない |

Full68の上流推論を毎回繰り返す契約にはしない。同一入力・source/config/model・幾何の適用範囲を
照合し、有効な保持出力は再採点/replayに使う。数値・幾何を追加変更した場合は、
[validation policy](../../dev/VALIDATION_POLICY.md)とその変更の元契約に従って必要な評価を追加する。

## 残存MMRと独立番号判定

[#414の残差と操作手順](../../refactors/issue414/MMR_STAFF_CONSENSUS.md#residual-disposition-manual-discovery-and-correction-before-release)、
[公開user guide](../../USER_GUIDE.md#check-and-correct-multi-measure-rests)を使う。
候補の原譜面を全ページ確認し、警告やconfidenceだけで対象を絞らない。
以下の位置は保持geometryのacceptance inventoryであり、実GUIの発見を事前入力で置き換えない。

| score/page | JSON system/measure（0-based） | GUI位置（1-based） | 自動値 → 原譜面の値 |
| --- | --- | --- | --- |
| Festival/001 | 0/0 | 1/1 | 37 → 7 |
| Festival/001 | 0/2 | 1/3 | 1（未検出）→ 4 |
| Festival/002 | 3/2 | 4/3 | 7 → 2 |
| Festival/004 | 2/2 | 3/3 | 1（未検出）→ 3 |
| Festival/009 | 0/0 | 1/1 | 1（未検出）→ 3 |
| Sibelius/003 | 2/6 | 3/7 | 111 → 4 |

実候補で位置を再確認し、原画像/観察/画像hash、選択位置、旧新値、英日案内、
保存corrections、application attempt ID、consumed inputs、final JSONと実修正PDFを保持する。
後続段頭と次ページまで独立照合する。自動認識の残存6件は未解決として残す。

Festival/page001の旧[#415サンプル](../../../tools/issue415/row_start_samples.json)は13/17だが、
保持4枠への休符補正7+1+4+1は合計13で、開始1なら後続段頭14/18となる。
旧basisの「合計12」は算術上不整合。今回、原GUI画像と原譜面を再読し、4枠の合計13、
次段14/18を実補正PDFでも確認した。旧sampleは変更せず、新旧根拠を保存した。
sampleの変更は別の明示的なGT reviewで扱う。具体的証拠は[検証記録](VALIDATION_20261015.md)を参照する。

Sym5/page012 IIIの印刷番号1/6/11と保持score-wide番号567/572/577は、movement-localと
score-wideの規約を区別する。reviewed resetを実workflowで扱い、休符誤読の帳尻合わせには使わない。
全絶対番号、および休符のある52ページ全域のGT漏れ不存在は未認証のまま明記する。

#416の旧FN_cnn5は全件採用済みで二重線ストローク不足/1対1割当の問題。
CNN棄却と誤記せず、FP11/FN32を維持したまま下流の物理小節と補正可否を評価する。
MMRを直しただけで小節線/resetの問題も解決したとは扱わない。

## branch・候補生成・promotionの設計

[branch policy](../../BRANCH_POLICY.md)に従い、準備コード/docsはdevelop向けtopic branchで扱う。
配布candidateには**versioned/ephemeralな`release/<cycle>-rc<N>`**を使う。
固定された候補ごとに証拠を結び付け、検証中の候補を上書きしない運用とする。

1. 必要変更を受理したthen-current develop SHAとmanifest/config/model identitiesを固定する。
   現在の`016e1818`は今回の準備snapshotであり、将来の昇格元を固定する指示ではない。
2. 固定source SHAのcommitted Git blobsから105-file選択をmaterializeする。
   作業treeの変更は読み込まない。欠落・symlink・未宣言依存・unexpected filesを拒否する。
3. frozen main SHAをparentとする候補commitに、選択された配布treeと生成provenanceだけを収める。
   mainに残る選択外ファイルを持ち越さず、developの開発supersetをmergeしない。
   developにあるデータ・履歴・モデルを削除する作業ではない。
4. 候補commitのclean checkoutで全gateを検証する。Dockerへdevelop rootをmountせず、
   GT/検証runnerは配布外の評価側に置く。入力PDF・operator登録modelは宣言された入力として区別する。
5. 候補からmainへの専用promotion PRにscope、全gateと限界、accept/hold、source/candidate identitiesを記載する。
   merge後のmain commitを記録する。tagを使うならtagとmain commitの対応も残す。
   merge・tag作成・保護/default-branch設定の変更は別の明示的な実行指示を受けて行う。

[release_candidate.py](../../../tools/release_candidate.py)の`create` / `check`を実装した。
source/main両方のfull commit SHAを必須にし、sourceのcommitted bytes・modeを取得する。
作業treeがdirtyでもローカル変更は一切取り込まれず、provenanceの`source_dirty=false`は
このcommitted snapshotについての記録となる。従来の作業tree用materializerは開発用途に残す。

生成先はfreshな独立Git repositoryで、sourceのobject alternatesや開発root mountに依存しない。
source/main/manifest/generator hash、file hash/modeと固定author/date/messageを使うため、
同じ入力から同じcandidate commitを生成できる。Git metadataはrootだけを検査対象から分離し、
配布content、sourceとの一致、親commit、clean checkout、commit identityを検証する。

```bash
source_commit=$(git rev-parse HEAD)
main_commit=$(git rev-parse origin/main)
python3 tools/release_candidate.py create /tmp/pdfscorebar-issue410-rc1 \
  --source-commit "$source_commit" --main-commit "$main_commit" \
  --branch release/issue410-rc1 --report logs/issue410/candidates/rc1/static.json
python3 tools/release_candidate.py check /tmp/pdfscorebar-issue410-rc1 \
  --source-commit "$source_commit" --main-commit "$main_commit"
python3 tools/materialize_distribution.py check /tmp/pdfscorebar-issue410-rc1 --git-checkout
```

source/main SHAは検証記録から再使用し、検証途中に再解決しない。実releaseには受理されたdevelop SHAを指定する。
reportは候補外に保持する。`static_checks=PASS`でも`release_accepted=false`を出力し、
GPU/GUI/semantic判断の代わりにはしない。共有branchの変更、push、merge、tagは実行しない。

[repository-surface CI](../../../.github/workflows/repository-surface.yml)に、新toolの回帰tests、
独立candidateの2回生成・commit/report再現性、隔離content検査とprovenance artifact保持を追加した。
develop push/PRおよび手動実行に対応する。`.github/`や検証toolsは配布外のまま維持する。
GitHub CI自体の実行結果と、ローカルの同等commandの成功は別に報告する。

初回昇格前はdefault mainが古いことと、維持中の実装がdevelopにあることを利用者へ案内する。
昇格後のmainは公開user guideのinstall/run/review/correct経路を案内し、開発作業はdevelopへ誘導する。
READMEに初回promotionまでmainが歴史版であること、maintained実装と開発先がdevelopであること、
抽出候補のprovenanceとrelease受入の区別を追記した。

## 今回の準備検証と証拠

source clean状態で、次を実行した。静的配布確認でありruntime/release受入ではない。

```bash
python3 tools/check_repository_surface.py
python3 tools/materialize_distribution.py --help
python3 tools/materialize_distribution.py materialize /tmp/pdfscorebar-issue410-016e1818-preparation
python3 tools/materialize_distribution.py check /tmp/pdfscorebar-issue410-016e1818-preparation
python3 tools/materialize_distribution.py materialize /tmp/pdfscorebar-issue410-016e1818-repeat
python3 tools/materialize_distribution.py check /tmp/pdfscorebar-issue410-016e1818-repeat
```

全command exit 0。105選択ファイル+provenanceの106ファイルは2回の抽出でbyte一致。
manifest SHA-256: `4f49702e54c0ef28fa2a17007835cab197a8ae79e0588e278b33d6bd528e3461`。
config SHA-256: `0edfdfda89ed50be6d0dafbf28fccc80840ef6330f193d19823a94f934cb2209`。
MMR checkpoint SHA-256: `f163fa2a7679d12c0f4fe6fc2fadc7ed1f144035779a18b83a303bfa6d35903a`。

ローカル証拠は元checkoutの`logs/issue410/preparation/20261015-016e1818/`に保持。
`inventory.json`にsource/main SHA、全model/config/manifest identities、選択差分、実行command、
exit code、ログ、未実施gateを記録し、`DISTRIBUTION_PROVENANCE.json`に全配布file hashを保持した。
ignoredのローカル保持物であり、GitHub添付ではない。

上記は最初のdocs整理時点の証拠。続く実装・runtime検証は別のsource/candidate identityと共に記録する。
tool・checker・CI・docs・test分類を変更し、productionの数値実装・config・model bytesは変更していない。
配布manifestのtest分類追加はdeveloper側metadata変更であり、105-file選択は維持する。
今回採用したJSON診断改善とは別に、実候補での必須gateが揃うまでmain昇格は保留する。
