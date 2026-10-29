# Engine Job Contract v1

<!-- translation: {"original":"ENGINE_JOB_CONTRACT.md","source":{"sha256":"ef941b2d929ae7ce46cf7c889570823b5765faf420f66963a29900bfd61900c9"},"state":"reviewed"} -->

[English / 原文](ENGINE_JOB_CONTRACT.md)（英語正本）

翻訳元: same PR / SHA-256 `ef941b2d929ae7ce46cf7c889570823b5765faf420f66963a29900bfd61900c9`。状態: `reviewed`。全文の意味・制約・例外を原文と照合し、日本語の可読性も確認済み。

本書はIssue #336の規範となるシリアライズ境界を定義する。現在の設定ファイルを起点とするCLIや内部の実行ディレクトリ構成から独立して、PDFScoreBar engineの1件の同期ジョブを規定する。

Python表現は `src/pipeline/engine_contract.py` にある。この契約は転送方式に依存せず、ローカルCLI、workerプロセス、将来のサービスadapterは、いずれも同じ `JobRequest -> ProgressEvent* -> JobResult` モデルを利用できる。

この変更は `run_pipeline()` の置き換え、HTTP APIの実装、内部の `logs/` / `intermediate/` パスの公開API化を行うものではない。

## 1. バージョンエンベロープと互換性

シリアライズされるすべての最上位レコードに次を含める。

- `schema`: レコード固有のスキーマ識別子
- `contract_version`: 現在は `"1"`

v1のスキーマは次のとおり。

| レコード | スキーマ |
| --- | --- |
| JobRequest | `pdfscorebar.engine.job_request.v1` |
| JobResult | `pdfscorebar.engine.job_result.v1` |
| ProgressEvent | `pdfscorebar.engine.progress_event.v1` |
| EngineError | `pdfscorebar.engine.error.v1` |
| CorrectionSet | `pdfscorebar.engine.correction_set.v1` |

互換性の規則は次のとおり。

- v1の必須フィールドはシリアライズされたレコードに存在しなければならない。デシリアライザーは、省略された必須の通信フィールドをコンストラクターの既定値で補ってはならない。
- 意味を変えずに任意フィールドを追加する変更は、v1内の追加的な変更となる。
- v1の読み手は、オブジェクト内の未知の任意フィールドを無視する。
- 必須フィールドの削除、改名、意味の変更には、新しい契約バージョンが必要となる。
- v1の閉じたenum、operation、stageのレジストリへの値追加は、厳密なv1の読み手にとって破壊的変更となる。そのため、新しいバージョンまたは明示的にバージョン管理された拡張が必要となる。
- 生成側は、デプロイ後にv1フィールドの意味を黙って読み替えてはならない。

`canonical_json()` は、オブジェクトのキーのソート、UTF-8テキスト、不要な空白の除去、NaN/Infinityの拒否により、決定的なシリアライズを提供する。補正レコードは、さらに `correction_id` 順でシリアライズされる。

## 2. 直接呼び出すPython境界

再利用可能な境界を `JobExecutor` protocolで表現する。

```python
result = executor(request, on_progress=handle_event)
```

`src.pipeline.engine_executor.PipelineJobExecutor` は、現在の設定起点のパイプラインを包む参照同期adapterである。終端結果・エラーの構築と公開用final/review成果物の公開を担い、内部の実行・ログパスを呼び出し側の契約から除外する。このadapterにはv1 `CorrectionSet` の直接実行は接続されていない。既存の保持済み成果物を使うreview/correctionワークフローが、引き続き補正実行の具体的な経路となる。

## 3. JobRequest

必須の意味規定は次のとおり。

- `input.kind`: `local_path` または `engine_ref`
- `input.reference`: 呼び出し側に見える入力参照
- 任意の `input.sha256`: 判明している場合の入力元の識別情報
- `output_profile`: `final`、`review`、`debug` のいずれか
- `config_overrides`: 対応する公開の意味的な上書きだけを指定する
- 任意の `corrections`: v1 CorrectionSet
- 任意の `caller_reference`: 呼び出し側の相関付けに使う不透明な値

v1で許可する設定の上書きは、意図的に次だけに限定する。

- `pages`: 呼び出し側が要求する1始まりのページ番号。v1では正規化・重複除去前の生の指定を最大200件受け付ける。
- `output_name`: 呼び出し側に見える出力ファイル名のstem。ファイル名のstemであり、呼び出し側が選択するパスではない。具体的な安全性検証はIssue #338で定義する。

任意のリポジトリ設定キー、モデル実装パス、出力root、worker設定、内部実行ディレクトリのパスは、外部契約に含まれない。

例:

```json
{
  "schema": "pdfscorebar.engine.job_request.v1",
  "contract_version": "1",
  "input": {
    "kind": "local_path",
    "reference": "score.pdf"
  },
  "output_profile": "review",
  "config_overrides": {
    "pages": [1, 2],
    "output_name": "score"
  },
  "caller_reference": "cli-42"
}
```

## 4. 成果物descriptor

JobResultは、内部の実行ディレクトリ構成ではなく、安定したdescriptorで成果物を公開する。

各descriptorは次を持つ。

- `artifact_id`: 結果内での安定した識別子
- `role`: `final.score_numbered_pdf` や `review.manual_correction_input` などの意味上の役割
- `location_kind`: `relative_path` または `engine_ref`
- `reference`: パッケージ内の相対パス、またはengine所有の不透明な参照
- `media_type`
- 任意の `sha256`
- 任意の `coordinate_space`

`coordinate_space` を含める場合、座標の来歴を意味のある比較可能なものにするため、v1では次の空でない文字列メンバーを必須とする。

- `type`
- `origin`
- `units`
- `version`

`relative_path` は、返された成果物パッケージ内に収まらなければならない。絶対パスと `..` によるtraversalは拒否する。したがって、内部の `logs/` や実装パスはAPIの必須フィールドではない。

ローカルのreview引き渡しでは、選択ページのジョブについて、補正対象のアドレスと物理的なPDFページの表示番号を分離する。既存の1始まりの `page_number` は、引き続きパイプラインの補正シーケンス上のページを識別する（補正キーでは `page_number - 1`）。任意の `source_page_number` は、元のPDFページを識別する。これは `source_reference.source_page + 1` から導出し、旧manifestではpage-IDにフォールバックする。GUI、番号付けプレビュー、最終PDFのsummaryは、この物理的な表示番号を使う。任意フィールドのない旧形式の引き渡しでは、従来の表示番号とキーを維持する。`--pages 2 4` の場合、補正キーは `0, 1` のままで、表示番号は `2, 4` となる。

## 5. CorrectionSetと現在の補正の意味

補正はengineへの入力であり、サービスやUIの状態ではない。v1は現在の手動補正の概念を維持し、安定した正規化済みoperationに対応付ける。

| 現在の補正概念 | v1 operation | 安定した対象・値 |
| --- | --- | --- |
| MMRの小節数設定 | `mmr.set_measure_span` | `page/system/measure` + `measure_span` |
| MMRの抑制 | `mmr.suppress` | `page/system/measure` |
| 小節構築の強制 | `measure.force_measure` | `page/system/measure` |
| 小節線の追加 | `barline.add` | `page/bbox` |
| 小節線の削除 | `barline.remove` | `page/bbox` |
| 楽章境界の判断 | `movement_boundary.set_decision` | `page/system` + `boundary` または `no_boundary` |

正規化した補正対象には、既存の永続化された0始まりのpage/system/measureインデックス契約を使う。現在のGUIのstaging用 `measure_construction` にある `interval` フィールドは、v1補正レコードになる前に正規のmeasure対象へ正規化される。これは名称のadapterであり、補正の意味の変更ではない。

### 5.1 来歴と古くなった補正の拒否

すべてのCorrectionSetは、補正対象となる正確な入力元を識別する。

- `source_job_id`
- `source_artifact_id`
- `source_artifact_sha256`
- `source_contract_version`
- `coordinate_space`

補正元の `coordinate_space` には、成果物descriptorと同じ必須の `type` / `origin` / `units` / `version` メンバーを使う。空の座標オブジェクトは、有効な来歴の識別情報ではない。

これらの値のいずれかが補正元の成果物と一致しなくなった場合、engineは補正セットを拒否しなければならない。推測や再スケーリングを行ったり、古い補正を別の成果物・バージョン・座標契約へ黙って適用したりしてはならない。

Pythonの `CorrectionSet.assert_source_matches()` helperが、このgateを実装する。

### 5.2 再処理、冪等性、競合

v1では次を固定する。

- `reprocess_mode = "reuse_compatible_artifacts"`
- `conflict_policy = "reject"`

補正付きリクエストは、新しい `job_id` を持つ**新しいengineジョブ**である。補正セットは元のジョブ・成果物を参照する。再処理は、その識別された元の状態から開始し、互換性のある保持済み成果物を再利用してよい。補正済み出力に同じ補正を累積適用してはならない。

冪等性の規則:

1. `correction_set_id` は、1つの論理的な補正送信を識別する。
2. 同じ入力元に対して、同じ正規化されたCorrectionSet payloadと同じ `correction_set_id` を繰り返し送信することは、冪等な再送となる。
3. 正規化された内容が異なるのに `correction_set_id` を再利用した場合は競合であり、拒否しなければならない。
4. 1つのCorrectionSet内での `correction_id` の重複は無効となる。
5. 同じ元の状態に対して2つのレコードを両立できない場合、executorは暗黙の優先対象を選ばず、セットを拒否する。

冪等性履歴の永続化は、呼び出し側とexecutorの統合部分が担う。この純粋なデータモジュールの責務ではない。

## 6. JobResult

JobResultは常に次を含む。

- `job_id`
- 終端 `status`
- engine/pipeline/sourceの `provenance`
- ページsummary（`requested`、`processed`、`skipped`）
- 成果物descriptor
- 警告
- reviewの判定

任意データには、構造化された失敗、呼び出し側参照、リソースsummaryがある。

終端ステータスは次のとおり。

- `succeeded`
- `review_required`
- `failed`
- `cancelled`

`failed` と `cancelled` にはEngineErrorが必須となる。成功およびreview必須の結果には、EngineErrorを含めてはならない。`review_required` には `review.required=true` が必須であり、その補正元は、同じ結果が返す成果物を指定しなければならない。

### 6.1 代表的な成功例

```json
{
  "schema": "pdfscorebar.engine.job_result.v1",
  "contract_version": "1",
  "job_id": "job-success",
  "status": "succeeded",
  "provenance": {
    "engine_version": "0.1.0",
    "pipeline_version": "dense-v1",
    "source_commit": "abc123"
  },
  "pages": {
    "requested": 2,
    "processed": 2,
    "skipped": 0
  },
  "artifacts": [
    {
      "artifact_id": "final.pdf",
      "role": "final.score_numbered_pdf",
      "location_kind": "relative_path",
      "reference": "final/score_score_numbered.pdf",
      "media_type": "application/pdf"
    }
  ],
  "warnings": [],
  "review": {
    "required": false,
    "reason_codes": []
  }
}
```

### 6.2 警告を伴う成功

警告だけでは成功の終端状態を変更しない。

```json
{
  "status": "succeeded",
  "warnings": [
    {
      "code": "page_skipped",
      "message": "One page was skipped."
    }
  ]
}
```

省略したフィールドの意味は、完全な成功例と同じである。

### 6.3 review必須

```json
{
  "status": "review_required",
  "review": {
    "required": true,
    "reason_codes": ["movement_boundary_ambiguous"],
    "correction_source_artifact_id": "review.manual_correction_input"
  }
}
```

指定した補正元成果物は、同じ結果内に存在しなければならず、内容のhashと座標空間の説明を含めるべきである。

### 6.4 失敗

```json
{
  "status": "failed",
  "failure": {
    "schema": "pdfscorebar.engine.error.v1",
    "contract_version": "1",
    "category": "input",
    "code": "input_pdf_invalid",
    "public_message": "The input PDF could not be read.",
    "user_actionable": true,
    "retryable": false
  }
}
```

production・公開用の結果は `public_message` を使い、診断contextを省く。信頼された診断用途では、明示的に `debug_context` をシリアライズしてよい。

## 7. EngineError

v1の安定したcategoryは次のとおり。

- `invalid_request`
- `input`
- `correction`
- `resource`
- `dependency`
- `cancelled`
- `internal`

`code` はcategory内の安定した機械可読の識別子である。`public_message` は信頼できない呼び出し側に返しても安全なメッセージである。`user_actionable` と `retryable` は明示的なbooleanである。内部例外・パス・stack情報は、任意の `debug_context` だけに含め、既定のシリアライズでは除外する。

Issue #337は、この公開エンベロープとv1終端ステータスの値を維持したまま、[ライフサイクル契約](ENGINE_JOB_LIFECYCLE.ja.md)でライフサイクル・再試行方針を定義する。Issue #338は、別のエラーエンベロープを追加せず、v1終端ステータスを変更せずに、[入力安全性契約](ENGINE_INPUT_SAFETY.ja.md)で信頼できないPDF・パス・ネットワーク・リソースの安全性を定義する。

## 8. ProgressEvent

進捗は構造化データであり、呼び出し側は `pipeline.log` を解析してはならない。

すべてのイベントは次を持つ。

- `job_id`
- 厳密に増加する `sequence`
- `kind`
- 安定した粗粒度の `stage_id`
- 任意の1始まりの `page_number`
- 任意の `completed_units`、`total_units`、`unit`
- 粗粒度の単調時計による経過実時間を表す任意の `elapsed_ms`
- 名前空間付きの機械可読な進捗詳細を表す任意の `detail_code`
- 導出される `terminal`

v1のstage IDは次のとおり。

- `job`
- `input_validation`
- `pdf_render`
- `score_detection`
- `measure_construction`
- `measure_number_recognition`
- `correction_application`
- `numbering`
- `artifact_materialization`

これらは公開する作業単位であり、内部関数名ではない。契約を変えずに実装を変更してよい。

終端の進捗kindは `job_succeeded`、`job_review_required`、`job_failed`、`job_cancelled` である。シリアライズされたイベントは、`kind` から導出した必須のbooleanとして `terminal` を含む。読み手は、boolean以外の値や `kind` と不一致の値を拒否する。終端イベントの後にイベントを続けてはならない。`validate_progress_sequence()` が、ジョブの同一性、厳密な単調増加、終端の順序を強制する。

Issue #339は、[テレメトリ契約](ENGINE_TELEMETRY.ja.md)で追加的なテレメトリの意味を定義する。上記のstage/kindレジストリは変更しない。呼び出し側は、追加的なテレメトリ詳細フィールドの欠落や未知のフィールドを許容しなければならない。

## 9. 来歴とリソースsummary

JobResultのprovenanceには次が必須となる。

- `engine_version`
- `pipeline_version`
- `source_commit`

生成側は、これらの必須値を置き換えずにruntime/modelの識別フィールドを追加してよい。モデル・runtimeのhashが再現性に重要な場合は、記録すべきである。

すべてのadapterがすべてのリソースを計測できるとは限らないため、`resources` は任意とする。v1は、`wall_time_seconds`、`peak_process_tree_rss_bytes`、`peak_gpu_memory_bytes` などの非負で有限の数値フィールドを受け付ける。ライフサイクルの意味は #337が担う。安定した進捗・時間・リソース観測の契約は、[テレメトリ契約](ENGINE_TELEMETRY.ja.md)で定義する。

## 10. 現在の出力・review契約との関係

この契約は、採用済みの製品化の系譜を置き換えず、再利用する。

- #227は `final` / `review` / `debug` 出力profileの意味を定義する。
- #236はreviewパッケージ、手動補正GUI、正規の補正ファイル、補正付き再実行、最終成果物の流れを接続する。
- [手動補正reviewパッケージ（英語・未翻訳）](manual_correction_review_package.md)は、引き続き現在の運用ガイドである。

engine契約は、これらの概念に呼び出し側向けのバージョン付きエンベロープを与える。現在の内部実行ディレクトリは、実装詳細のままとする。

## 11. 検証と保留事項

対象を絞ったテストは、次をカバーする。

- リクエストの決定的な往復変換とv1の追加フィールドの許容
- 未知のバージョンの拒否
- 現在の補正operationの対応付け
- 古くなった補正元の拒否
- 補正ID重複と内部設定パスの拒否
- 成功、警告、review必須、失敗の結果形式
- 公開用に安全なエラーと診断用エラーのシリアライズ
- 単調増加・終端の進捗の意味
- 成果物パスの包含
- NaNの拒否

1ジョブのライフサイクル・キャンセルの意味は[ライフサイクル契約](ENGINE_JOB_LIFECYCLE.ja.md)、信頼できない入力の安全性は[入力安全性契約](ENGINE_INPUT_SAFETY.ja.md)、構造化テレメトリは[テレメトリ契約](ENGINE_TELEMETRY.ja.md)で定義する。Issue #340は、[サービス準備gate](ENGINE_SERVICE_READINESS.ja.md)で説明する参照executorとCI・コンテナ互換性gateを追加する。数値的な挙動が変わる場合、これらのgateはdetector/MMR/番号付けの精度検証の代わりにはならない。
