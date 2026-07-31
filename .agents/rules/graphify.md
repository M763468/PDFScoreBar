---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ for codebase and architecture questions.
---

## Graphify利用ガイド

このリポジトリではコードベースのナレッジグラフ化ツール `Graphify` (CLI: `graphify`) を利用できます。

**利用ルール**:
- **事前絞り込み**: リポジトリ全体を広範囲に検索する前に、`graphify query "<question>"` などで関連領域を絞り込む。
- **直接確認**: Graphifyの結果だけで実装を判断せず、対象ソースを直接確認する。
- **裏付け**: Graphifyにより推定された依存関係は、実際の実装またはテストコードで裏付ける。
- **フォールバック**: Graphifyが失敗した場合や十分な情報が得られない場合は、通常の検索（grep等）やソース確認へ速やかにフォールバックする。
- **過剰利用の禁止**: Graphifyを使うこと自体を目的化せず、単純な変更や調査では過剰な問い合わせをしない。
- **ドキュメントのナビゲーション**: Graphifyのコードグラフを補完するため、ドキュメントの全体像を把握する場合は `graphify-out/wiki/index.md` を参照してください。
- **グラフの更新と再生成**:
  - コード修正後や大きな構造変更後には `graphify update .` でグラフを更新する。
  - グラフが古い可能性がある場合は再生成（`graphify .`）する。
