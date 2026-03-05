# Task: ISSUE-070 (Issue #70)

## Title
[Task] パイプライン・テスト実行時のパフォーマンス低下（時間増大）の原因調査と対策

## Branch Information
- **Base branch**: `feature/batch_orchestrator`
- **Branch name**: `chore/performance-investigation`
- **PR base**: `feature/batch_orchestrator`

## Goal
直近の開発やテストの実行において、処理時間が予想以上にかかる（パフォーマンスの低下）現象が確認されたため、その根本原因を調査し、必要に応じて対策を講じる。

## Background & Hypothesis
- `make test` や `main.py --dry-run` などの実行時に、応答が非常に遅い（タイムアウトになるケースも発生）。
- 特に、Docker Exec でコンテナにアクセスする頻度や、モデル推論時のメモリ使用量が影響している可能性が疑われる。
- **仮説**: 専用GPUメモリ（VRAM: RTX 4060 8GB）が不足し、共有GPUメモリ（システムメモリ）へスワップ・はみ出しが発生していることで、極端な速度低下を招いている可能性がある。ただし、単なるモデル読み込みのオーバーヘッドやスペック不足の可能性もあるため検証が必要。

## Scope
### In-Scope
- ホスト上のプロセスとDockerコンテナ内のプロセスでのボトルネックの特定。
- テストおよびパイプライン実行中のGPUメモリ（専用・共有）とシステムメモリの使用量のモニタリング。
- プロセス生成（`subprocess.run` 等）のオーバーヘッドの測定。
- ボトルネックを解消、または回避するための設定・コード修正の提案と実装。

### Out-of-Scope
- モデルアーキテクチャの根本的な軽量化・再学習（推論環境の設定調整レベルに留める）。

## Acceptance Criteria / Definition of Done
- [ ] パフォーマンス測定用のスクリプト、またはモニタリング手順の確立（`nvidia-smi`, `htop`, `nsys` などの活用）。
- [ ] 処理時間が極端に長くなる箇所の特定（ログ出力等によるプロファイリング）。
- [ ] VRAMはみ出し等、リソース枯渇の有無の確認と原因の特定。
- [ ] 設定変更（例: バッチサイズ縮小、onnxruntime-gpuのスレッド数調整、メモリ割り当て制限）やロジック改善による対策の実施。
- [ ] 対策後の実行時間とリソース使用量の改善確認。

## Notes
- Issue #13 (Full Pipeline Phase 2: Batch optimization, VRAM management) と関連が深い。本調査の結果は #13 の VRAM管理戦略に反映させる。
