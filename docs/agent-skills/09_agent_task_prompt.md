# コーディングエージェントに渡す改善タスク（Codex CLI / Gemini CLI 共通）

このファイルは「エージェント自身に、リポジトリ内の情報を参照させて改善を実装させる」ためのタスク文面テンプレです。
そのままコピペして利用できます。

------------------------------------------------------------------------

## タスク：Make-first + artifacts + skill整備

### 目的

このリポジトリの開発/保守作業を、長時間実行できるコーディングエージェント向けに整備する。

-   入口は Make ターゲットに統一する（Make-first）
-   出力は artifacts/ にファイルとして保存する（stdoutを会話に流さない）
-   反復作業を検出して Make ターゲット or skill
    として追加できるようにする
-   運用ルールを agent.md にまとめる

### 制約

-   破壊的操作（大量削除、強制push、本番デプロイ等）は禁止。必要なら提案のみ。
-   新規のターゲット/スキル追加は PR 方式のコミットとして行う。
-   secrets をログや artifacts に出力しない。

------------------------------------------------------------------------

## 実施手順（エージェントの行動計画）

1)  現状把握
    -   `Makefile` のターゲット一覧を確認（あれば `make help` /
        `make -n` / grep 等）
    -   既存の skill 体系（skills/ や類似ディレクトリ）を確認
    -   代表的な言語・ビルド・テスト・lint の手段を推定（package.json,
        pyproject, go.mod 等）
2)  artifacts/ の導入
    -   `artifacts/` を追加し、標準出力をファイルに保存する方針へ統一
    -   `.gitignore` を適切に更新（基本 artifacts は無視、必要なら docs
        に移動）
3)  Make-first 化
    -   `make help`（または `make list`）を追加し、説明付きで一覧化
    -   既存の2ターゲットを artifacts 出力に寄せる
    -   次の定番ターゲットを追加（repoに合わせて中身は適切に選ぶ）：
        -   repo-tree
        -   tests
        -   lint
        -   build
4)  skills の整理（必要な範囲で）
    -   SKILL.md
        を用意し、判断基準・入出力・生成物（artifactsのパス）を明記
    -   必要なら `skills/<name>/run.sh` を作り、Makefile から呼び出す
5)  自己進化の足場
    -   反復して実行されるコマンド列を見つけたら、Makeターゲット or
        skill 化を提案し実装
    -   `docs/agent-skills/skill-index.md` を更新
6)  agent.md の整備
    -   エージェントが守るべきルール（Make優先、artifacts、禁止事項、追加はPR等）を明文化

------------------------------------------------------------------------

## 成果物（必須）

-   `artifacts/` ディレクトリ
-   `Makefile` の更新（help/list、repo-tree/tests/lint/build など）
-   `agent.md`
-   （任意）`skills/` の追加・整理（SKILL.md と必要なら run.sh）
-   `docs/agent-skills/`（このバンドルの文書を配置するための置き場）
-   変更点の簡単な説明（PR本文相当を README か docs に追加）

------------------------------------------------------------------------

## 期待する最終動作

エージェントは次のように動けること：

-   まず `make help` で操作を発見する
-   `make repo-tree` / `make tests` / `make lint` / `make build`
    を実行し、結果を `artifacts/` で読む
-   反復作業があれば、新しい Make ターゲット or skill
    として追加していける
