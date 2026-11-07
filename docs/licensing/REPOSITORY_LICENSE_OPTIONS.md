# リポジトリ自身のライセンスと著作権境界（#505 検討）

[#505](https://github.com/M763468/PDFScoreBar/issues/505) の検討記録。原文は日本語（正本）。英語版は未作成。
第三者部品の義務は [第三者ライセンス監査（#504）](THIRD_PARTY_LICENSE_AUDIT.md) を入力とし、ここでは重複しない。

> **本文書は提案であり、ライセンスはまだ決定していない。** 最終選択はリポジトリオーナーの明示的な決定とする。
> 法的助言ではない。

## 1. 現状（2026-11-07、`develop@3f7c8a632c6b`）

- ルートに `LICENSE` / `NOTICE` / `COPYING` がない。`pyproject.toml` に `license` 欄がない。SPDX 表示もない。
- リポジトリは GitHub で公開されている。公開されていることだけでは、利用・改変・再配布の一般的許諾にはならない
  （GitHub 利用規約に基づく GitHub 上での閲覧・fork を除く）。
- #504 のとおり、配布・クラウド提供する runtime は AGPL-3.0 部品と結合しているため、**LICENSE がない状態では (b) / (c) の提供ができない**。

## 2. 権利台帳の骨子

| 区分 | 範囲 | 所有者・取得経路 | ライセンス付与の扱い（案） |
| --- | --- | --- | --- |
| first-party コード | `src/`、`tools/`、`docker/`、`scripts/`、`tests/`（fixture 除く）、`experiments/`、`Makefile`、`Dockerfile*`、`configs/` | リポジトリオーナー。§3 の寄与者確認を参照 | 選択したライセンスで許諾 |
| first-party 文書 | `docs/`、`README*`、`AGENTS.md`、`.github/` テンプレート | 同上 | コードと同じライセンス（文書だけ CC BY 4.0 にする選択肢もある） |
| GUI 資産 | `tools/review_correction/*.html` / `*.js` 等 | first-party。外部ライブラリ・CDN を含まない | コードと同じ |
| 第三者コード片 | `docker/patch_homr_onnx_provider.py` 内の、置換対象として引用した HOMR のソース断片（数行） | HOMR 作者（AGPL-3.0） | 再許諾しない。断片は AGPL-3.0 の下にあると注記する |
| 第三者コード（未同梱） | HOMR、Ultralytics、PyMuPDF、Real-ESRGAN 等は build 時に取得。`external/` は #382 で廃止済み | 各上流 | 対象外。`THIRD_PARTY_NOTICES` で案内 |
| first-party 重み | `models/mmr/mmr_classifier_best.pth`（git 管理）、barline CNN（本リポジトリの GitHub release、manifest のみ git 管理） | オーナーが学習。MMR は torchvision の ImageNet 事前学習重みから初期化。学習データは楽譜由来 | **コードと分けて決める**。§4 参照 |
| 第三者重み | HOMR、OMR-DLN、Real-ESRGAN、RapidOCR | 各上流（#504 §3） | 対象外。git には manifest と SHA-256 のみ |
| 評価・学習データ | `data/evaluation2/annotations/**`（座標 JSON、git 管理）。楽譜画像・PDF は git 管理外 | ラベルは first-party。元の楽譜は第三者著作物（保護期間内の作品を含む） | ラベルは許諾対象にできるが、楽譜画像・PDF は含めない |
| テスト fixture 画像 | `tests/fixtures/system_grouping/*.png`（#218 で追加） | 出典記録なし | **出典確認まで許諾対象から除外**（または出典確認後に判断） |
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

## 5. 推奨候補（未採択。オーナー決定待ち）

**Apache-2.0 は推奨候補であり、採択済みではない。** 決定前に次の二点を判断する。

1. **第三者が first-party コードを改変し、非公開のまま商用製品や SaaS に使うことを認めるか。**
   Apache-2.0 / MIT は認める。AGPL-3.0-or-later はネットワーク提供を含めて改変ソースの公開を求める。
2. **将来、AGPL 依存を減らした部分を緩い条件で再利用できるようにしたいか。**
   Apache-2.0 / MIT ならそのまま再利用できる。AGPL-3.0-or-later では first-party 部分にも AGPL の条件が残る。

どれを選んでも、**HOMR・PyMuPDF・Ultralytics と結合した runtime を渡す・提供するときの AGPL 遵守義務は消えない**（#504 §5）。
#504 の方針では HOMR / PyMuPDF は遵守を前提に原則維持するため、runtime 全体はしばらく AGPL の条件で提供することになる。
また、一度 Apache-2.0 / MIT で公開した版の許諾は取り消せない。後の版から別ライセンスに変えることはできる。

| 候補 | 向いている判断 | 要点 |
| --- | --- | --- |
| **Apache-2.0**（推奨候補） | 1 = 認める、2 = したい | 特許許諾と特許報復条項、改変の明示と NOTICE 保持。外部寄与を受けるときも扱いが明確 |
| MIT | 1 = 認める、2 = したい。手続きを最小にしたい | 最も簡潔。特許許諾の明示がない |
| AGPL-3.0-or-later | 1 = 認めない | 改変版の閉じた SaaS 利用を防げる。依存を減らしても first-party の再利用の敷居は残る |

推奨候補の内容:

1. **first-party コード・文書・GUI 資産に Apache-2.0 を付与する。**
   理由: AGPL 部品と互換で (b)(c) の遵守策を満たせる。AGPL 部品を置き換えた部分は緩い条件のまま再利用できる。
   特許許諾条項があり、外部寄与を受けるときも扱いが明確。
2. **第三者のコード・重みは再許諾しない。** `NOTICE` と `THIRD_PARTY_NOTICES` で、配布する runtime 結合物が AGPL-3.0 部品を含み、
   その条件で提供されることを明記する。
3. **first-party 重みは今回の付与対象から外す**（「別途定める」と明記）。ImageNet 初期化と楽譜由来の学習データの条件を確認したうえで、
   後日 Apache-2.0 等を付けるか決める。配布 runtime に含まれる MMR 分類器は、それまで「PDFScoreBar の実行目的に限り利用可」等の限定条件を
   付けるかもオーナー決定事項。
4. **データと fixture 画像は除外する。** `data/evaluation2/annotations/**` は CC BY 4.0 等を後日検討。`tests/fixtures/**/*.png` は出典確認まで除外。

## 6. 反映計画（承認後の focused PR）

| 項目 | 内容 |
| --- | --- |
| `LICENSE` | 選択したライセンスの全文（Apache-2.0 の場合は公式全文） |
| `NOTICE` | `Copyright 2026 Masaki Muramatsu`（年・表記はオーナー確認）、第三者部品と AGPL 結合の注記、除外範囲（重み・データ・fixture） |
| `THIRD_PARTY_NOTICES.md` | #504 §2・§3 の台帳から作成。部品、版、ライセンス、取得元、改変の有無（HOMR、BasicSR） |
| `pyproject.toml` | `license = "Apache-2.0"` と `license-files = ["LICENSE", "NOTICE"]`（PEP 639） |
| README（英・日） | ライセンス節: first-party の条件、第三者部品と AGPL の関係、除外範囲 |
| SPDX | 全ファイルへの header 一括追加は行わず、`REUSE.toml` で path 単位に宣言する（第三者断片を含む `docker/patch_homr_onnx_provider.py`、除外する重み・データ・fixture を明示）。新規ファイルの header は任意 |
| 配布 manifest | `LICENSE`、`NOTICE`、`THIRD_PARTY_NOTICES.md` を `docs/MINIMAL_MAINLINE_SURFACE.json` の配布 metadata に追加。配布選択の変更として、同 PR で surface 検査と関連テストを実施 |
| 版管理 | 付与 commit 以降の版に適用すると明記する。過去 commit へ遡及適用するかはオーナー決定 |

`main` への反映は通常の `develop → main` 昇格 PR で行い、自動昇格しない。

## 7. オーナー決定・専門家確認が必要な事項

オーナー決定:

- [ ] first-party コードのライセンス（推奨候補 Apache-2.0。ほかに MIT、AGPL-3.0-or-later。§5 の二つの判断による）
- [ ] 文書を同一ライセンスにするか、CC BY 4.0 にするか
- [ ] first-party 重み（MMR、barline CNN）の扱い
- [ ] GT ラベルと fixture 画像の扱い
- [ ] 著作権表示の名義と年
- [ ] 過去 commit への遡及の有無
- [ ] 外部寄与を受ける場合の DCO / CLA
- [ ] `Distribution test` / `Release tests` identity の commit がオーナー環境で作成されたものであることの確認

専門家確認（必要に応じて）:

- ImageNet 事前学習重みから初期化した重み、および保護期間内の楽譜から作った学習・評価データについて、重みやラベルへ条件が及ぶか。
- AI エージェントが生成したコード部分の著作権表示の書き方。

## 8. #504 から受け取る事項

確定: 結合物の提供に AGPL 互換の first-party ライセンスが必要であること、第三者部品を再許諾できないこと、HOMR・BasicSR に改変があること。
未確定: OMR-DLN と HOMR の重みの条件、別プロセス・別リポジトリの結合関係、(c) での §13 の範囲。
これらは本リポジトリのライセンス選択を左右しないが、`NOTICE` と提供手順の記述に反映する。
[#519](https://github.com/M763468/PDFScoreBar/issues/519) の OMR-DLN 代替検証の結果も、ライセンス選択の前提にはしない。
