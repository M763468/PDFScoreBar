---
trigger: always_on
description: Use the committed Graphify graph before broad searches for codebase structure, dependencies, call paths, and relevant files.
---

## Graphify利用ガイド

- **共有グラフを優先する**: `graphify-out/graph.json` が存在する場合、構造・依存関係・call path・関連ファイルの調査では広範な検索より先にGraphifyへ問い合わせる。
- **入口を統一する**: 新規worktreeを含め、通常は `scripts/graphify_query.sh "<question>"` を使う。Agent Skillとしては `.agents/skills/graphify/SKILL.md` を利用する。
- **code-onlyを既定とする**: 無人の生成・再生成はローカルASTによるcode-onlyとし、document・PDF・imageのsemantic extractionを自動実行しない。
- **document semanticsは明示選択制**: ユーザーがローカルcoding sessionまたはGemini API経路を明示的に選び、対象pathを限定した場合だけ実行する。
- **共有する成果物を限定する**: `graph.json`、`GRAPH_REPORT.md`、`wiki/**`、`MANIFEST.json`だけを共有し、抽出cache・途中JSON・HTML・local path情報はコミットしない。
- **直接確認する**: Graphifyの結果だけで実装を判断せず、対象sourceまたはtestで裏付ける。
- **古さを考慮する**: branch固有の変更は共有グラフに未反映の場合がある。該当差分を直接確認し、必要な場合だけlocal refreshを行う。
- **フォールバックする**: Graphifyが失敗した場合や情報が不十分な場合は、`rg` / `grep` とsource確認へ速やかに切り替える。
