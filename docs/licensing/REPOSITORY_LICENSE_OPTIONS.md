# リポジトリ自身のライセンスと著作権境界（#505 検討）

[#505](https://github.com/M763468/PDFScoreBar/issues/505) の検討記録。原文は日本語（正本）。英語版は未作成。
第三者部品の義務は [第三者ライセンス監査（#504）](THIRD_PARTY_LICENSE_AUDIT.md) を入力とし、ここでは重複しない。

> **決定（2026-11-08）: first-party コードに `AGPL-3.0-or-later` を採用する。** リポジトリオーナーの明示的な指示により、
> #505 専用の focused PR で `LICENSE` 等を追加した（§5、§6）。2026-11-07 時点の Apache-2.0 推奨候補は §5.3 に履歴として残す。
> 法的助言ではない。

## 1. 現状

**採用後（2026-11-08、#505 の PR）:** ルートに `LICENSE`（GNU 公式の AGPL-3.0 全文）、`NOTICE`、`THIRD_PARTY_NOTICES.md`、
`REUSE.toml`、`LICENSES/` を追加し、`pyproject.toml` に `license = "AGPL-3.0-or-later"` を宣言した。以下は採用前の記録。

**採用前（2026-11-07、`develop@3f7c8a632c6b`）:**

- ルートに `LICENSE` / `NOTICE` / `COPYING` がない。`pyproject.toml` に `license` 欄がない。SPDX 表示もない。
- リポジトリは GitHub で公開されている。公開されていることだけでは、利用・改変・再配布の一般的許諾にはならない
  （GitHub 利用規約に基づく GitHub 上での閲覧・fork を除く）。
- #504 のとおり、配布・クラウド提供する runtime は AGPL-3.0 部品と結合しているため、**LICENSE がない状態では (b) / (c) の提供ができない**。

## 2. 権利台帳の骨子

| 区分 | 範囲 | 所有者・取得経路 | ライセンス付与の扱い（決定） |
| --- | --- | --- | --- |
| first-party コード | `src/`、`tools/`、`docker/`、`scripts/`、`tests/`（fixture 除く）、`experiments/`、`Makefile`、`Dockerfile*`、`configs/` | リポジトリオーナー。§3 の寄与者確認を参照 | **AGPL-3.0-or-later** |
| first-party 文書 | `docs/`、`README*`、`AGENTS.md`、`.github/` テンプレート | 同上 | **AGPL-3.0-or-later**（文書だけ CC BY 4.0 にする選択肢は §7 で確認） |
| GUI 資産 | `tools/review_correction/*.html` / `*.js` 等 | first-party。外部ライブラリ・CDN を含まない | **AGPL-3.0-or-later** |
| 第三者コード片 | `docker/patch_homr_onnx_provider.py` 内の、置換対象として引用した HOMR のソース断片（数行） | HOMR 作者（AGPL-3.0。上流 `pyproject.toml` は `license = "AGPL-3.0"` で only / or-later を明示しない） | 再許諾しない。`REUSE.toml` で `AGPL-3.0-or-later AND AGPL-3.0-only`（断片を保守的に only と扱う）、著作権者に HOMR authors を併記 |
| 第三者コード（未同梱） | HOMR、Ultralytics、PyMuPDF、Real-ESRGAN 等は build 時に取得。`external/` は #382 で廃止済み | 各上流 | 対象外。`THIRD_PARTY_NOTICES` で案内 |
| first-party 重み | `models/mmr/mmr_classifier_best.pth`（git 管理）、barline CNN（本リポジトリの GitHub release、manifest のみ git 管理） | オーナーが学習。MMR は torchvision の ImageNet 事前学習重みから初期化。学習データは楽譜由来 | **除外**（MMR は `LicenseRef-PDFScoreBar-NotLicensed`、CNN は git 管理外）。別途定める |
| 第三者重み | HOMR、OMR-DLN、Real-ESRGAN、RapidOCR | 各上流（#504 §3） | 対象外。git には manifest と SHA-256 のみ |
| 評価・学習データ | `data/evaluation2/**`（GT 座標 JSON、golden baseline 出力、`staff_units.json`。git 管理）。楽譜画像・PDF は git 管理外 | ラベルは first-party。元の楽譜は第三者著作物（保護期間内の作品を含む） | **除外**（`LicenseRef-PDFScoreBar-NotLicensed`）。ラベルへの許諾は後日判断。楽譜画像・PDF は含めない |
| テスト fixture（合成） | `tests/fixtures/system_grouping/issue218_3div*` / `issue218_4div*`（PNG と JSON、#218） | first-party。同ディレクトリの `README.md` が合成と記載し、`generate_issue218.py` で 8 ファイルすべてを byte 一致で再生成できた（2026-11-08 確認）。#504 監査の「出典記録なし」はこの確認で訂正する | **AGPL-3.0-or-later** |
| テスト fixture（楽譜由来） | `tests/fixtures/expected_overrides_page_*.json`、`tests/fixtures/movement_boundaries/**`、`tests/fixtures/system_grouping/issue218_{la_mer,measure_gt,real_detection,real_score}.json` | 第三者の楽譜（IMSLP 等）から作った座標・期待値 | **除外**（`LicenseRef-PDFScoreBar-NotLicensed`） |
| 実験の評価データ | `experiments/issue333/corpus.json`、`phase25_ground_truth.json`、`results/**`、`configs/cnn_barline_runs/issue44_baseline_v1/fixtures/**` | 第三者の楽譜に対するコーパス・GT・評価出力 | **除外** |
| Graphify 参照資料（第三者） | `.agents/skills/graphify/references/**`（8 ファイル） | 第三者。導入済み `graphifyy 0.9.41`（[Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)）の `graphify/skills/*/references/` と byte 一致（2026-11-08 確認）。パッケージメタデータは `License-Expression: Apache-2.0`。NOTICE は MIT 時代の寄与部分が MIT でも利用可能と記載 | 再許諾しない。`Apache-2.0`（`LICENSES/Apache-2.0.txt`）、Graphify の NOTICE をルート `NOTICE` に転記 |
| Graphify 生成物 | `graphify-out/**`、`.agents/skills/graphify/.graphify_version` | first-party 由来の生成物。Graphify 0.9.41 の code-only モード（semantic / LLM 経路なし）で first-party の source（`3ff2800b`）から生成。node の参照元は first-party のコードと model manifest のみで、除外データや Graphify 参照資料を含まない。`.graphify_version` は installer の版 stamp | **AGPL-3.0-or-later**（`REUSE.toml` で来歴を明記） |
| Graphify skill 本体 | `.agents/skills/graphify/SKILL.md`、`.agents/workflows/graphify.md` | first-party。パッケージ同梱のファイルと一致せず、本リポジトリ固有の運用を記述 | **AGPL-3.0-or-later** |
| 利用者が提供する PDF と出力 | git 管理外 | 利用者 | リポジトリのライセンスは及ばない。利用者の権利のまま |

## 3. 寄与者の確認

`git log` の author と `Co-authored-by` trailer を確認した（2026-11-07）。

| identity | 件数（author） | 判断 |
| --- | --- | --- |
| M763468 / Masaki Muramatsu（複数のメールアドレス） | 807 | オーナー |
| `masaki.muramatsu <agent@example.com>`、`Codex Agent <agent@example.com>` | 614 | オーナー環境の AI エージェント |
| `google-labs-jules[bot]` | 11 | オーナーが起動した AI エージェント |
| `Distribution test` / `Release tests`（`example.invalid`） | 109 | テストが作業リポジトリへ commit したテスト用 identity と考えられる（オーナー環境で作成）。**オーナー確認事項** |
| `Co-authored-by: Claude Opus 5.5`、`github-actions[bot]` | trailer のみ | AI エージェント / CI |

オーナー以外の人間の寄与者は見つからなかった。したがって**ライセンス付与・将来の変更にオーナー以外の同意は不要**と見込める。
AI 生成部分の著作物性は法域により扱いが異なるが、第三者が権利を主張する構造ではない。
今後外部の寄与を受ける場合は、DCO（`Signed-off-by`）か CLA を事前に決めておくと、再ライセンスの柔軟性を保てる。

## 4. ライセンス選択肢の比較

前提（#504 から）: 結合した runtime を渡す・(c) で提供するときは、first-party コードが AGPL-3.0 と互換であればよい。
MIT、Apache-2.0、GPL-3.0、AGPL-3.0 はすべて互換。いずれを選んでも、**現時点で配布する結合物全体は AGPL-3.0 の条件で受領者に渡ることになる**。

| 選択肢 | 他者に許すこと | AGPL 部品との互換 | 配布・クラウド提供への影響 | 長所 | 短所 |
| --- | --- | --- | --- | --- | --- |
| LICENSE なし（現状維持） | GitHub 上の閲覧・fork のみ | **不可**（受領者に追加制限を課す） | (b)(c) の提供ができない | なし | #504 の遵守策が満たせない |
| MIT | 改変・再配布・商用を広く許可。著作権表示のみ要求 | 互換 | 結合物は AGPL として渡す。first-party 部分は単独でも再利用可能 | 最も単純 | 特許許諾の明示なし。SaaS 化された改変の source 公開は求められない |
| **Apache-2.0** | MIT と同等に広い。改変の明示、NOTICE 保持、特許許諾と特許報復条項 | 互換（GPLv3 / AGPLv3 と互換） | 同上 | 特許条項。将来 AGPL 部品を置き換えた部分は、そのまま緩い条件で再利用できる | MIT より手続き（NOTICE、改変の明示）が少し多い |
| AGPL-3.0-or-later | 改変版をネットワーク提供する者にも source 提供を要求 | 同一 | 現在の結合物の条件と一致し、説明が単純 | 他者が改変して閉じた SaaS にすることを防げる | #504 で AGPL 部品を置換しても first-party 部分の負担は残る。再利用の敷居が高い |
| GPL-3.0-or-later | 配布時の source 提供を要求（ネットワーク条項なし） | 互換（GPLv3 §13 / AGPLv3 §13） | 結合物は AGPL の条件になる | — | 中間的で、現状の AGPL 結合とも将来の緩い条件とも合わず利点が少ない |
| MPL-2.0 | ファイル単位のコピーレフト | 互換（GPL 系との併用条項） | 同上 | 改変ファイルの公開を求めつつ結合は自由 | 運用が分かりにくい |
| 領域別の複数ライセンス | 例: engine は AGPL、補正 GUI・ランチャー・将来の Web 入口は Apache-2.0 | 各領域で互換 | 領域境界が明確なら柔軟 | 将来の別リポジトリ Web 入口と整合しやすい | 境界管理・SPDX 管理の手間。#504 の結合関係が未確定な領域に適用すると誤解を招く |

engine と将来の control-plane（#449、別リポジトリ想定）は同じライセンスである必要はない。
control-plane が engine の AGPL 部品と結合しない（ジョブ投入とデータ受け渡しのみ）設計であれば独自に選べるが、その判断は #504 §4 の未確定事項に依存する。

## 5. 決定: AGPL-3.0-or-later

### 5.1 採用理由（オーナー意向、#505 の 2026-11-07 / 2026-11-08 のコメントと 2026-11-08 の実装指示）

- 他者による PDFScoreBar の利用・改変・商用サービス提供そのものは認める。
- ただし、改良部分を非公開のまま囲い込んだ商用サービス化には抵抗がある。改変版の利用者が改良したソースを入手でき、
  オーナーも条件を守って再利用・取り込みを検討できるオープンソースの循環を重視する。
- オーナー自身も将来 PDFScoreBar をサービス化・収益化したい。

Apache-2.0 / MIT は第三者による非公開の改変・SaaS 利用を広く認めるため、上記の優先事項と合わない。
BSL 等の競合サービス禁止型はオープンソースではなく、現行の AGPL 依存との整合も複雑になるため採らない。
GPL-3.0 はネットワーク提供時の source 提供を求めないため、上記の目的を満たさない。

### 5.2 AGPL-3.0-or-later で言えること・言えないこと

- **商用利用や第三者のサービス提供を禁止しない。** 誰でも利用・改変・販売・ホスティングできる。
- **§13 のネットワーク利用者への source 提供は、プログラムを改変した版をネットワーク越しに操作させる場合に関わる。**
  未改変版を単にホスティングする場合まで、新たな開示義務が必ず生じるわけではない。複製物を渡す（convey する）場合は、
  改変の有無にかかわらず §4〜§6 の条件（ライセンス文の同梱、対応ソースの提供等）に従う。
- **提供先はその複製物の受領者、またはそのサービスのネットワーク利用者である。** 公開 GitHub への掲載、オーナーへの報告、
  upstream への PR 提出は義務ではない。独立した別プログラムや周辺事業のコード全体が自動的に開示対象になるわけでもない。
- AGPL で提供された他者の改良は、著作権表示とライセンス条件を守ればオーナーも取り込める可能性がある。ただし、提供者が
  オーナーへ改良を還元する義務はない。
- **オーナーは自分が権利を持つ first-party コードについて、AGPL とは別の商用条件を提示できる**（デュアルライセンス）。
  ただし HOMR / PyMuPDF / Ultralytics 等の第三者 AGPL 部品の許諾を代行することはできず、それらを含む runtime を提供する限り
  その部品の AGPL 義務（または各社の商用ライセンス）は残る。外部寄与を取り込むと、その部分の権利は寄与者に残るため、
  別条件での提供には寄与者の許諾が要る（§7 の DCO / CLA）。
- 一度 AGPL-3.0-or-later で公開した版の許諾は取り消せない。後の版から条件を変えることはできる。
- `-or-later` により、受領者は FSF が将来公表する AGPL の後継版の条件も選べる。

公式根拠: [GNU AGPL v3](https://www.gnu.org/licenses/agpl-3.0.html)（§13）、
[GPL FAQ](https://www.gnu.org/licenses/gpl-faq.html)（AGPL のネットワーク利用・ソース提供対象）。

### 5.3 履歴: 2026-11-07 時点の推奨候補（不採用）

2026-11-07 版の本文書は Apache-2.0 を推奨候補（未採択）としていた。判断の分かれ目は
「第三者が first-party コードを改変し、非公開のまま商用製品や SaaS に使うことを認めるか」であり、オーナーは
2026-11-08 に「認めない（改変ソースの提供を重視する）」側を選んだ。§4 の比較表はその判断の入力として残す。

### 5.4 適用範囲

1. **first-party のコード・スクリプト・設定・テスト・補正 GUI・文書に AGPL-3.0-or-later を付与する。**
   文書を CC BY 4.0 等に分ける選択はとらず、同一ライセンスとした（変更する場合は後続 PR、§7）。
2. **第三者のコード・重み・データは再許諾しない。** `NOTICE` と `THIRD_PARTY_NOTICES.md` で、runtime が AGPL-3.0 部品を含むことと、
   HOMR / BasicSR の改変を明記する。
3. **権利が未確定のものは AGPL の対象外**とし、`LicenseRef-PDFScoreBar-NotLicensed`（`LICENSES/` に説明文）で区別する:
   first-party の MMR 重み、`data/evaluation2/**`、楽譜由来の fixture と実験データ（§2）。
   Graphify の参照資料は第三者の Apache-2.0 として区別し、Graphify 生成物は first-party として扱う。Graphify 関連はいずれも
   開発用で、実行用配布物には含めない（本 PR で Graphify のファイルと配布 manifest の Graphify 分類は変更していない）。
   barline CNN 重みは git 管理外の release asset で、同じく別途定める。
4. 楽譜画像・PDF、利用者の入力 PDF と出力はリポジトリに含まれず、ライセンスは及ばない。

## 6. 反映内容（#505 の focused PR）

| 項目 | 内容 |
| --- | --- |
| `LICENSE` | GNU 公式 `https://www.gnu.org/licenses/agpl-3.0.txt` の全文（2026-11-08 取得、SHA-256 `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`） |
| `NOTICE` | `Copyright (C) 2025-2026 Masaki Muramatsu`（最初の commit 2025-09-15、git の作者名。§7 で確認）、GNU 推奨の許諾文、適用範囲、除外一覧、第三者部品と AGPL 結合の注記 |
| `THIRD_PARTY_NOTICES.md` | #504 §2・§3 の台帳から作成。部品、版、ライセンス、取得元、HOMR / BasicSR の改変内容と日付、第三者重みの状態 |
| `pyproject.toml` | `license = "AGPL-3.0-or-later"`（PEP 639）。`LICENSE` / `NOTICE` は setuptools の既定 glob で wheel に入る。`license-files` は指定しない（Docker builder は `pyproject.toml` だけを copy して `uv pip install -e .` するため） |
| README（英・日） | ライセンス節: first-party の条件、AGPL の義務の範囲、第三者部品、除外範囲 |
| SPDX / REUSE | `REUSE.toml` で path 単位に宣言（全体は `AGPL-3.0-or-later`、HOMR 断片を含む patch script、Graphify の参照資料と生成物、除外対象を override）。`LICENSES/` に `AGPL-3.0-or-later.txt`、`AGPL-3.0-only.txt`、`Apache-2.0.txt`（Graphify 参照資料用。開発用のため配布 manifest には入れない）、`LicenseRef-PDFScoreBar-NotLicensed.txt`。各ファイルへの header 追加はしない（`docker/patch_homr_onnx_provider.py` は runtime fingerprint の対象でもある） |
| 配布 manifest | `LICENSE`、`NOTICE`、`THIRD_PARTY_NOTICES.md`、`REUSE.toml`、`LICENSES/*.txt` の 7 ファイルを `distribution_metadata_patterns` に追加（121 → 128 ファイル） |
| 版管理 | `LICENSE` を含む版から適用する。それ以前の commit への遡及は明示しない（§7） |

**runtime 互換性への影響:** `pyproject.toml` は `docker/runtime_contract.py` の `RUNTIME_CONTRACT_FILES` に含まれるため、
本変更で runtime fingerprint が変わる。既存イメージは preflight の互換性検査で不一致となり、再ビルドが必要になる
（依存関係・実行コードは変わらない）。

`main` への反映は通常の `develop → main` 昇格 PR で行い、自動昇格しない。

## 7. オーナー決定・専門家確認が必要な事項

決定済み:

- [x] first-party コードのライセンス: **AGPL-3.0-or-later**（2026-11-08）

PR 上で確認を求める事項（本 PR では推測で確定せず、上記の暫定値で実装した）:

- [ ] `Distribution test` / `Release tests`（`example.invalid`）identity の commit がオーナー環境のテストで作られたものであること
  （§3。本 PR はオーナー以外の人間の寄与者がいないという §3 の確認結果を前提に実装した）
- [ ] 著作権表示の名義と年（暫定: `Masaki Muramatsu`、`2025-2026`）
- [ ] 文書も同一ライセンスでよいか（暫定: 同一。CC BY 4.0 に分ける選択肢あり）
- [ ] HOMR 断片の SPDX 表記（暫定: `AGPL-3.0-only` として保守的に扱う）
- [ ] 過去 commit への遡及の有無（暫定: 明示しない。`LICENSE` を含む版から適用）
- [ ] first-party 重み（MMR、barline CNN）の扱い
- [ ] GT ラベル、楽譜由来 fixture、実験データの扱い
- [ ] 外部寄与を受ける場合の DCO / CLA（デュアルライセンスを維持するなら CLA 等で別条件の許諾を得る必要がある）
- [ ] (c) で提供するときの「Source」リンク（#449 / #508 で実装）

専門家確認（必要に応じて）:

- ImageNet 事前学習重みから初期化した重み、および保護期間内の楽譜から作った学習・評価データについて、重みやラベルへ条件が及ぶか。
- AI エージェントが生成したコード部分の著作権表示の書き方。
- first-party コードの商用ライセンスを別途提示する場合の条件設計。

## 8. #504 から受け取る事項

確定: 結合物の提供に AGPL 互換の first-party ライセンスが必要であること、第三者部品を再許諾できないこと、HOMR・BasicSR に改変があること。
未確定: OMR-DLN と HOMR の重みの条件、別プロセス・別リポジトリの結合関係、(c) での §13 の範囲。
これらは本リポジトリのライセンス選択を左右しないが、`NOTICE` と提供手順の記述に反映する。
[#519](https://github.com/M763468/PDFScoreBar/issues/519) の OMR-DLN 代替検証の結果も、ライセンス選択の前提にはしない。
