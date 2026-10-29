# Engineのサービス準備gate

<!-- translation: {"original":"ENGINE_SERVICE_READINESS.md","source":{"sha256":"01dc8a79805090cb2b437c5fd72bb4d67ca12dd1749bda176ee6a7d8c4b95736"},"state":"reviewed"} -->

[English / 原文](ENGINE_SERVICE_READINESS.md)（英語正本）

翻訳元: same PR / SHA-256 `01dc8a79805090cb2b437c5fd72bb4d67ca12dd1749bda176ee6a7d8c4b95736`。状態: `reviewed`。全文の意味・制約・例外を原文と照合し、日本語の可読性も確認済み。

Issue #340は、v1 engine契約を取り巻くサービス準備検証の範囲を完了する。これらのgateはengine境界を検証するものであり、webサービスの実装・デプロイを行うものではない。

## 対応する1ジョブ境界

再利用可能な同期adapterは `src.pipeline.engine_executor.PipelineJobExecutor` である。

```python
result = executor(request, on_progress=handle_event)
```

v1 `JobRequest` を受け付け、v1 `ProgressEvent` レコードを転送し、失敗時には構造化された `EngineError` を持つv1 `JobResult` を返す。現在の参照adapterが出すのは `succeeded` または `failed` である。`review_required` と `cancelled` は引き続きv1契約の値であり、このadapterが現在生成する結果ではない。再利用可能な #337のキャンセル・実行期限primitiveは、まだその実行経路へ統合されていない。

このローカルadapterは入力preflight上限を適用するが、ジョブごとの実行時ディスクquotaを強制せず、storage使用量の増加によって内部を制御できない子プロセスを停止することもない。将来の公開サービスには、外部でのstorage上限とプロセスツリーのキャンセルが必要となる。[入力安全性](ENGINE_INPUT_SAFETY.ja.md#9-将来の公開サービスworkerコンテナ要件)を参照する。OSの `ENOSPC` は、best-effort cleanupを伴う `disk_capacity_exhausted` を返す。ローカルCLIはstorageが許す場合に失敗結果を記録する。容量枯渇・書き込み不可のfilesystemでは、永続化を保証できない。

adapterは `artifact_root/<job_id>` の試行storageを所有する。内部生成config、実行ディレクトリ、`pipeline.log` は実装詳細のままとする。呼び出し側に公開するのは、`JobResult.artifacts` が提示する相対パスだけである。

公開は成功時だけに行う。

- `final/<output-name>_score_numbered.pdf` は `final.score_numbered_pdf` として提示する。
- `review` と `debug` profileでは、`review/manual_correction_input.json` を提示する。
- 公開用review引き渡しには、パッケージ相対のreviewファイルと、安定した元ジョブ・座標の識別情報を含める。内部の元実行・manifestパスは含めない。
- 失敗試行ではfinal/review成果物を提示せず、return前にstaging済み公開出力を削除する。

現在の参照executorは、v1 `CorrectionSet` レコードを実行しない。Issue #340の補正互換性gateは、安定したreview引き渡しを公開し、その成果物hash・座標の識別情報を `CorrectionSet.assert_source_matches()` で利用できることの実証に限定する。リポジトリが1ジョブ境界を通して補正実行を公開しているという主張ではない。その機能は引き続き既存の保持済みreview・補正ワークフローにある。`CorrectionSet` を持つリクエストは、補正前の入力を黙って再実行せず、`correction_execution_unavailable` で安全側に拒否する。

## 軽量なPR互換性gate

`.github/workflows/pr-validation.yml` は、軽量なPython依存だけで `engine-contract` jobを実行する。対象は次のとおり。

- JobRequest / JobResult / ProgressEvent / EngineError / CorrectionSetの通信互換性
- 受理するv1と非互換バージョンの挙動
- 入力安全性と安定した失敗code
- ライフサイクル・テレメトリの不変条件
- 内部実行・ログパスを公開しないexecutorのfinal/review公開
- 不正なリクエストの処理
- 決定的な子プロセス失敗のマッピングと公開出力のcleanup

同じexecutorテストは `make test-fast` にも含まれる。

## クリーンなコンテナ・runtime smoke

次を実行する。

```bash
make verify-service-readiness-smoke
```

Docker runtime wrapperは、image・モデル資産契約を含む、既存の正規runtime preflightを最初に行う。その後、コンテナの外向きネットワークを無効にして（`--network none`）、サービス準備smokeを起動する。

smokeは `artifacts/` 以下にPDF・staff・barlineのfixtureを決定的に作成し、Git管理外のローカル評価PDFに依存しない。代表ジョブは `configs/service_readiness_smoke.yaml` と実際の設定起点のpipeline・番号付け・実体化経路を使い、detectorとMMR推論は意図的にskipする。構造化進捗・結果のシリアライズ、final/reviewの配置、補正元の互換性、公開結果に内部実行・ログパスがないことをassertする。

同じsmokeは、推論前に次も確認する。

- 破損PDFの拒否
- 設定したPDF byte上限
- リクエスト必須フィールドの欠落
- 決定的な子プロセス失敗のマッピング
- これらの失敗後にfinal/reviewを公開しないこと

このsmokeは、サービス境界・runtime互換性のチェックであり、精度benchmarkではない。

## GPU・精度検証方針

変更を検知できる、最も範囲の狭い正本に基づく検証を使う。

| 変更 | 必須の検証 |
| --- | --- |
| 契約・スキーマ・executorのunit範囲だけの変更 | PRの `engine-contract` gateと `make test-fast` |
| コンテナ・サービス境界の接続 | `make verify-service-readiness-smoke` |
| productionのGPU・モデル読み込み、detector runtime経路 | 上記に加え `make verify-gpu-smoke` |
| detector/MMR/番号付けの数値的挙動、または正規評価出力 | 既存の対象別テスト + GPU smoke + [検証方針（英語・未翻訳）](dev/VALIDATION_POLICY.md)で要求する高負荷・full評価 |

シリアライズ、失敗マッピング、成果物descriptor、CIの接続、サービス準備smokeだけが変わったことを理由に、full68実行は要求しない。productionの精度挙動にも影響する変更の場合は、既存の精度方針を引き続き正とする。

## 将来のサービスとの関係

将来のサービス・control planeは、このバージョン付きengine境界を呼び出し、HTTP、queue、永続化、object storage、再試行scheduling、デプロイ、ユーザー・製品方針を別途担ってよい。`pipeline.log` の解析、内部実行ディレクトリ以下のファイル探索、detector/MMR/番号付けの意味規定の再実装を行ってはならない。
