# Engineの構造化テレメトリ契約

<!-- translation: {"original":"ENGINE_TELEMETRY.md","source":{"sha256":"ad0929b6982b88c89414f9055e701cc86157a7e417fd39ba393ed04b6464ae14"},"state":"reviewed"} -->

[English / 原文](ENGINE_TELEMETRY.md)（英語正本）

翻訳元: same PR / SHA-256 `ad0929b6982b88c89414f9055e701cc86157a7e417fd39ba393ed04b6464ae14`。状態: `reviewed`。全文の意味・制約・例外を原文と照合し、日本語の可読性も確認済み。

> **状態: Engine Job Contract v1に重ねるIssue #339の構造化テレメトリ契約。**
>
> シリアライズされたjob/result/error境界は[Engine Job Contract](ENGINE_JOB_CONTRACT.ja.md)、終端ライフサイクルの意味は[ライフサイクル契約](ENGINE_JOB_LIFECYCLE.ja.md)で定義する。本書は、engineの呼び出し側が使う安定した進捗、粗粒度の時間計測、任意のリソース観測の語彙を定義する。

再利用可能な実装は `src/pipeline/engine_telemetry.py` にある。現在の設定起点の `run_pipeline()` は、明示的に要求された場合に同じ構造化イベントを出せる。これは引き続き設定起点のrunnerであり、`src.pipeline.engine_executor.PipelineJobExecutor` が別のv1 adapterである。

## 1. 設計境界

構造化テレメトリは、engineの観測用の窓口である。別の実行契約になったり、呼び出し側に `pipeline.log` の解析を要求したりしてはならない。

契約は次の3層を分ける。

1. **公開進捗イベント**: CLI、worker、desktop app、サービスadapter向けの、小さく安定したProgressEventレコード。
2. **コンパクトなジョブテレメトリsummary**: `JobResult.resources` への射影やdebug成果物に適した、stageの実時間と任意のリソースpeak。
3. **開発者用profiling・trace**: Issue固有の詳細trace、CUDA profiling、subprocessログ、内部パス。これらは診断用のままであり、公開の進捗フィールドではない。

テレメトリは、detector、HOMR、OMR-DLN、grouping、番号付け、MMR、補正、成果物公開の意味を変更してはならない。

### 1.1 受理とengine開始

v1 engineの進捗streamは、engine実行開始時に始まる。最初のジョブレベルイベントは `job_started` であり、`job_accepted` という `ProgressKind` は意図的に設けない。

リクエストの受付・受理は、呼び出し側、worker、queue、将来のサービスwrapperが担う。wrapperは自身のライフサイクルでaccepted/queued状態を公開してよいが、それを新しいv1 engine `ProgressEvent` kindとしてシリアライズしてはならない。これによりqueueへの受付の意味を1ジョブengine契約の外に保ちつつ、外部adapterに対してaccepted -> startedの境界を明確にする。

## 2. 安定したProgressEvent語彙

Issue #339は、新しいv1 enum値やstageレジストリ値を追加しない。既存の閉じたv1語彙を引き続き正とする。

イベントkind:

- job_started
- stage_started
- stage_progress
- stage_completed
- job_succeeded
- job_review_required
- job_failed
- job_cancelled

Stage ID:

- job
- input_validation
- pdf_render
- score_detection
- measure_construction
- measure_number_recognition
- correction_application
- numbering
- artifact_materialization

これらは呼び出し側向けの作業単位であり、内部関数名ではない。dense detectorのsubprocess名、モデルファイル名、実行ディレクトリ名、Issue固有のprofiler span名を必須の進捗フィールドにしてはならない。

### 2.1 v1の追加的テレメトリフィールド

Issue #339は、ProgressEventに2つの任意フィールドを追加する。

- elapsed_ms: 完了した粗粒度spanまたはジョブ終端イベントの、非負整数の経過実時間。
- detail_code: イベントの詳細を示す、空でない名前空間付きの機械可読値。

どちらも、[Engine Job Contract](ENGINE_JOB_CONTRACT.ja.md)の互換性方針に従う追加的なv1フィールドである。読み手は、どちらかが欠けても引き続き動作しなければならない。

`detail_code` は意図的に開いた文字列名前空間とする。利用側は文書化されたcodeを認識してよいが、将来の未知のcodeも許容し、契約バージョンの失敗と扱ってはならない。

現在の設定起点のcodeには次がある。

| Code | 意味 |
| --- | --- |
| pdf_render.page_prepared | メモリ内のrender・resize済みページが1つ準備できた。そのページのrender完了直後に出力する |
| detection.source_generation_and_scoring | dense/standard detectionの粗粒度span |
| measure_construction.page_completed | 1ページのbase構築・番号付け処理が完了した |
| mmr.page_completed | 準備済みの1ページでMMR batch出力が完了した |
| mmr.skipped_missing_numbering_base | 必須のbase番号付け成果物がなく、MMRがそのページを処理できなかった |
| numbering.page_completed | 1ページの最終番号付け処理が完了した |
| page_skipped.user_excluded | 報告対象stageで、呼び出し側・運用者の除外指定により意図的にそのページをskipした |

未知のdetail codeは、追加的な観測であり、新しい終端状態ではない。

### 2.2 警告とskipページ

ジョブの実行中に有用で、公開用に安全な警告は、安定した名前空間付き `detail_code` と、意味のある場合には `page_number` を付けた `stage_progress` イベントとして提示してよい。進捗streamに任意の診断文、内部パス、stack traceは含めない。

終端での警告保持は、引き続き `JobResult.warnings` が担う。その安定した `code` / 呼び出し側向けに安全な `message` 契約は、[Engine Job Contract](ENGINE_JOB_CONTRACT.ja.md)で定義する。したがって、進捗詳細は観測であり、終端結果の代わりではない。

skipページの詳細にも同じ規則を適用する。`page_skipped.user_excluded` のようなskipだけでは、失敗、review必須、成功のどれも意味しない。終端状態は、ジョブに使うものと同じライフサイクル・結果判定で決定する。

## 3. 順序と終端の意味

v1の順序規則は変更しない。

- 1つのstreamは1つのjob_idを含む。
- sequenceは厳密に増加する。
- 終端イベントの後にイベントは続かない。
- 終端進捗kindは、終端JobStatusから導出する。

`TelemetryRecorder.terminal()` は、次のとおり正確にマッピングする。

| JobStatus | ProgressKind |
| --- | --- |
| succeeded | job_succeeded |
| review_required | job_review_required |
| failed | job_failed |
| cancelled | job_cancelled |

実行期限と明示的なキャンセルの解釈は、引き続き[ライフサイクル契約](ENGINE_JOB_LIFECYCLE.ja.md)が担い、テレメトリが再定義してはならない。

設定起点の `run_pipeline()` を直接呼び、recorderを自身で所有する場合は、正常returnを `job_succeeded`、未処理の通常例外を `job_failed` として報告する。EngineErrorは構築せず、`review_required` を推定しない。対して現在の `PipelineJobExecutor` は、自身の `telemetry_recorder` を渡し、成果物の公開・cleanup後の終端出力を担う。その判定には、JobResultと同じsucceeded/failedを使う。現在はreview_requiredやcancelled結果を生成しないが、これらは引き続きv1 recorder・契約で対応する値である。

## 4. 進捗の単位

ページごとの進捗は、現在の実行境界が事実として表せる箇所だけで報告する。

`page_number` は、そのstageが報告する作業集合内の1始まりの通し番号である。元PDFのページindexが連続するという保証ではない。設定起点のrunnerが順序付きのpipelineページ集合を収集した後は、下流の構築・MMR・番号付けstageが同じページ通し番号を使う。

前処理の作業集合は異なっていてもよい。たとえば、現在の設定起点のrunnerはPDF rendering後に `page_limit` を適用するため、`pdf_render` が報告する準備済みページ数は、後続stageが処理する数より多くなり得る。したがって呼び出し側は、ページ通し番号をstage間で共通の元ページ識別子と扱わず、各イベントの `stage_id`、`completed_units`、`total_units` を組み合わせて使わなければならない。

completed_units / total_unitsがある場合:

- どちらも整数である。
- completed_units <= total_unitsである。
- unitは作業単位を示し、現在は通常pageである。

呼び出し側はcompleted_units / total_unitsを表示してよいが、ページごとの作業量が同じとは仮定してはならない。特にdense source生成やモデル処理はphaseごとのbatchになり得て、ページの処理コストも大きく異なる。UIを動いて見せるためだけに、架空の滑らかな進捗率を出してはならない。

そのため、現在のdense detection境界は、内部の全ページSR・ページ別worker graphを均一なページcounterに見せかけず、粗粒度のscore_detection spanとして報告する。

## 5. 時間計測の意味

elapsed_msは、粗粒度のengine spanを囲む単調な実時間時計を使う。

これは意図的にCUDA kernelの時間計測とはしない。

- 公開テレメトリは `torch.cuda.synchronize()` を呼ばない。
- CUDA eventを挿入しない。
- 非同期GPU実行をprofiler相当のモデル推論時間として読み替えない。

これにより構造化進捗を軽量に保ち、テレメトリを得るためだけにGPU schedulingを変更することを避ける。同期を正しく考慮した詳細な時間帰属は、過去の #281の方法論など、開発者用profilingの作業とする。

例外によって終了したstageは、コンパクトsummaryに `state = aborted` として保持し、誤ったstage_completedイベントを出さない。その後、ジョブは適切な失敗・キャンセルの終端イベントを出せる。

## 6. リソースsummary

リソースsamplingは、**明示的な有効化が必要**である。通常のproduction・設定起点実行では無効とする。

有効にした場合、ResourceSamplerはCUDA同期なしでbest-effortの定期samplingを行う。

- psutilが利用可能なら、再帰的なプロセスツリーのRSSとCPU使用率
- samplingしたプロセスPIDをnvidia-smiのcompute-app集計と対応させた、プロセスツリーのGPUメモリ
- nvidia-smiによるdeviceレベルのGPU使用率

コンパクトな数値射影には、JobResult.resourcesと互換な次のフィールドを使う。

- wall_time_seconds
- progress_sink_error_count
- resource_sample_count
- resource_sample_interval_seconds
- プロセスツリー計測が可能な場合のpeak_process_tree_rss_bytes
- プロセスツリー計測が可能な場合のpeak_process_tree_cpu_percent
- プロセスツリー計測が可能な場合のpeak_process_count
- NVIDIAのプロセス集計が可能な場合のpeak_gpu_memory_bytes
- NVIDIAのdevice samplingが可能な場合のpeak_device_gpu_utilization_percent

すべて、v1 JobResult.resourcesが要求する有限かつ非負の数値である。

samplingは観測用であり、強制quotaの仕組みではない。定期samplingでは短いspikeを見逃し得る。またdevice使用率には、共有GPU上の無関係な処理が含まれ得る。CPU/RAM/GPU/diskの強制上限は、引き続き[入力安全性契約](ENGINE_INPUT_SAFETY.ja.md)と[ライフサイクル契約](ENGINE_JOB_LIFECYCLE.ja.md)に基づくworker・コンテナの責務である。

実装は意図的にpsutilを任意依存とする。任意の計測元がない場合、engineジョブを失敗させず、対応するpeakフィールドを省く。

## 7. コンパクトsummary

`TelemetryRecorder.summary()` は次を生成する。

- schema pdfscorebar.engine.telemetry_summary.v1
- job_id
- 安定したstage ID、経過milliseconds、completed / aborted状態を含む粗粒度のstage_spans
- 数値のresources object

summaryに内部実行ディレクトリのパス、モデルパス、subprocessのcommand line、生ログを含めない。現在のPipelineJobExecutorは、数値のリソース射影をJobResult.resourcesへコピーし、debug profileでは、より詳細なsummaryをdebug成果物として保持する。

進捗sinkの失敗は楽譜処理から分離し、progress_sink_error_countへ計数する。観測側の失敗によって、それ以外は有効な楽譜処理を黙って異なるdetector/MMR結果にしてはならない。

## 8. 現在の設定起点の統合

`src.pipeline.main.run_pipeline()` は、現在、任意引数として次を受け付ける。

- on_progress
- telemetry_summary_path
- sample_resources
- resource_sample_interval_seconds
- telemetry_recorder（executor所有のrecorder）

どれも要求しなければTelemetryRecorderを構築せず、既存のpipeline実行経路が既定のままとなる。executor所有のtelemetry_recorderと、on_progress、telemetry_summary_path、sample_resourcesは同時指定できない。このモードでは、終端出力、recorderのclose、summary保持をexecutorが担う。

リポジトリ内CLIは、対応する明示的有効化用flagを公開する。

~~~bash
python -m src.pipeline.main \
  --config configs/dense_full_pipeline.yaml \
  --progress-jsonl artifacts/progress.jsonl \
  --telemetry-summary artifacts/telemetry.json
~~~

リソースsamplingは別途有効化する。

~~~bash
python -m src.pipeline.main \
  --config configs/dense_full_pipeline.yaml \
  --progress-jsonl artifacts/progress.jsonl \
  --telemetry-summary artifacts/telemetry.json \
  --sample-resources
~~~

明示的なtelemetry summaryパスなしでリソースsamplingを有効にした場合、設定起点のrunnerは、sample値を捨てずに実行ディレクトリ内の `telemetry.json` としてコンパクトsummaryを保持する。

JSONL進捗は機械可読であり、console・ファイルログの文言から独立している。診断用pipeline.logは引き続き開発者に役立つが、呼び出し側の状態契約ではない。

## 9. 検証と非影響契約

対象を絞ったテストは次をカバーする。

- 追加的なProgressEventのシリアライズ
- 厳密なsequence・終端の挙動
- 正確なJobStatus -> 終端ProgressKindマッピング
- 終端後にイベントがないこと
- 中断stageの挙動
- 進捗sink失敗の分離
- JobResult.resourcesの互換性
- 現在のrun_pipeline()の既定無効の挙動
- 現在の設定runnerによる成功・失敗の終端出力

テレメトリ統合は、モデル・runtime選択、detector閾値、画像形状、grouping/MMR/番号付け規則、成果物公開規則を変更しない。既定の実行ではrecorderを構築しない。明示的に有効にする粗粒度の時間計測はhostの単調時計だけを使う。任意のリソースsamplingは観測用のhost・NVIDIA問い合わせを使い、GPU処理を同期しない。

現在の実装はpipeline・orchestratorに触れるため、テレメトリが既定無効であっても、リポジトリ検証方針は該当するpipeline smokeを要求する。このsmokeが検証するのは接続・runtime互換性であり、数値精度の変更を主張することとは異なる。

candidate生成、routing、数値的挙動、出力の意味が変わらないため、この観測だけの契約変更でdetector/full68精度再実行を行う因果的な必要性はない。今後、数値に敏感なGPU kernel内へテレメトリを移す、プロセス・モデルの寿命やschedulingを変える、出力を変える場合は、[検証方針（英語・未翻訳）](dev/VALIDATION_POLICY.md)に従って検証分類を見直さなければならない。
