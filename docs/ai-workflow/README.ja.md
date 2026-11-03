# AIエージェントのワークフロー文書

<!-- translation: {"original":"README.md","source":{"sha256":"478ca28f6f2dc8f2e8636f723059cba2d8c32cc78260bf16f716058c63bae366"},"state":"reviewed"} -->

[English / 原文](README.md)（英語正本）

翻訳元: same PR / SHA-256 `478ca28f6f2dc8f2e8636f723059cba2d8c32cc78260bf16f716058c63bae366`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

このディレクトリには、PDFScoreBar で AI を活用した開発を行うための任意のガイドがあります。リポジトリで有効な指示の正本はルートの `AGENTS.md` です。

## 有効なガイド

- [一般的なワークフロー](WORKFLOW.ja.md): タスク → ブランチ → 検証 → PR の軽量な流れ。
- [Graphify](GRAPHIFY.ja.md): 複雑なモジュール横断の質問のための任意のナビゲーション。
- [Codex と Gemini への相談メモ](CODEX_GEMINI_COLLAB.ja.md): 任意のセカンドオピニオンのガイド。
- [検証方針](../dev/VALIDATION_POLICY.ja.md): リスクに応じた検証と、評価契約の規則。
- [ラベル辞書](LABELS.ja.md): GitHub のラベルの定義。
- [プロンプト集](PROMPTS.md): 任意のプロンプトの断片（日本語）。
- [教訓集](LESSONS.md)（英語、未翻訳）: 過去のヒューリスティック。使う前に現在のソースやテストと照合してください。

## 文書の翻訳

翻訳の選択と同期には、[対応状況の台帳](../DOCUMENTATION_INVENTORY.md#bilingual-coverage-and-translation-scope)（英語）と[言語方針](../DOCUMENTATION_LANGUAGE_POLICY.ja.md)を使います。アーカイブしたタスクのワークフローは、翻訳されていても過去のものです。

## 非推奨になった過去のワークフロー

- [AI Agent Strategy 2026](AI_AGENT_STRATEGY_2026.md)
- [Long-Horizon Task Workflow](LONG_HORIZON_WORKFLOW.md)
- [AI Agent Runner Design](RUNNER_DESIGN.md)

これらのファイルはアーカイブした履歴への案内として残しているもので、有効な指示ではありません。

## Skill

リポジトリの Skill は、その限定されたワークフローが実質的に役立つ場合にだけ使います。残している Skill を、通常の Issue/PR の読み取り、実装、レビュー、テスト、状況報告のために必ず経由すべきものとして扱わないでください。Skill を追加したり大きく変更したりする場合は、[Skill の軽量評価](../agent-skills/EVAL.ja.md)を使います。
