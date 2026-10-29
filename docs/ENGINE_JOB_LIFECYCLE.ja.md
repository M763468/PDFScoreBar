# Engineの1ジョブ・ライフサイクル契約

<!-- translation: {"original":"ENGINE_JOB_LIFECYCLE.md","source":{"sha256":"cb519a21fd3713081d3a46c68b4173a4ed3a727195b865f8cf359e6edfc9d19d"},"state":"reviewed"} -->

[English / 原文](ENGINE_JOB_LIFECYCLE.md)（英語正本）

翻訳元: same PR / SHA-256 `cb519a21fd3713081d3a46c68b4173a4ed3a727195b865f8cf359e6edfc9d19d`。状態: `reviewed`。全文の意味・制約・例外を原文と照合し、日本語の可読性も確認済み。

> **状態: Engine Job Contract v1に重ねるIssue #337のライフサイクル契約。**
>
> シリアライズされた外部境界は、すでに[Engine Job Contract](ENGINE_JOB_CONTRACT.ja.md) / `src.pipeline.engine_contract` で定義されている。本書はそのスキーマを再定義しない。1回の同期engine試行が既存のv1終端ステータスへ至る方法、timeout・キャンセル・再試行可能性の挙動、成果物を公開済みとして扱える時点を規定する。
>
> 現在のproduction runtimeの挙動については、[パイプラインアーキテクチャ](PIPELINE_ARCHITECTURE.ja.md)、現在のソース・テスト、有効なproduction設定を正とする。

## 1. スコープと正本

PDFScoreBarは、1ジョブのengine境界では引き続き同期的に動作する。

```text
JobRequest
  -> one engine attempt
       -> ProgressEvent*
  -> JobResult
```

将来のworker・サービスは、この呼び出しをqueueing、lease、永続化、再試行、worker配置、object storageで包んでもよい。これらはengineの責務ではない。

このライフサイクル契約が担う範囲は次のとおり。

- 実行・ライフサイクル上のv1終端ステータスの意味
- 実行期限と協調的キャンセル
- 安全なキャンセル・timeout checkpoint
- `EngineError.retryable` が伝える再試行可能性の意味
- 再実行と一般的な試行の冪等性に関する要件
- 部分的な成果物の公開規則
- 1試行の一時・中間データのcleanup
- OOM、ディスク容量不足、子プロセス異常終了、無効なPDF、runtime資産欠落のライフサイクルへの対応付け
- 既存のreview/correctionの挙動との整合

この契約では次を定義しない。

- production用のqueueやscheduler
- queue leaseやジョブ間のscheduling
- ジョブ・履歴状態の永続化
- object storageでの保持期間
- 認証・アカウント・課金
- 信頼できないPDFの具体的なサイズ・ページ・pixel制限（#338）
- [テレメトリ契約](ENGINE_TELEMETRY.ja.md)（#339）が担う進捗・リソーステレメトリの詳細
- サービスのデプロイやコンテナ互換性gate（#340）

## 2. Engine Job Contract v1との関係

Issue #336は完了しており、そのv1型を規範とする。特に次が適用される。

- `JobStatus` は次の4値だけである。
  - `succeeded`
  - `review_required`
  - `failed`
  - `cancelled`
- `failed` と `cancelled` には `EngineError` が必須となる。
- `succeeded` と `review_required` に `EngineError` を含めてはならない。
- `review_required` には `review.required=true` と有効な補正元成果物が必須となる。
- `EngineError` は次を公開する。
  - `category`
  - 安定した機械可読の `code`
  - 公開しても安全なメッセージ
  - `user_actionable`
  - `retryable`
  - 任意の診断専用 `debug_context`
- `caller_reference` は相関付け用のmetadataであり、冪等性キーではない。
- 補正実行では、#336のバージョン付き `CorrectionSet` の来歴・冪等性規則を使う。

したがって、Issue #337は別の終端ステータスenumやエラーエンベロープを導入しない。

## 3. #337時点の挙動監査と現在のadapterの状態

以下の表は、#340の参照adapterより前の、#337時点の設定起点runtimeの監査記録である。表内のadapterの不足は過去のものであり、現在もv1 executorが存在しないという意味ではない。

現在の `PipelineJobExecutor` は `run_pipeline()` を包み、v1結果の返却、対応する失敗のマッピング、final/review成果物のstaging・公開、失敗時のbest-effort cleanupを行う。現在返すのは `succeeded` または `failed` である。`review_required` の推定、v1 `CorrectionSet` リクエストの実行、`ExecutionControl` checkpointやプロセスグループ終了の統合は行わない。以下のキャンセル・実行期限・補正ジョブに関する要件は、統合に向けた規範となる契約であり、現在の参照adapterが対応済みという意味ではない。対応する境界は[サービス準備gate](ENGINE_SERVICE_READINESS.ja.md)を参照する。

| 関心事 | #337時点の挙動 | #337で特定したライフサイクル契約との差分 |
| --- | --- | --- |
| 呼び出し | `run_pipeline(...)` は同期的で内部実行ディレクトリを返す | `JobResult` を生成するv1 adapterがまだない |
| 最上位の失敗 | 例外が伝播し、最上位のlogging handlerは `finally` で復元される | 例外を `EngineError` に変換するadapterがない |
| Timeout | `run_pipeline()` にdeadline引数がない | 外側のプロセス・コンテナ制限が働くまで停止不能な処理が続き得る |
| キャンセル | cancellation token・checkpointを受け付けない | パイプラインに協調的キャンセルがない |
| 子プロセス | dense-route workerは `subprocess.run`、OMR helperは `run_with_logging` を使う | 共通のtimeout・cancel・プロセスグループ終了方針がない |
| 子プロセスの失敗 | 非zero終了が `RuntimeError` / `CalledProcessError` になる | v1エラーcategory/codeへ未マッピング |
| 実行完了marker | `manifest.json` と `filters.json` は正常完了に近い段階で書かれる | 公開ライフサイクル結果ではない |
| ページ別出力 | 後続処理の完了前に `numbering_final.json` が書かれ得る | 名前に「final」があっても不完全な試行の証跡になり得る |
| Reviewパッケージ | パイプラインの通常処理完了後に実体化される | 実体化自体はtransactionalではない |
| JSON/PDF書き込み | 複数の出力を宛先パスへ直接書く | プロセス・ディスク障害で不完全な宛先ファイルが残り得る |
| Cleanup | 実行・中間・SR・debugデータは通常、別途cleanupするまで残る | 試行ごとのライフサイクルcleanup分類がない |
| 再実行 | `--skip-existing` で内部成果物を再利用できる | 運用者向けの仕組みであり、公開の冪等性ではない |
| 補正付き再実行 | 保持済み成果物の選択的再実行は、すでに入力元の来歴を維持する | 補正試行の公開・cleanupはまだv1 executorのtransactionではない |

直接の設定起点runtimeには、引き続き次の2つの重要な性質がある。

1. 内部ファイルの存在は、1ジョブの結果が成功した証明ではない。
2. 現在のプロセスを強制終了すると、engineの終端結果なしに不完全なファイルが残り得る。

## 4. 終端状態の意味

### 4.1 `succeeded`

要求されたengine処理が完了し、呼び出し側が利用できる成果物群を `JobResult` が意図的に提示した状態。

要件:

- リクエストに必要な成果物は、宣言された役割を果たすのに十分な完成状態である。
- 提示された成果物descriptorが公開境界となる。
- staging・内部パスは、存在するだけで呼び出し側向けの成果物にはならない。
- `EngineError` を付けない。
- 終端進捗を出す場合は `job_succeeded` とする。

### 4.2 `review_required`

engineは有効なreview生成試行を完了したが、ワークフローを完全に受理された最終出力として扱う前に、呼び出し側・ユーザーによるreviewが必要な状態。

v1から引き継ぐ要件:

- `review.required=true`
- `review.correction_source_artifact_id` は、この結果が返す成果物を指定する。
- その補正元成果物は、必要なhashと座標空間の識別情報を持つ。
- `EngineError` を付けない。
- 終端進捗を出す場合は `job_review_required` とする。

ライフサイクル上の意味:

- この結果が提示するreview成果物は、有効な公開済み成果物である。
- 結果が提示しない内部の不完全なファイルは、非公開のままとする。
- 呼び出し側は `review_required` を `succeeded` と同一視してはならない。
- 補正・再処理は、#336の `CorrectionSet` 契約に従う新しいengineジョブとなる。

### 4.3 `failed`

要求されたengine操作を試行が完了できなかった状態。

要件:

- `EngineError` が存在する。
- 内部の不完全なファイルを、暗黙に成功成果物へ昇格させない。
- 診断成果物は、上限を設けたcleanup方針に従って保持してよい。
- 終端進捗を出す場合は `job_failed` とする。

実行期限の超過は `failed` であり、`cancelled` ではない。

### 4.4 `cancelled`

対応するキャンセルcheckpointで明示的なキャンセル要求を観測し、その要求によって実行を停止した状態。

要件:

- categoryが `cancelled` の `EngineError` が存在する。
- 提示されていない不完全な出力を成功として扱わない。
- 終端進捗を出す場合は `job_cancelled` とする。
- 再送信は外側の呼び出し側が判断し、engine側の自動再試行ではない。

engineがキャンセルを観測する前にプロセス・コンテナが強制終了された場合、`cancelled` の結果を出せないことがある。それでも外側のadapterはその試行を非成功として扱わなければならず、残ったファイルから成功を推定してはならない。

## 5. 実行期限とキャンセル

### 5.1 再利用可能な制御primitive

Issue #337は `src.pipeline.engine_lifecycle` に次を提供する。

- `CancellationToken`
- 単調時計に基づく `ExecutionDeadline`
- `ExecutionControl.checkpoint()`
- `JobCancelled`
- `JobDeadlineExceeded`
- これらの制御例外から、規範となるv1 `JobStatus` / `EngineError` へのマッピング

これらはengine実装用helperであり、新しい通信スキーマのフィールドではない。

### 5.2 安全なcheckpoint

ライフサイクルの確認は、任意のPython/CUDA実行を中断するのではなく、安定した境界に追加すべきである。

- 高コストのPDF rendering・推論の前
- 粗粒度の公開stage間
- stageの意味上可能であればページ間
- 子プロセスの起動前
- 子プロセス完了後、結果を利用する前
- final/review成果物の実体化前
- 終端結果の公開直前

中断できないCPU/GPU操作の最中に要求されたキャンセルは、次のcheckpointまで観測されないことがある。

### 5.3 キャンセルの優先順位

1つのcheckpointに到達した時点で、明示的なキャンセルと実行期限超過がともに成立している場合、明示的なキャンセルを優先する。試行は `JobStatus.CANCELLED` にマッピングされる。

これにより、呼び出し側が要求した停止と、engine試行が独立に実行予算を使い切った場合を区別できる。

### 5.4 実行期限のマッピング

実行期限のcheckpointは次にマッピングする。

- status: `failed`
- category: `resource`
- code: `execution_deadline_exceeded`
- 公開メッセージ: 範囲を限定し、診断情報を含めない
- `retryable=true`

ここで `retryable=true` は、一時的な時間条件・配置条件が変われば、意味的に同じリクエストの新しい試行が成功する**可能性がある**ことを意味する。engineやqueueへの自動再試行指示ではない。

### 5.5 明示的なキャンセルのマッピング

観測された明示的なキャンセルは次にマッピングする。

- status: `cancelled`
- category: `cancelled`
- code: `job_cancelled`
- `retryable=false`

外側の呼び出し側は、それでも後から意図的に新しいジョブを送信してよい。このflagは、キャンセル自体が自動再試行すべき一時的な失敗ではないことだけを示す。

### 5.6 子プロセス終了方針

現在のsubprocess境界へライフサイクル制御を統合する際、目指す方針は次のとおり。

1. 起動前にキャンセル・実行期限を確認する。
2. 終了可能なプロセスグループ境界内で、使い捨ての子プロセスを起動する。
3. 待機中にキャンセル・実行期限を観測する。
4. グループの終了を要求する。
5. 短く上限のある猶予期間を設ける。
6. 子プロセスが終了しなければ強制終了する。
7. 終了状態・結果の検証に成功するまで子プロセスの結果を利用しない。
8. 起因する条件に応じて親試行を `cancelled` または `failed` へマッピングする。

現在のsubprocess呼び出し箇所は、この共通方針をまだ実装していない。統合時には、既存の意図的なGPU・プロセス分離を維持しなければならない。

### 5.7 外側の強制timeout

worker・コンテナは、最終的な保護策として強制的な実行制限を設けてよい。SIGKILLやコンテナ喪失は、engineの `finally` cleanupと終端シリアライズを妨げ得る。したがって、正しさを強制終了後のcleanupに依存させてはならず、成功の終端結果がなければ常に非成功となる。

## 6. 再試行可能性の方針

`EngineError.retryable` はengineからのhintであり、再試行のorchestrationを実装するものではない。

v1のbooleanは次の意味を持つ。

- `true`: 入力・補正の変更を要求せずに、意味的に同じリクエストの新しい試行が成功すると合理的に期待できる。再試行回数・backoff・配置は引き続き外側の呼び出し側が担う。
- `false`: 変更なしの自動再試行は推奨しない。入力、補正、設定、意図を変更した後に、ユーザー・サービスが新しいジョブを送信してよい。

推奨するライフサイクルのマッピング:

| 失敗 | v1 category | 推奨code | user_actionable | retryable |
| --- | --- | --- | --- | --- |
| 不正・破損・未対応PDF | `input` | `input_pdf_invalid` | true | false |
| 無効なリクエスト・設定上書き | `invalid_request` | `request_invalid` | true | false |
| 設定されたジョブごとの上限による拒否 | `resource` | `resource_limit_exceeded` | true | false |
| 実行期限の超過 | `resource` | `execution_deadline_exceeded` | false | true |
| GPU OOM | `resource` | `gpu_out_of_memory` | false | true |
| ディスク容量不足・書き込み容量の障害 | `resource` | `disk_capacity_exhausted` | false | true |
| 予期しない子プロセス異常終了・signal | `internal` | `child_process_failed` | false | true |
| 必須モデル・runtime資産の欠落・無効 | `dependency` | `runtime_dependency_unavailable` | false | true |
| 古い・無効な補正元 | `correction` | `correction_source_invalid` | true | false |
| 観測された明示的キャンセル | `cancelled` | `job_cancelled` | false | false |
| 未知の内部エラー | `internal` | `internal_error` | false | true |

これらは既定のマッピングである。engineがより正確で決定的な条件を特定できる場合、一般的な再試行可能な内部エラーよりも、その正確なcode/categoryを優先すべきである。

サービスは、方針や運用上の理由により、さらに再試行を抑制してよい。queueのbackoffや再試行上限はengineの責務ではない。

## 7. 再実行と冪等性

PDFScoreBarは、worker間のexactly-once実行を保証しない。

一般的なジョブの意味規定:

- 実行ごとに新しいengine `job_id` を割り当てる。
- `caller_reference` は相関付けmetadataであり、冪等性キーとして扱ってはならない。
- 再試行・再実行では、既定で新しい試行workspaceを使うべきである。
- 同じ呼び出し側参照を再利用したというだけで、以前の不完全な内部実行ディレクトリを信頼してはならない。
- 現在の `--skip-existing` は、内部・運用者向けの最適化・復旧機構のままであり、外部の再試行契約ではない。

補正固有の冪等性は、すでに #336で規範となっており、変更しない。

- `correction_set_id` は、1つの論理的な補正送信を識別する。
- 同じ入力元に対して同じ正規化内容を繰り返すことは、冪等な再送となる。
- 内容が異なるのに同じIDを再利用することは競合となる。
- 補正付き実行自体は、新しいengineジョブとなる。
- 冪等性履歴の永続化は、純粋な契約モジュールではなく、呼び出し側とexecutorの統合部分が担う。

## 8. 成果物のライフサイクルと公開

ライフサイクル上の扱いは、現在のディレクトリ名ではなく、成果物の意味で決まる。

| 分類 | 現在の例 | 非失敗の終端結果時 | 失敗・キャンセル試行時 | 公開契約 |
| --- | --- | --- | --- | --- |
| 不変の入力・参照 | 入力PDF、補正元reviewパッケージ、CorrectionSet | 呼び出し側所有・保持 | 保持 | 入力・参照のみ |
| 一時作業データ | 一時render/SR/staging/requestファイル | 不要になったら削除 | best-effortで削除 | 成果物にはしない |
| 試行の中間データ | detector/MMR/番号付けの中間データ | debug・再利用方針によってのみ保持 | 任意で上限付きの診断用保持 | 存在だけでは公開しない |
| 明示的な再利用可能成果物 | 来歴を持つ検証済み保持成果物 | 契約が許す場合に保持 | 独立に有効な場合だけ保持 | descriptor・来歴で管理 |
| review成果物 | 手動補正の引き渡し・パッケージ | descriptorを返す場合だけ公開 | 不完全なパッケージは公開しない | 成果物descriptor |
| final成果物 | 完成した小節番号付き出力 | descriptorを返す場合だけ公開 | 不完全な宛先を公開しない | 成果物descriptor |
| debug・来歴の証跡 | ログ、構造化診断、trace | 任意で上限付き保持 | 任意で上限付き保持 | 診断用途のみ |

重要な規則:

> **内部パスの存在は公開を意味しない。呼び出し側が利用できるのは、非失敗の終端 `JobResult` が意図的に提示した成果物だけである。**

`failed` または `cancelled` の場合、残ったファイルを診断用の試行証跡として保持してよいが、成功したfinal/review成果物として提示してはならない。

`review_required` の場合、提示されたreview・補正元成果物は有効な公開済み出力となる。それでも呼び出し側は終端ステータスを尊重し、`succeeded` と扱わずにreviewワークフローを続けなければならない。

## 9. 原子性と部分的な書き込み

現在のhelperは、JSON/PDFを宛先パスに直接書くことが多い。このため、OS・プロセス・ディスク障害で不完全な宛先が残り得る。

将来のライフサイクルを考慮した実体化では、実用上可能な範囲で次を優先すべきである。

1. 同じfilesystem上の試行内一時パスへ書く。
2. flush・closeし、成果物を検証する。
3. 試行の確定済み成果物の場所へ、原子的に置換・renameする。
4. 確定済み成果物からdescriptorを構築する。
5. 必要な公開の完了後にだけ、非失敗の終端結果を出す。

これは特に、最終PDF、review引き渡し、後続の補正試行が使う機械可読成果物で重要となる。

## 10. Cleanupの意味

### 10.1 `succeeded` / `review_required`

確定済み成果物が準備できた後:

- debug・再利用のために保持する役割のない一時データを削除する。
- 提示した成果物と必要な来歴を保持する。
- 任意のdebug証跡は、上限を設けたローカル方針に従ってのみ保持する。
- 提示した成果物を損なわないcleanup警告は、警告として返してよい。

### 10.2 `failed`

- 内部の不完全なfinal/review成果物を公開しない。
- engine所有の一時・stagingファイルをbest-effortで削除する。
- 任意で上限付きの診断証跡を保持する。
- 不変の呼び出し側入力や成功した補正元reviewパッケージを削除してはならない。
- cleanup失敗は診断context・警告として記録し、失敗試行を成功に変えてはならない。

### 10.3 `cancelled`

失敗と同じcleanup原則を使いながら、独立した `cancelled` ステータスを維持する。

### 10.4 強制終了

engineは、SIGKILL、コンテナ喪失、マシン障害、filesystem喪失後のcleanupを保証できない。試行workspaceを所有するworkerは、detector/MMR内部を理解せずに、後からそれを隔離・削除できなければならない。TTLと長期保持は、引き続きサービス・storage方針とする。

## 11. 失敗別の挙動

### 無効・破損PDF

直接の設定起点のPyMuPDF open/renderエラーは伝播する。現在の参照executorは #338のpreflightを使い、決定的なPDF拒否を `ErrorCategory.INPUT` と公開用に安全な入力code/messageへマッピングする。具体的なpreflight制限と悪意ある入力のチェックは #338で定義する。

### GPU OOM

`failed`、category `resource` として扱う。成功させるためだけに、同じ試行内でモデル品質を黙って下げたり、要求された意味的な処理契約を変更したりしてはならない。既存の使い捨てプロセス境界は、引き続きGPU状態の解放に役立つ。

### ディスク容量不足・書き込み失敗

`failed`、category `resource` として扱う。不完全な宛先は公開ではない。リソース配置・容量を変更できるようになった後の再試行は、外側が判断する。

### 子プロセス異常終了

より具体的な入力・リソースエラーが判明していない限り、非zero終了・signalは親試行の失敗となる。欠落した、古い、または不正な子プロセス結果ファイルを、成功として利用してはならない。

### モデル・runtime資産の欠落

`dependency` として扱う。通常のジョブ実行中に、別のモデルを黙ってdownload・代用してはならない。適切に準備された別のworkerなら、意味的に同じリクエストを再試行できる。

## 12. Review・補正ライフサイクル

既存のreview・補正の意味規定を、引き続き実装の基礎とする。

```text
initial JobRequest
  -> succeeded OR review_required JobResult
  -> advertised review/correction-source artifact
  -> CorrectionSet bound to source job/artifact/hash/coordinate/version
  -> new corrected JobRequest / new job_id
  -> corrected JobResult
```

ライフサイクルの規則:

- 対応する補正元にできるのは、公開済みのreview・補正元descriptorだけである。
- 部分的なreviewディレクトリが存在するだけでは、失敗・キャンセル試行から有効なreview引き渡しは成立しない。
- 古くなった補正元の識別情報は、#336の来歴gateで拒否する。
- 補正ジョブの失敗・キャンセルによって、成功した元ジョブの分類を変更しない。
- 元のreviewパッケージと補正入力は、補正試行に対する不変の入力である。
- 補正試行の中間データには、通常の試行cleanup規則を適用する。
- 補正されたfinal/review成果物は、その補正試行の非失敗の終端結果によってのみ公開する。

## 13. プロセス終了と結果の整合性

将来のCLI/subprocess adapterは、次に従うべきである。

- そのadapterが受理する非エラー終端結果についてのみ、終了codeをzeroとする。
- `failed` と `cancelled` では、プロセス終了を非zeroにする。
- 別途標準化されていない限り、非zeroの具体的な数値の割り当てはadapterの方針とする。
- 出力された構造化結果とプロセス終了は矛盾してはならない。
- 終端結果のシリアライズ前にプロセスが終了した場合、外側のadapterは非成功として扱う。
- 自由形式のログは診断であり、状態機械ではない。

`review_required` は有効な非失敗の `JobResult` なので、明示的な `review_required` ステータスも維持する限り、CLI/workerはzeroを使ってよい。呼び出し側は、プロセスcodeだけから `succeeded` を推定してはならない。

## 14. 責務の分担

### Engine・本リポジトリ

- 同期的な1試行の意味規定
- ライフサイクルcheckpointと制御例外
- ライフサイクル制御からv1 status/errorへのマッピング
- 統合された際の安全な子プロセス終了hook
- 成果物の公開規則
- engine所有の試行内cleanup
- 保持済み成果物の来歴検証
- 補正・再処理の意味規定
- 対象を絞った互換性テスト

### #338

採用済みの安全性の意味規定は、[入力安全性契約](ENGINE_INPUT_SAFETY.ja.md)に記録する。

- 信頼できないPDF・パス・ネットワークの安全性
- 設定可能で具体的なジョブごとの上限
- 可能であれば不要で高コストな推論の前に拒否すること
- worker・コンテナの強制リソース制限とoffline runtimeの前提

### #339

採用済みの構造化テレメトリの意味規定は、[テレメトリ契約](ENGINE_TELEMETRY.ja.md)に記録する。

- 固定済みのv1 stage/status語彙を変更しない、追加的なelapsed/detailフィールド
- このライフサイクルと整合する単調な順序と、正確な終端 `JobStatus` マッピング
- コンパクトな粗粒度の時間計測と、明示的に有効化するプロセス・GPUリソース計測

### #340

- 採用された1ジョブ境界を実証する、軽量な契約・失敗テストとコンテナ・runtime smoke

### 将来のサービス・control plane

- queue lease
- ジョブ間のschedulingと並行実行
- ジョブ・履歴状態の永続化
- 再試行回数・backoff・orchestration
- workerの配置・置換
- object storageへのuploadと保持期間
- 全体quota・rate-limit・製品方針

## 15. #337後の実装状態

Issue #337では、意図的に `run_pipeline()` やすべてのdense-route subprocessを新しいexecutorへ接続しなかった。当時採用された段階的実装は次のとおり。

- 現在のproductionパイプラインの挙動を変更しない。
- 再利用可能なキャンセル・実行期限primitiveを追加する。
- それらをmerge済みのv1 `JobStatus` / `EngineError` へマッピングする。
- 当時の不足と必要な公開・cleanupの意味規定を文書化する。
- helperの挙動を軽量な対象別テストでカバーする。

現在は、3節のとおり #340の参照adapterが `run_pipeline()` を包んでいるが、これらのライフサイクル制御primitiveは利用していない。その統合に #336の通信スキーマ変更は不要である。高負荷のGPU stageまで接続する際は、現在のプロセス・メモリアーキテクチャを維持し、そのruntime変更に適した検証を行うべきである。
