# Issue #120 Rebuild Commits Summary (Current Status)

本ドキュメントは、`90a278c` を起点とした高精度パイプラインの再構築（Epic Issue #120）における、現在ローカルブランチ(`rebuild/baseline-90a278c-fixed`)上に積まれているコミットの整理と監査結果をまとめたものです。

## 1. 変更の適切な立ち位置の整理 (Epic #120 との対応)
現在、一つのローカルブランチに Phase 1 〜 Phase 3 までの複数の異なる性質の変更（Infra, Refactoring, Precision Fix）が**まとめて積まれてしまっている状態**です。
本来、Epic #120 の設計図(`118_rebuild_issue_map.md`)においては、以下のグループごとに独立したPR（スモールステップ）として段階的にマージしていくことが意図されていました。

* **Group A & C (Phase 1: Infra/Env)**: インプロセス化、バッチ化、環境統合
* **Group B (Phase 2: Func BugFix)**: ページ範囲指定などの機能バグ修正
* **Group D & E (Phase 2-3: Logic & Precision)**: 精度の復旧（サイレントバグの修正と100% Recallロジック）

今後の作業では、このローカルブランチをそのまま全体としてPush/Mergeするのではなく、**グループごとにブランチを分割して個別のPRとして提出し直す（再整理する）**必要があります。

---

## 2. 各コミットの概要と状況（問題・解決内容・計測結果）

以下は、`1e4b574`（ゴールデンベースラインの計測環境確定）以降に積まれたコミットの時系列順の記録です。
すべてのステップにおいて、計測方法として `verify_golden_baseline.py` および `bisect_test.sh` (ネイティブ再実行による検証スクリプト) を用いて、**FP=0, FN=1 の精度（TP=3580）が保たれていることを確認**しています。

### [1] 過去のネイティブ実行デグレの解消 (Epic前提のリカバリ)
* **Commit**: `3591202` (fix: resolve silent bug in CNN image scaling...)
* **何が問題だったか**: `90a278c` にてネイティブ実行をすると、FP=11, FN=4 となり、当時の研究用キャッシュなしでは FP=0, FN=1 が再現できない状態（デグレ）でした。`git bisect` の結果、`b1a9ce6` の時点で CNN の `max_h` が 256 から 1024 に誤って引き上げられていたことが原因と判明しました。
* **何を解決したか**: `max_h=256` に戻すことで、純粋な `90a278c` 上の自動実行で FP=0, FN=1 が完全再現される状態を回復しました。
* **状況・結果**: `bisect_test.sh` をパス。これにより以降のステップの「精度維持」の前提が整いました。

### [2] 計測・検証スクリプトの軽微な修正
* **Commit**: `0ddabe1` (fix: resolve candidate_rescale_factor kwarg...)
* **何が問題だったか**: `verify_repro_batch_final.py` スクリプトの呼び出し引数が古い API とズレており、エラーが発生していました。
* **何を解決したか**: 不要な kwargs を削除し、テストスクリプトが正常に動作するようにしました。

### [3] Group A & C (Phase 1): 基盤整備・インプロセス化
* **Commit**: `bf5f21c` (feat: complete Phase 1 - In-process execution and Batch Orchestrator)
* **何が問題だったか**: OMRやCNNなどの外部プロセス呼び出しによるオーバーヘッドと、依存関係の分散。
* **何を解決したか**: `ecec76c`, `4177e7a`, `f2de576` 等の変更を一括適用し、Orchestrator上での In-process 実行化、およびDockerfileの統合を行いました。
* **状況・結果**: 統合パイプラインでの実行が可能に。`bisect_test.sh` にてネイティブに `FP=0, FN=1` が維持されていることを確認。

### [4] Group E (Phase 3): Precision / 100% Recall ロジック
* **Commit**: `ac0bba1` (Fix: Restore 100% recall/precision by implementing native candidate filtering...)
* **何が問題だったか**: 当時の手動フィルタリングをパイプライン上で自動化する必要がありました。
* **何を解決したか**: `64d9a37` の Box Tightening および Candidate Filtering ロジックをネイティブに統合しました。
* **状況・結果**: `bisect_test.sh` パス。ネイティブの自動実行で FP=0, FN=1 を維持。

### [5] Group D (Phase 2): Logic Fix (サイレントバグ修正)
* **Commit**: `6babdf7` (fix: Resolve silent bugs found during accuracy reproduction investigation)
* **何が問題だったか**: 長い五線の誤認 (Tall Band Dilution) や、クロップ時の微小な丸め誤差が精度低下（FP増加）を招いていました。
* **何を解決したか**: `c12c600` の Tall Band 対策と Threshold の微調整を導入しました。
* **状況・結果**: コンフリクトを解消して適用。`bisect_test.sh` にて FP=0, FN=1 を維持。

### [6] Group E (Phase 3): 閾値一貫性
* **Commit**: `2c385cc` (fix: address candidate filter logic and CNN scoring threshold consistency)
* **何が問題だったか**: 1x スケールと 2x/4x スケールの評価座標間で、フィルタロジックの閾値に不整合がありました。
* **何を解決したか**: `7108a78` に基づき、CNNスコアリングとフィルタの座標スケール一貫性を修正しました。
* **状況・結果**: `bisect_test.sh` パス。FP=0, FN=1 維持。

### [7] Group D (Phase 2): Logic Fix (Seed Splitting Resolution)
* **Commit**: `1994ac0` (fix: standardize mask resolution handling and seed splitting in pipeline)
* **何が問題だったか**: Tall Band 分割の閾値が、画像の解像度に依存するハードコードされたピクセル値になっていました。
* **何を解決したか**: `710e4b1` の核心ロジックである、`unit_size` をベースにした解像度非依存の分割閾値 (12.0x) を導入しました。
* **状況・結果**: 手動適用後、`bisect_test.sh` にて FP=0, FN=1 維持確認。

### [8] Group A/B (Phase 2): 純粋なリファクタリング・機能改善群
* **Commit**: `694e1a2` (Refactor: Minor updates to pipeline orchestrator...)
* **Commit**: `f6cdb78` (Chore: 機械的なimport修正)
* **Commit**: `489bb93` (Fix: Support page range notation during PDF conversion)
* **Commit**: `06c0684` (fix(pipeline): correct staff mask path mapping in probe_scan)
* **何が問題だったか**: モジュール化の不備や、PDF変換のページ指定機能の欠如、マスクパス解決の不具合がありました。
* **何を解決したか**: インメモリ画像のキャッシュ渡しへの対応(`223ba75`)、ページ指定(`dad6801`)などの機能改善とインポート整理を実施しました。
* **状況・結果**: 全て適用後、`bisect_test.sh` にて FP=0, FN=1 が維持されていることを確認。

### [9] 最終の統合パイプラインのランタイムバグ修正
* **Commit**: `2a7441e` (fix(pipeline): add in_memory_images support to run_detection_step...)
* **何が問題だったか**: `make run-pipeline` による E2E 実行において、引数 `in_memory_images` が `run_detection_step` に渡されず TypeError でクラッシュしました。
* **何を解決したか**: オーケストレータのメソッドシグネチャを修正し、統合パイプラインが完走するようにしました。
* **状況・結果**: `make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full.yaml` を実行し、E2E でのエラーなし完走、および最終精度 `TP=3580, FP=0, FN=1` になることを確認済み。
