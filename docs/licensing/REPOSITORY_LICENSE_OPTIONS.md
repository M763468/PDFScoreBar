# リポジトリ自身のライセンス方針と適用準備（#505）

[#505](https://github.com/M763468/PDFScoreBar/issues/505) の方針・準備記録。原文は日本語（正本）。英語版は未作成。
第三者部品の義務は [第三者ライセンス監査（#504）](THIRD_PARTY_LICENSE_AUDIT.md) を入力とし、ここでは重複しない。

> **本文書はライセンスの許諾ではない。** 本文書の記述、および本文書を含む `develop` / `main` のどの版によっても、
> PDFScoreBar の first-party のコード・文書・その他の資料について、利用・改変・再配布の許諾は与えられない。
> リポジトリには `LICENSE` がなく、正式な許諾は将来の `main` リリースで `LICENSE` 一式を追加した版から始まる。
> 法的助言ではない。

## 1. 現在の方針と状態（2026-11-13、`develop@04c16674d7e6`）

オーナー決定（#505、2026-11-08 以降のコメント）:

1. first-party コードには **`AGPL-3.0-or-later`** を採用する。ライセンスの選択は再検討しない。
2. 他者の商用利用は禁止しない。改変版を非公開のまま囲い込んだネットワーク提供を抑えることを重視する。
3. **現時点で `develop` には `LICENSE` を付与しない。**
4. OMR-DLN 除去等の整備と `main` への昇格の後、正式リリース対象の `main` に適用する。**保留しているのは適用時期だけ。**
5. 第三者のコード・重み・データを first-party のライセンスで再許諾しない。

現状:

- ルートに `LICENSE` / `NOTICE` / `COPYING` / `REUSE.toml` はなく、`pyproject.toml` に `license` 欄はない。
- GitHub で公開されていることだけでは、利用・改変・再配布の一般的な許諾にならない（GitHub 利用規約に基づく GitHub 上での閲覧・fork を除く）。
- そのため、`develop` を基にした実行物を第三者へ配布・提供するには、#504 の第三者義務とは別に first-party の権利処理が必要である。
  限定試用（[#508](https://github.com/M763468/PDFScoreBar/issues/508)）との関係は §6 を参照。

AGPL についての注意（オーナー方針の前提。2026-11-08 の #505 コメント）:

- AGPL は商用利用や第三者のサービス提供を禁止しない。
- §13 の対応ソース提供は、**改変版**をネットワーク越しに利用者に操作させる場合に関わる。提供先は受領者・ネットワーク利用者であり、
  GitHub での公開や、オーナー・上流への還元を義務付けるものではない。
- オーナーは自分が権利を持つ first-party コードに別の商用条件を提示できるが、HOMR・PyMuPDF 等の第三者 AGPL を代行・免除できない。
- 一度 AGPL で公開した版の許諾は取り消せない。

## 2. 経緯

| 日付 | 出来事 |
| --- | --- |
| 2026-11-07 | 本文書の初版。Apache-2.0 を推奨候補とし、オーナー決定待ちとした（比較は §8 に履歴として保持） |
| 2026-11-08 | オーナー意向により AGPL-3.0-or-later を第一候補に見直し、採用を指示 |
| 2026-11-08 | PR #521（`docs/issue505-agpl-license`）で `LICENSE`・`NOTICE`・`THIRD_PARTY_NOTICES.md`・`REUSE.toml`・`LICENSES/`・`pyproject.toml`・README・配布 manifest を実装し検証 |
| 2026-11-08 | オーナー方針を更新: 正式な適用は将来の `main` リリース時に限る |
| 2026-11-08 | **PR #521 を取り下げ。** 公開 Draft PR の head 自体が LICENSE 全文と許諾表示を含み、Draft・未マージでも許諾と解釈される余地があるため、revert commit `b73e8a64` を通常の push で追加して Close した。実装一式は git 管理外の非公開領域へ退避 |
| 2026-11-11 | PR #523 で OMR-DLN 重みと Ultralytics を production から除去（#522） |
| 2026-11-13 | PR #525 で #504 監査の現行節（§0）と Python 台帳を追加 |
| 2026-11-13 | 退避した実装一式を最新 `develop` に合わせて再構成し、非公開の環境で適用リハーサルを実施（§5） |

公開済みの commit `966ce854`・`c091ad48` は、ブランチ履歴、PR の記録、取得済みの複製やフォークに残り得る。
revert や Close によってそれらの効力が消えたとは断定しない。必要であれば法律の専門家に確認する。

## 3. 権利台帳（正式適用時の分類）

正式適用時は `REUSE.toml` で path 単位に宣言する（各ファイルへの header 一括追加はしない）。
`LicenseRef-PDFScoreBar-NotLicensed` は「本リポジトリのライセンスを適用せず、何も許諾しない」ことを示す識別子。

| 区分 | 範囲 | 権利者・出所 | 適用時の扱い | 通知 |
| --- | --- | --- | --- | --- |
| first-party コード | `src/`、`tools/`、`docker/`、`scripts/`、`tests/`（下記 fixture を除く）、`experiments/`、`configs/`、`Makefile`、`Dockerfile*` | オーナー（§4 の寄与者確認） | `AGPL-3.0-or-later` | `LICENSE`、`NOTICE` |
| first-party 文書 | `docs/`、`README*`、`AGENTS.md`、`.github/` | 同上 | コードと同じ `AGPL-3.0-or-later` | 同上 |
| 補正 GUI | `tools/review_correction/*.html` / `*.js` 等 | first-party。外部ライブラリ・CDN を含まない | `AGPL-3.0-or-later` | 同上 |
| HOMR の引用断片 | `docker/patch_homr_onnx_provider.py` 内の置換対象として引用した数行 | HOMR 作者（上流は `AGPL-3.0` と表示し、only / or-later を明示しない） | ファイル全体を `AGPL-3.0-or-later AND AGPL-3.0-only` と宣言。断片は再許諾しない | `NOTICE`、`THIRD_PARTY_NOTICES.md` |
| 第三者コード（未同梱） | HOMR、PyMuPDF、Real-ESRGAN、BasicSR 等。build 時に取得 | 各上流 | 対象外 | `THIRD_PARTY_NOTICES.md`（HOMR・BasicSR の改変表示を含む） |
| first-party 重み: MMR | `models/mmr/mmr_classifier_best.pth`（git 管理、配布物に含まれる） | オーナーが学習。torchvision の ImageNet 事前学習重みから初期化。学習データは楽譜由来 | `NotLicensed` | `NOTICE` |
| first-party 重み: barline CNN | 本リポジトリの GitHub release。git には `models/barline_cnn/manifest.json` のみ | オーナーが学習 | git 管理外のため `REUSE.toml` の対象外。重み自体は許諾しない（`NOTICE` に記載） | `NOTICE`、`THIRD_PARTY_NOTICES.md` |
| 第三者重み | HOMR ONNX、Real-ESRGAN、RapidOCR 同梱モデル | 各上流（#504 §0.3） | 対象外。git には manifest と SHA-256 のみ | `THIRD_PARTY_NOTICES.md` |
| 初期化元・学習データ | ImageNet（torchvision 事前学習重み）、楽譜画像 | 第三者 | 本リポジトリに含めない。重みへの条件の波及は未確定（§4） | — |
| 評価・GT データ | `data/evaluation2/**`（GT 座標 JSON 等）、`configs/cnn_barline_runs/issue44_baseline_v1/fixtures/**`、`experiments/issue333/{corpus.json,phase25_ground_truth.json,results/**}` | ラベルは first-party。元の楽譜は第三者著作物（保護期間内の作品を含む） | `NotLicensed` | `NOTICE` |
| 楽譜由来の評価証拠・reviewed GT | `tools/issue522/evidence/*.jpg`（楽譜ページの切り抜き）、`tools/issue522/evidence/review_audit.json`、`tools/issue415/reviewed_gt.json`、`tools/issue415/row_start_samples.json`、`tools/issue416/production_validation.json` | 同上 | `NotLicensed`（2026-11-13 の再分類で追加） | `NOTICE` |
| 楽譜由来の test fixture | `tests/fixtures/expected_overrides_page_*.json`、`tests/fixtures/movement_boundaries/**`、`tests/fixtures/system_grouping/issue218_{la_mer,measure_gt,real_detection,real_score}.json` | 第三者の楽譜（IMSLP 等）から作った座標・期待値 | `NotLicensed` | `NOTICE` |
| 合成 fixture（#218） | `tests/fixtures/system_grouping/issue218_3div*` / `4div*`（PNG 6、JSON 2） | first-party。`generate_issue218.py` で 8 ファイルとも byte 一致で再生成できる（2026-11-08、2026-11-13 に再確認） | `AGPL-3.0-or-later`。#504 旧監査の「出典記録なし」はこれで訂正 | — |
| Graphify 参照資料 | `.agents/skills/graphify/references/**`（8 件） | 第三者。導入済み `graphifyy 0.9.41` の `graphify/skills/*/references/` と byte 一致（2026-11-13 に再確認）。パッケージは `Apache-2.0` | `Apache-2.0`。Graphify の NOTICE をルート `NOTICE` に転記。開発用で配布物に含めない | `NOTICE`、`LICENSES/Apache-2.0.txt` |
| Graphify 生成物 | `graphify-out/**`、`.agents/skills/graphify/.graphify_version` | first-party source から code-only モードで生成 | `AGPL-3.0-or-later` | — |
| 利用者の PDF と出力 | git 管理外 | 利用者 | リポジトリのライセンスは及ばない | — |

分類規則: 第三者の楽譜ページの画像・切り抜き、またはそのページ上の GT・座標・評価出力を含む追跡ファイルは `NotLicensed` とする。
集計値だけのファイル（例: `tools/issue522/evidence/summary.json`）、入力のハッシュ・パスだけの契約ファイルは first-party とする。
この規則に基づく点検は heuristic であり、正式適用時に対象版で再実行する（§7 の G3）。

## 4. 確定した事項と残る判断

確定（既定値。オーナーが変更しない限りこの内容で適用する）:

| 事項 | 内容 | 根拠 |
| --- | --- | --- |
| ライセンス | `AGPL-3.0-or-later`（GNU 公式 `agpl-3.0.txt` 全文、SHA-256 `0d96a4ff68ad…abcb0`） | オーナー決定 |
| 著作権表示 | `Copyright (C) 2025-<適用年> Masaki Muramatsu` | 最初の commit は 2025-09-15。オーナー以外の人間の寄与者なし（下記） |
| 文書 | コードと同じ `AGPL-3.0-or-later`。CC BY 4.0 等への分離はしない | #521 の判断を維持。分ける必要が生じたら後の版で変更できる |
| 過去 commit への遡及 | 明示しない。`LICENSE` を含む版から適用する | 公開済みの #521 commit は §2 の注意のとおり |
| HOMR 断片の SPDX | `AGPL-3.0-or-later AND AGPL-3.0-only` | 上流が only / or-later を明示しないため保守的に宣言 |
| 重み・データ・fixture | §3 の `NotLicensed` 一覧 | 権利が確認できるまで許諾しない |

寄与者の確認（2026-11-13、`develop` の author と `Co-authored-by`）:

| identity | 判断 |
| --- | --- |
| M763468 / Masaki Muramatsu | オーナー |
| `masaki.muramatsu <agent@example.com>`、`Codex Agent <agent@example.com>`、`google-labs-jules[bot]`（オーナーのメールアドレス） | オーナー環境で起動した AI エージェント |
| `Distribution test` / `Release tests`（`example.invalid`）、109 件 | 2026-10-20〜10-31 の commit。内容は #492 等のオーナー作業。テストの fixture が共有 `.git/config` に `[user]` を書き込んだ不具合（#513、修正済み）でオーナー環境の commit がこの名義になったもの。**確認済み** |
| `Co-authored-by: Claude Opus 5.5`、`github-actions[bot]` | AI エージェント / CI |

オーナー以外の人間の寄与者はいない。適用にオーナー以外の同意は不要と見込める。

残るオーナー判断・専門家確認（いずれも `LICENSE` 適用自体のブロッカーではない）:

- [ ] **適用するリリースの決定**（§7 の手順の開始）。
- [ ] **MMR 重みの扱い。** 配布物に含まれ実行に必要だが `NotLicensed` のため、正式リリースの受領者は MMR 重みの許諾を得ない。
  ImageNet 事前学習重みと楽譜由来の学習データの条件が重みに及ぶかは未確定。ライセンスを付けるか、PDFScoreBar の実行に限る許諾を付けるか、
  現状のままとするかを、配布・試用の前に判断する（§6）。barline CNN の release asset も同じ。
- [ ] GT ラベル（座標）に別ライセンスを付けるか（後日。付けるまで `NotLicensed`）。
- [ ] 外部の寄与を受け始める前に DCO / CLA を決める（別管理。first-party の別商用条件を維持するなら CLA 等が必要）。
- 専門家確認（必要に応じて）: 上記の重み・データの条件、AI エージェント生成部分の表示、公開済み #521 commit の効力。

## 5. 適用準備の状況

**非公開の適用パッケージ**（オーナーのローカル作業領域、git 管理外の `logs/issue505/`。公開リモートへ送らない）:

- 退避した #521 の 2 commit（`966ce854`、`c091ad48`）を `develop@04c16674` に再適用し、1 commit に再構成した。
- #521 からの更新: Ultralytics・OMR-DLN の記載を削除（#522 / #523）。`THIRD_PARTY_NOTICES.md` を #504 §0 の監査対象イメージ
  （`sha256:71cbccf6d7f7…`、Python 99 件）に合わせた（pypdfium2、NVIDIA / `cuda-toolkit`、HOMR 重みの上流 FAQ と学習データの注意を追加）。
  `NotLicensed` に §3 の楽譜由来の評価証拠・reviewed GT を追加。配布 manifest は 117 → 124 ファイル。
- 変更対象: `LICENSE`、`LICENSES/`（`AGPL-3.0-or-later`、`AGPL-3.0-only`、`Apache-2.0`、`LicenseRef-PDFScoreBar-NotLicensed`）、`NOTICE`、
  `THIRD_PARTY_NOTICES.md`、`REUSE.toml`、`pyproject.toml`（`license = "AGPL-3.0-or-later"`）、README（英・日）、
  `docs/MINIMAL_MAINLINE_SURFACE.json` / `.md` / `.ja.md`。

**非公開の適用リハーサル**（2026-11-13、リモートを持たない使い捨てのクローンと独立リポジトリ）:

| 検査 | 結果 |
| --- | --- |
| repository surface / 翻訳 metadata | Passed（surface 124 件、翻訳 43 ファイル） |
| `reuse lint`（パッケージ適用後のリポジトリ） | Passed（REUSE 3.3、2023 / 2023 files） |
| リリース候補の生成・検査（`tools/release_candidate.py`） | Passed（124 files。候補ツリーでも `reuse lint` Passed、120 / 120） |
| ライセンスなし昇格の後にライセンスだけを入れる候補 | Passed。差分は `LICENSE` 一式・README・`pyproject.toml`・manifest と provenance だけ |
| wheel メタデータ（`uv build --wheel`） | `License-Expression: AGPL-3.0-or-later`。`LICENSE` / `NOTICE` 同梱時は `License-File` も出る |
| targeted pytest（配布面・リリース候補・runtime 契約・翻訳・#100 surface） | 128 passed |
| runtime fingerprint | `pyproject.toml` の変更で `177fe356…` → `b3d4ae1d…` に変わる。既存イメージは再ビルドが必要 |
| Docker 再ビルド | Passed（イメージの `/workspace` に `LICENSE` / `NOTICE` / `THIRD_PARTY_NOTICES.md` が入る。editable install の dist-info に `License-File` は入らない） |
| focused smoke（`configs/smoke_test.yaml`、再ビルドしたイメージ） | Passed（preflight の fingerprint 一致、85 / 85、hard FP 0、FN 0） |

**リハーサルで確認した注意点:**

1. **`main` だけにライセンスを入れると、次の昇格で消える。** リリース候補は source commit の manifest 選択ファイルだけで作られる。
   ライセンスのない `develop` から次の候補を作ると、`LICENSE` 一式の削除を含む候補が静的検査を通過する（リハーサルで再現）。
   正式適用の直後に同じ変更を `develop` へ入れる必要がある（§7 の手順 6）。この時点では `main` で公開済みのため、早期付与にはならない。
2. **Docker イメージは build context 全体を `/workspace` に COPY する。** 開発用 checkout から作ったイメージには、`NotLicensed` の
   楽譜切り抜き・GT も入る。イメージを配布する場合は、リリース候補ツリー（124 ファイル）から build することを条件にする（§6）。

## 6. #504・#508 との境界

- **#505 は first-party の許諾**、**#504 は第三者の義務**。`LICENSE` を付けても HOMR・PyMuPDF 等の AGPL 義務、Ubuntu・NVIDIA の条件、
  第三者重みの権利は消えない。逆に第三者義務を満たしても、first-party の許諾がなければ受領者は PDFScoreBar を利用・再配布できない。
- 限定試用（#508）の方式別の前提:

| 方式 | first-party（#505）の前提 | 主な第三者・重みの条件（#504） |
| --- | --- | --- |
| (a) 利用者 PC への portable 実行物の配布 | 正式ライセンス済みの版から作る。または、その版の適用前に試用者へ個別に書面で許諾する。MMR / CNN 重みの許諾 | 同梱する全部品の LICENSE / NOTICE、HOMR・PyMuPDF の対応ソースと改変表示、Python の Metadata only 94 件・Unresolved 1 件の照合、NVIDIA 部品の再配布条件、HOMR 重みの学習データ |
| (b) Docker イメージ等の配布 | (a) と同じ。イメージはリリース候補ツリーから build し、`/workspace` に `LICENSE` 一式が入ることを確認 | (a) に加え、Ubuntu の各パッケージの通知・対応ソースと商標、CUDA ベースイメージの再配布条件 |
| (c) 時間限定のクラウド GPU・リモート提供 | 実行物を渡さないため first-party の許諾は配布ほど必須ではないが、提供する版と対応ソースの案内を固定する | 改変版 HOMR を利用者に操作させるため §13 の対応ソース提供、HOMR 重みの学習データ（Camera-PrIMuS の HF 複製は CC BY-NC 4.0）、NVIDIA・クラウドの利用条件 |

- 試用の人数が少ないことを理由に未解決の権利問題を許容しない。方式の選択と Go/No-go は #508 で行う。
- #505 の正式適用は `main` リリースに連動する。(a) / (b) を正式ライセンス済みの版で行う場合は、その版の昇格と §7 の適用が試用開始の前提になる。

## 7. 正式適用の手順と最終ゲート

前提: 適用対象のリリース（`develop` の凍結 commit `S`）を決め、OMR-DLN 除去後の内容で `main` へ昇格できる状態にする。

1. 非公開パッケージを、オーナーのローカルで `S` に適用し、ライセンス commit `L` を作る（衝突時はパッケージを内容の正本として手で合わせる）。
   適用年を著作権表示に反映する。
2. 方式を選ぶ。
   - 方式 A（推奨。オーナー方針の「main 向け focused PR」と一致）: `S` を通常どおり昇格した後、`L` を source、昇格後の `main` を parent として
     `tools/release_candidate.py create` で候補を作る。候補の差分はライセンス一式だけになる。
   - 方式 B: `L` を source に昇格候補を作り、昇格とライセンス適用を 1 回で行う。
3. 最終ゲート（対象版で実施。過去のリハーサル結果では代用しない）:
   - G1 `python3 tools/check_repository_surface.py`、`python3 tools/verification/check_doc_translations.py`、`git diff --check`
   - G2 `uvx reuse lint`（ソースと候補ツリーの両方）
   - G3 楽譜由来ファイルの点検（パッケージ同梱の点検スクリプト）。新しい hit は §3 の規則で分類
   - G4 `LICENSE` を GNU 公式 `agpl-3.0.txt` と SHA-256 照合
   - G5 `tools/release_candidate.py check`、候補に `LICENSE` / `NOTICE` / `THIRD_PARTY_NOTICES.md` / `REUSE.toml` / `LICENSES/` があること
   - G6 `THIRD_PARTY_NOTICES.md` が対象版の依存・イメージ（#504 の再採取）と一致すること
   - G7 wheel の `License-Expression`、runtime fingerprint の変化の記録、Docker 再ビルドと focused smoke
   - G8 Git 依存の pytest（`docs/dev/LOCAL_VALIDATION.md` の使い捨てコンテナ）
4. ライセンスを含む候補ブランチを push し、`main` 向け PR を作る。**push と PR の作成が許諾の公開になる**ため、オーナーの明示的な承認後に行う。
5. オーナーがマージする。
6. **直後に `L` と同じ変更を `develop` へ入れる PR を作る**（注意点 1）。以後の昇格 PR では `LICENSE` 一式の削除がないことを確認する。
7. #505 と本文書を「適用済み」に更新する。

最終リリース対象に依存する検証（対象 commit との fingerprint 一致、最終イメージ内の通知、第三者部品の版）は、その時点で再実施する。

## 8. 履歴: 2026-11-07 のライセンス比較（取り下げ済みの推奨を含む）

以下は初版の比較の要約で、**現在の方針ではない**。Apache-2.0 の推奨は 2026-11-08 のオーナー決定で置き換えた。

| 選択肢 | 他者に許すこと | 当時の評価 |
| --- | --- | --- |
| LICENSE なし（現状） | GitHub 上の閲覧・fork のみ | 結合物の (b)(c) 提供ができない |
| MIT | 改変・再配布・商用を広く許可 | 最も簡潔。特許許諾の明示なし。改変版の非公開 SaaS も認める |
| Apache-2.0（当時の推奨候補） | MIT と同等に広い。特許許諾、NOTICE 保持 | AGPL 依存を減らした部分を緩い条件で再利用できる。改変版の非公開 SaaS も認める |
| **AGPL-3.0-or-later（採用）** | 改変版をネットワーク提供する者にも対応ソースの提供を要求 | 改変版の囲い込みを防げる。first-party 部分の再利用の敷居は残る |
| GPL-3.0-or-later、MPL-2.0、領域別の複数ライセンス | — | 利点が少ない、または境界管理の手間が大きい |

当時の判断軸は「第三者が改変版を非公開のまま商用製品・SaaS に使うことを認めるか」と「AGPL 依存を減らした部分を緩い条件で再利用したいか」だった。
オーナーは前者を認めない方針を選んだ。MIT、Apache-2.0、GPL-3.0、AGPL-3.0 はいずれも HOMR・PyMuPDF の AGPL と互換で、
どれを選んでも結合した runtime を渡す・提供するときの AGPL 遵守義務は残る。
