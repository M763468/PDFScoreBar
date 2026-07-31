---
trigger: always_on
description: Consult the local Graphify knowledge graph for codebase and architecture questions.
---

## Graphify利用ガイド

このリポジトリではコードベースのナレッジグラフ化ツール `Graphify` (CLI: `graphify`) を利用できます。

**利用ルール**:
- **事前絞り込み**: リポジトリ全体を広範囲に検索する前に、既存グラフへ `graphify query "<question>"` などで問い合わせ、関連領域を絞り込む。
- **ローカル完結を既定とする**: グラフの新規生成・全面再生成は `graphify extract . --code-only --force` を使用する。コードはローカルAST解析され、ドキュメント・PDF・画像は対象外となる。
- **外部送信の禁止**: 明示的な承認と承認済みのローカルバックエンドがない限り、ドキュメント・PDF・画像を含むsemantic extractionや外部APIバックエンドを使用しない。
- **直接確認**: Graphifyの結果だけで実装を判断せず、対象ソースを直接確認する。
- **裏付け**: Graphifyにより推定された依存関係は、実際の実装またはテストコードで裏付ける。
- **フォールバック**: Graphifyが失敗した場合や十分な情報が得られない場合は、通常の検索（`rg` / `grep` 等）やソース確認へ速やかにフォールバックする。
- **過剰利用の禁止**: Graphifyを使うこと自体を目的化せず、単純な変更や調査では過剰な問い合わせをしない。
- **ドキュメントのナビゲーション**: コードグラフを補完するドキュメント一覧として `graphify-out/wiki/index.md` を参照する。
- **更新**: 既存のコード専用グラフは `graphify update .` で増分更新する。大規模な構造変更後や整合性に疑いがある場合は、上記のcode-only全面再生成を行う。
