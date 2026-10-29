# Engineの信頼できないPDFに対する安全性契約

<!-- translation: {"original":"ENGINE_INPUT_SAFETY.md","source":{"sha256":"4a9e69a6d99a57fdb54dfb3fac63e03a93191dd5829d801ed3314761b018bcc6"},"state":"reviewed"} -->

[English / 原文](ENGINE_INPUT_SAFETY.md)（英語正本）

翻訳元: same PR / SHA-256 `4a9e69a6d99a57fdb54dfb3fac63e03a93191dd5829d801ed3314761b018bcc6`。状態: `reviewed`。全文の意味・制約・例外を原文と照合し、日本語の可読性も確認済み。

本書は、バージョン付きengine境界を通して1つの信頼できないPDFを処理するための、規範となるIssue #338の安全性契約である。

初期のローカルDocker配布（#410）では、この契約が強制するのはPDF入力のpreflight上限だけである。ジョブごとの実行時ディスクquotaは提供せず、storage使用量の増加によって実行中のジョブを強制停止することもない。強制的なstorage分離とプロセスツリーのキャンセルは、将来の公開サービスへのデプロイまで保留とする。

この契約は次に重ねる。

- v1のrequest/result/error形式を定める[Engine Job Contract](ENGINE_JOB_CONTRACT.ja.md)
- 実行期限、キャンセル、公開、cleanupの意味を定める[ライフサイクル契約](ENGINE_JOB_LIFECYCLE.ja.md)

現在の設定起点のproductionパイプラインは、運用者・信頼された入力向けのワークフローのままとする。Issue #338は、任意のリポジトリパスや現在のYAML設定を、黙って公開upload APIへ変えるものではない。

再利用可能な実装は `src/pipeline/engine_input_safety.py` にある。

## 1. セキュリティ境界

匿名またはその他の信頼できない呼び出し側が、1つのengineリクエストを無制限の処理や任意のhost filesystem・ネットワークへのアクセスへ転用できてはならない。

将来の信頼できない入力を受ける1ジョブadapterでは、次を行う。

1. 呼び出し側がPDFのbytes、またはstaging済みのengine参照を渡す。
2. adapterがworker所有の入力root以下へ入力をstagingする。
3. engineがパス、byte数、PDF、ページ、予測render上限をpreflight検証する。
4. 可能な範囲でページrendering・モデル推論の前に入力を拒否し、構造化されたv1 `EngineError` を返す。
5. 受理した処理を、worker・コンテナのリソース境界内で実行する。
6. 非失敗の終端 `JobResult` が提示した成果物だけを公開する。

認証、アカウント、課金、全体のrate limiting、IP reputation、queueの公平性、ジョブ間schedulingは、引き続きサービス・control planeの関心事である。それらは、ここで定めるジョブごとの上限の代わりにはならない。

## 2. 現在のruntime監査

現在のリポジトリには有用な安全性の部品があるが、設定起点の経路は任意の公開uploadを受け付けるようには設計されていない。

| 領域 | 現在の挙動 | Issue #338からの帰結 |
| --- | --- | --- |
| PDF bytesの読み込み | `PipelineOrchestrator._run_pdf_to_images()` はPyMuPDFを開く前に `Path.read_bytes()` を呼ぶ | 信頼できない入力向けadapterは、現在の無制限な読み込み方式の前にbyte上限を強制しなければならない |
| PDF解析 | PyMuPDFは入力元の全bytesを開き、`page_count` を公開する | parserエラー・暗号化には、決定的で公開用に安全なマッピングが必要 |
| Rendering | `render_pdf_to_memory()` は `page.get_pixmap()` を呼び、render済みページをlistへ蓄積する | rendering前に予測寸法・ページ別pixel数・総pixel数を制限しなければならない |
| ページ選択 | 既存helperは選択ページのindexを検証する | 信頼できない入力の実行には、さらに文書ページ数・選択ページ数の上限が必要 |
| 入力パス | 設定は運用者指定のパスを受け付ける | 公開ジョブはworker所有の入力root内でのみ解決し、traversal・URL形式の参照を拒否しなければならない |
| Symlink | 一般的な公開入力のsymlink方針がない | 信頼できない入力では、既定でsymlinkをたどらない |
| 出力名 | v1は呼び出し側の `output_name` を公開する | ファイル名のstemだけであり、パスではない |
| 成果物パス | v1成果物の `relative_path` は、すでに絶対パスと `..` traversalを拒否する | この既存契約を維持する |
| 子プロセス | 高負荷stageは、すでに複数の経路でプロセス境界を使う | #337の終了の意味規定には、引き続きworker・プロセスグループの統合が必要 |
| 実行時download | productionモデル・runtime資産はbuild・準備時に明示的に実体化され、runtime resolverがローカル資産を検証する | 通常のジョブ実行はofflineを維持し、必要なローカル資産が利用できなければ失敗しなければならない |
| ログ | 現在の内部pipelineログは、完全なローカルパスや子プロセス出力を含み得る | `pipeline.log` は診断用であり、公開の呼び出し側応答ではない |
| Cleanup・公開 | #337は試行cleanupを定義し、内部パスの存在は公開ではないとする | 上限・入力による拒否は試行の失敗であり、不完全なfinal/review成果物を公開してはならない |

直接のPDF rendererは入力元のhashも計算し、来歴を記録する。これは有用な内部証跡だが、将来の公開結果では、内部の絶対パスを公開metadataへコピーしてはならない。

## 3. ジョブごとの既定方針

`JobSafetyPolicy` は具体的な既定値を提供し、worker・サービスadapterがデプロイ先に合わせてより厳しい値を選べるようにする。

| 制限 | 既定値 |
| --- | ---: |
| PDF bytes | 256 MiB |
| 文書ページ数 | 500 |
| 選択ページ数・生の要求ページ指定数 | 200 |
| ページごとのrender幅 | 12,000 px |
| ページごとのrender高さ | 12,000 px |
| ページごとのrender pixel数 | 64,000,000 |
| 選択ページの総render pixel数 | 1,000,000,000 |
| 入力のsymlink traversal | 拒否 |
| worker所有の入力root | 必須 |

これらはpreflightの拒否上限であり、上限未満のすべてのジョブがあらゆるマシンで処理可能だという主張ではない。デプロイ先はv1通信スキーマを変えずに値を引き下げてよい。引き上げは運用・セキュリティ上の判断であり、後述する将来の公開サービスworker要件を取り除くものではない。

ページ・pixel制限は、`get_pixmap()` の前に、PyMuPDFのページ形状と実際に要求されたrender DPIから計算する。出力の増幅を制限するが、病的なPDFの解析・renderingの計算量が小さいことまでは証明できない。

## 4. PDF preflight契約

`validate_local_pdf()` が、再利用可能なpreflightを行う。

### 4.1 パス・参照チェック

信頼できない `local_path` リクエストでは、次を適用する。

- `http:`、`https:`、`file:` などのURI schemeを持つURL形式の参照を拒否する。
- 制御文字と明示的な `..` パス要素を拒否する。
- 解決後のファイルは、worker所有の `allowed_root` 内に収まらなければならない。
- 既定でsymlink要素を拒否する。
- 最終的に開いた対象は通常ファイルでなければならない。
- 利用可能な環境では、file descriptor単位の通常ファイルチェックより前にnonblockingで開く。これにより、FIFOなどの特殊ファイルが相手待ちでpreflightを停止させることを防ぐ。
- adapterは検証開始前に、信頼できない呼び出し側がstaging済み入力rootを変更できないようにすべきである。

実装は、利用可能なら最終ファイルに `O_NOFOLLOW` も使う。別の主体が親ディレクトリを並行して変更できる場合、filesystem検証だけではすべてのtime-of-check/time-of-use raceを排除できない。そのため、worker所有で攻撃者が書き込めないstaging rootも契約に含める。

`engine_ref` はengine所有の不透明な識別子である。storageへの解決はadapterの責務だが、解決された対象も、rendering前に同じ上限付きPDF検証経路を通らなければならない。

### 4.2 上限付きbyte読み込み

入力を通常ファイルとして開き、`max_pdf_bytes` まで段階的に読み込む。同じ読み込み中にSHA-256を計算する。設定上限を超えるサイズを観測した場合は、PyMuPDFの解析前にジョブを拒否する。staging済み入力を開く・検査する・読む際に想定されるfilesystemの失敗は、生の `OSError` 例外を外へ出さず、安定した `input_pdf_unavailable` エラーへ正規化する。

信頼できない入力向けの上限付きpreflightは、現在の「検証前に `Path.read_bytes()`」という方式を意図的に避ける。

### 4.3 PDFの妥当性と暗号化

次は、決定的で再試行不能な入力失敗となる。

- 読み取り不能・不正・PDF以外の内容
- 0ページのPDF
- password保護・暗号化されたPDF

Issue #338はpassword処理を追加せず、呼び出し側入力の復号も試みない。将来暗号化入力に対応するには、別途明示的なcredential・secret取り扱い契約が必要となる。

### 4.4 ページとrender計画の制限

ページ内容をrenderingする前に、preflightは次を検証する。

- 文書の総ページ数
- 重複除去前の生の要求ページ指定数
- 選択ページ数
- 選択ページindex
- 要求DPIでの予測幅・高さ
- 各選択ページのpixel数
- 選択ページ集合全体の総予測pixel数

検証済みmetadataには、入力元のbasename、SHA-256、byteサイズ、ページ数、選択ページ、render DPI、寸法・pixel数、総render pixel数を含める。workerのローカル絶対パスは意図的に省く。

PDF内の埋め込みobject・画像寸法だけを、十分なセキュリティ指標とは扱わない。vector内容、圧縮stream、その他のPDF構造は、なお高コストになり得る。render出力の上限とworkerの強制制限の組み合わせが、セキュリティ境界となる。

## 5. 出力名とパス構築

v1の `config_overrides.output_name` は、呼び出し側に見えるファイル名のstemだけを表す。

空であってはならず、次を含んではならない。

- `/` または `\\`
- 値全体が `.` または `..`
- ASCII制御文字
- 200 UTF-8 bytesを超える値

ディレクトリはengine・adapterが選ぶ。呼び出し側は `output_name` を使って絶対パス、親ディレクトリ、モデルパス、実行root、一時root、その他の内部の場所を選べない。

既存のv1成果物descriptorは、別の包含規則を維持する。`relative_path` 成果物は絶対パスにできず、`..` を含められない。

## 6. 構造化された拒否category

preflight失敗は、既存のv1 `EngineError` エンベロープへマッピングする。

| 条件 | Category | Code | Retryable |
| --- | --- | --- | --- |
| 不正・読み取り不能PDF | `input` | `input_pdf_invalid` | false |
| 暗号化・password付きPDF | `input` | `input_pdf_encrypted` | false |
| 入力の欠落・通常ファイル以外 | `input` | `input_pdf_unavailable` | false |
| URL・traversal・symlink・root外の入力 | `input` | `input_reference_not_allowed` | false |
| 無効なリクエストページlist | `invalid_request` | `request_pages_invalid` / `request_page_out_of_range` | false |
| 安全でない出力stem | `invalid_request` | `output_name_invalid` | false |
| 入力bytesが方針を超過 | `resource` | `input_pdf_bytes_limit_exceeded` | false |
| 文書・選択ページ数が方針を超過 | `resource` | `input_pdf_page_limit_exceeded` / `input_pdf_selected_pages_limit_exceeded` | false |
| render寸法が方針を超過 | `resource` | `input_pdf_render_dimension_limit_exceeded` | false |
| ページpixel数が方針を超過 | `resource` | `input_pdf_render_pixels_limit_exceeded` | false |
| 総render pixel数が方針を超過 | `resource` | `input_pdf_total_render_pixels_limit_exceeded` | false |
| 実行中にOSが容量不足（`ENOSPC`）を報告 | `resource` | `disk_capacity_exhausted` | true |

設定上限による拒否は、engineの非成功結果となる。変更なしで自動再試行してはならず、不完全なfinal/review成果物を公開してはならない。

## 7. 公開用に安全な情報と診断情報

`InputSafetyError.to_engine_error()` が、preflight失敗をv1エンベロープへマッピングする。

公開応答に含めてよいもの:

- 安定したcategory/code
- 範囲を限定した `public_message`
- ユーザーが対処できるか・再試行可能かの情報
- 結果契約向けに意図的に選択した検証済みmetadata

公開応答に含めてはならないもの:

- host・コンテナの絶対パス
- 意図的に公開する呼び出し側参照またはsanitize済みbasenameを超える、任意の呼び出し側ファイル名
- parserのstack trace
- 子プロセスのcommand line・環境
- モデル・cacheの場所
- 内部の実行・一時ディレクトリ名
- 生の `pipeline.log`

正確なparser例外、内部パス、観測した制限値、stage名、stack traceは、信頼された診断・`debug_context` に存在してよい。`EngineError.to_dict()` は、引き続き既定で `debug_context` を省く。

## 8. Runtimeのネットワークとモデル資産

通常の1ジョブ実行はoffline契約である。

正規のimage・build経路は、すでに管理対象のHOMR、過去のStage-E HOMR、Real-ESRGAN、production CNN資産をimage構築・準備時に実体化する。runtime resolverは実体化済みのローカル資産を検証し、必須資産がなければ失敗する。

`src.common.model_artifacts materialize` は明示的な運用者・buildの操作であり、ネットワークを使ってよい。ジョブexecutorは、ジョブを成功させるためにこの操作、HOMR初期化時download、任意のURL、同等のdownload helperを呼び出してはならない。

サービスworkerは、既定で外向きネットワークを無効にして動作すべきである。第三者依存が予期せずdownloadを試みた場合、その試行は失敗させ、PDFジョブにネットワークアクセスを与えるのではなく、dependency・internal失敗とすべきである。

外部から供給するOMR/MMR/model資産も同様に、信頼できないジョブを受け付ける前にstaging・検証しなければならない。

## 9. 将来の公開サービスworker・コンテナ要件

PythonレベルのPDF検証は必要だが、十分ではない。解析自体や受理したPDF内容が予期しないCPU/RAMを消費し得るため、native PDF/CUDA/runtimeコードも信頼できない入力の境界の一部として扱わなければならない。

任意のPDFを受け付けるworkerは、純粋なhelperの外側で次を提供しなければならない。

- 使い捨ての1ジョブ試行workspace
- worker所有のroot以下へstagingし、実行中はread-only・攻撃者による書き込み不可とした入力
- 実用上可能なら非rootプロセス
- Docker socketや無関係なhost filesystemのmountを持たないこと
- read-onlyのruntime・モデル資産
- CPUとRAMの上限
- デプロイ先に適したGPU配置・VRAM影響の上限
- #337の協調的checkpointに加えた、強制的な試行期限
- temp/intermediate/final staging用の書き込み可能なfilesystem・volumeの上限
- 停止しない子プロセスに対するプロセスグループ・コンテナ終了
- 通常ジョブの外向きネットワーク無効化
- 強制終了後の試行workspaceの隔離・削除

初期のローカルDocker配布は、これらのサービス分離制御を実装しない。`JobSafetyPolicy` が持つのはpreflight入力上限だけであり、`resource_budget()` はそれらの上限を報告するもので、実行時のCPU/RAM/diskを保証しない。以前の `max_attempt_disk_bytes` 方針フィールド、`enforce_attempt_disk_budget()` hook、polling monitorは削除された。これらは使用量を検知できても、内部を制御できないrunnerや子プロセスが書き込みを続ける間、上限を強制できなかったためである。Python呼び出し側はその方針引数を削除しなければならず、互換性用の引数を黙って無視することはない。v1のrequest/result/error通信スキーマは変更しない。

ローカル運用者は、モデル資産、一時ファイル、保持するreviewパッケージ、最終出力に十分な空き容量を用意しなければならない。検証した入力サイズ・ページ数・pixel数は、中間storage総量を制限せず、受理したジョブが利用可能なディスクに収まる保証もない。OSの `ENOSPC` は、best-effort cleanupを伴う `disk_capacity_exhausted` の失敗結果にマッピングされ、不完全な成果物を公開しない。ローカルadapterは、filesystemへの書き込みが可能ならcleanup後にその失敗を永続化する。storageの枯渇・書き込み不可が続く場合、結果ファイルは保証できない。

将来の公開サービスは、quota・volume制限、プロセスツリー全体のキャンセル、確実な回収によって、ジョブプロセスの外でstorageを制限しなければならない。pollingやその高頻度化は、これらの制御の代わりにはならない。

engineは、ジョブ間の公平性や分離を保証しない。サービス・worker poolは、1つのジョブが別ジョブのworkspaceを読んだり、共有リソースを無制限に使ったりできないようにしなければならない。

## 10. 病的な入力と展開による増幅

byte・ページ・pixelチェックは一般的な増幅要因を減らすが、PDF parser・renderの計算量を完全には制限しない。たとえば、深く入れ子になったobject、圧縮stream、病的なvector内容、native libraryのedge caseがある。

したがって、次を適用する。

- preflightは、同じ制約付きworker・コンテナの信頼境界内で実施する。
- rendering・推論をvalidatorの代わりにしてはならない。
- 将来の公開サービスworkerは、preflight成功後にもdeadline/CPU/RAM/disk制限を強制しなければならない。
- workerの強制終了は、有効な最終保護策である。
- 不完全なファイルが残っていても、強制終了された試行は非成功となる。

成功結果を得るためだけに、制限を回避してrender DPIを黙って切り替えたり、要求ページを飛ばしたり、モデル品質を下げたり、detector/MMRの意味を変更したりしてはならない。

## 11. Cleanupと公開

cleanup・公開については、引き続き #337を正とする。

Issue #338による拒否では、次を適用する。

- 決定的なpreflight失敗後に、不要なGPU・モデル推論を起動しない。
- final/review成果物を提示しない。
- engine所有のstaging・一時ファイルをbest-effortで削除する。
- 信頼された運用者方針に従い、上限付きの診断情報だけを保持する。
- engine所有の試行workspace外にある、不変の呼び出し側・入力元の入力を削除してはならない。
- プロセスが強制終了された場合、後の隔離・削除は外側のworkerが担う。

内部ファイルの存在は公開を意味しない。

## 12. 実装状態

Issue #338は、再利用可能な検証・方針の層を導入した。現在の `PipelineJobExecutor` は、設定起点のパイプラインより前にpreflightを呼び、終端の失敗をv1結果へマッピングする。ローカル結果の永続化は、パイプラインrunnerではなく `docker.distribution_job` が担う。

現在実装済みのもの:

- 上限付きローカルPDF byte読み込みとSHA-256
- 不正・暗号化PDFの分類
- ページ選択とrender前の寸法・pixel制限
- 絶対パスを含まない検証済みmetadata
- ローカルパス・root・traversal・URL・symlinkチェック
- 呼び出し側の `output_name` のファイル名stem検証
- v1 `EngineError` へのマッピング
- 実装済み挙動の対象別テスト

引き続き将来のproduction `JobExecutor`・worker adapterが担うもの:

- 試行ごとの強制的なfilesystem・コンテナquotaの設定・強制
- CPU/RAM/VRAM/filesystem/コンテナの強制制御
- worker・コンテナレベルでの外向きネットワーク方針の強制
- #337のプロセスグループ終了の統合

これらの統合は、現在のdetector/MMR/番号付けの精度契約を維持しなければならない。実際にproduction実行経路を変える際は、runtime・GPU検証を行うべきである。
