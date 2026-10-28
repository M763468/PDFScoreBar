# Issue #447 調査結果と最終判定

[Issue #447](https://github.com/M763468/PDFScoreBar/issues/447)の性能調査を、元のAcceptance Criteriaに対して充足と判定する。
これは調査完了の判定であり、最適化のproduction採用・全入力の精度保証ではない。
PR #455のレビュー後に人が最終確認する。マージ・Issueクローズはこの作業では行わない。
production本体・閾値・モデル・依存関係は変更していない。

## 結論と優先順位

主な遅延はdetectionにあり、最新の対照3ページではwarm E2E中央値244.755秒のうち、
同じ実行のdetection telemetry中央値が226.248秒だった。その内部ではSRが約119秒、
source workerが観測上94–99秒の規模を占める。これらの包含・観測区間を足して新しいE2Eを作らない。
coldではSRのcompile/cache初期化が増大し、sourceの並列化だけではその負担は消えない。

1. **compiler-cache寿命管理：[既存 #454](https://github.com/M763468/PDFScoreBar/issues/454)を維持。**
   single-pageのcold/warm反復でpaired差の中央値122.373秒。短命jobに特に価値がある。
   invalidation・権限・同時jobの契約は実装Issueで検証する。compile無効化への置換は不採用。
2. **SR終了後のresource制限付きページ並列：[新規 #458](https://github.com/M763468/PDFScoreBar/issues/458)。**
   warm E2Eを8.59%、coldの観測値を2.93%短縮。RAM/VRAMとCPU workが増えるため、admission・順序・異常終了の設計が必要。
3. **job内OMR再利用：[新規 #459](https://github.com/M763468/PDFScoreBar/issues/459)。**
   warm E2Eを6.91%短縮し、並列方式より低メモリ。coldは0.66%遅く、改善を確認できなかった。
   deployment UID/cacheで利益が変わるため、その再確認と失敗境界を採用前の条件にする。
4. **組合せは候補として保持し、専用Issueを作らない。**
   warm 11.32%短縮で今回最速だが、並列単独からの追加は2.99%。#458/#459の単独gate後に価値を判断する。
   decode共有・native化も専用Issueを作らない。現時点で実装効果を確定する証拠が不足している。

## 元のAcceptance Criteriaとの照合

| 元Issueの条件 | 調査としての判定 | 証拠と範囲 |
| --- | --- | --- |
| production経路・固定入力・モデル/環境・コマンド・成果物のprovenance | 充足 | source/image/runtime/input/model hashes、各runのconfig・argv・script snapshot、下記証拠索引。最終整理時もdevelopとの差はdocs/translation検証のみ |
| trace OFF E2E、主要段階、cold/warm、CPU/GPU/VRAM/RAM、Blocked理由 | 充足 | single-page cache反復3組、3ページE2E 12回、native/telemetry/resource観測。完全なGPU-PID・厳密な待ち帰属はBlockedと明記 |
| 無駄処理/I/O・ページ並列・batch・native候補を現在の実測で判定 | 充足 | 次のボトルネック表、I/O/import/reuse/compiled-batch PoC。不成立・未確定を保持し、根拠のない移植を推奨しない |
| PoCの同条件比較と下流影響、未検証の採用可判定をしない | 充足 | 同じsource/config/models/input/cache条件、strict source/番号/MMR比較、実際の補正再生と故障注入。3ページ以外の品質は未保証 |
| 優先順位付きbacklog、実装価値があるものだけ後続Issue | 充足 | #454維持、#458/#459作成。組合せ・decode・nativeは非Issue化の理由を記録 |

Issueの調査条件にある「可能な範囲の測定・Blocked理由の明示」を適用した判定である。
未確定の精度・OOM・hang・cancel復旧をPassedへ読み替えていない。後続Issueの採用gateは未達成のまま引き継ぐ。

## 計測の層と時間の読み方

| 層 | 何を計ったか | 包含・限界 |
| --- | --- | --- |
| trace OFF Docker E2E | fresh container起動から終了までのhost perf_counter | 主指標。imports/model/teardown込み、observer teardownは別。既存render画像から開始し、PDF renderとservice PDF exportは含まない |
| 同じE2Eのtelemetry stage | detection、MMR、番号等のcoarse区間 | E2E内部の区間。SR/sourceはdetectionに内包される。stage外の残差を全てI/Oやsubprocessへ割り当てない |
| native worker timer | SR batch本体・初期化等 | subprocessの起動/終了全体とは違い、親区間に内包される。別runのcomponent値でE2Eの排他的段階を埋めない |
| process samples | workerが観測されたresidency、cgroup CPU/メモリ/I/O | 約0.2秒周期。親子・並列workerは重複。RSS合計は共有mappingを重複計上し得る。CPU-sはwall秒ではない |
| trace ON / standalone PoC | 同期付き詳細trace、独立component/import/tile比較 | 診断と仮説の切分け用。trace OFFとの役割を分離。nested spanや独立wallを足し算しない |

例えば同じrunのdetection 228.562秒に、その内部のSR 118.999秒を加算してはならない。
source観測94–99秒にもnested HOMR/OMR childが含まれる。source値に各child時間を加算するのも誤りである。
CUDA eventとhost clockは校正差があり、引き算で「CPU待ち秒」を作らない。primary E2Eの時計や合格基準は変更していない。

## ボトルネックの場所・原因・改善可能性

数値は記載したcohort/層に限る。原因の「確認済み」と「未確定」を分ける。

| 場所 | 実測時間・層 | 遅さの根拠/原因 | 改善判断・未確定 |
| --- | --- | --- | --- |
| detection全体 | 最新production 3ページwarm telemetry 223.934/228.562秒、cold 341.775秒 | E2Eの主要部分。SRと2系統HOMR/OMR sourceを含む | 以下の子区間と重複。Dense/Probe/CNN・groupingそれぞれのexclusive時間は確定していない |
| SR compile/cache | single-page 3組のcold中央値233.242秒、warm111.652秒（いずれもE2E） | 空compiler cacheと再利用cacheでpaired中央値122.373秒差、cold時CPU work増。processは毎回fresh | #454。OS/driver cacheはflushしておらず、差の全てを特定のcompiler関数に帰属しない |
| SRのwarm処理 | 最新production 3ページnative batch 118.899/118.999秒、cold236.358秒 | x4 RRDB/tile処理・画像read/write・初期化を含む。single-page trace ONではenhance43.76秒、init7.18秒がenclosing subprocess56.60秒に内包 | compiled batch=2は固定2tileのwarm差1%未満で5%改善gate Failed、reserved VRAM約1.41→2.55 GiB。full-page batch2の品質/速度は未検証で、永久不採用とも断定しない |
| page-source処理 | 最新production 3ページのhost観測94.074/98.736秒。初回source parentは各34.20/35.85/34.65秒 | source内の元画像HOMR・x4 HOMR・OMRのprocess/import/model作業を逐次反復。並列PoCが同条件E2Eで改善 | #458。観測時間はexclusive stageではない。2-workerでRAM/VRAM・CPU増、他shape/device・OOM/hang/cancel復旧は未検証 |
| 元画像/x4 HOMR | 初回E2Eの元画像worker-native約9.26–10.46秒/page、x4 child residency13.29–14.72秒/page。独立x4診断12.63秒 | 独立診断ではimports2.19秒、predictor9.95秒、nested read1.57秒・session構築0.61秒。NN/nativeと準備の双方がある | 独立診断をE2Eへ代入しない。ONNX非同期spanは重複し、exclusive GPU割合・特定Python loop支配は確定せず |
| OMR-DLN | 初回E2E child residency約9.64–9.84秒/page。独立診断7.98秒 | 独立診断のruntime import2.11秒、lazy YOLO class解決3.39秒、body2.48秒（read1.51秒・model構築0.075秒・first predict0.90秒を含む）。worker時間全体がNN推論ではない | #459。3-page component中央値27.321→12.485秒、実E2E warm244.755→227.849秒。rootのbytecode cache、predictor state/長文書・失敗回復は未検証。component短縮をE2Eから引かない |
| 画像I/O・変換・hash | single-page SR trace read0.09/write1.22/hash0.014秒。独立x4 HOMR/OMR read約1.5秒ずつ | large SRを複数consumerでdecode。bytecode権限でも起動負担が変化。physical I/O counterはcache hit/logical read/decode時間を示さない | decode共有は候補だが、IPC/所有権/メモリ/下流gate付きE2E PoCは未実施。0.014秒のhash除去よりprovenance維持を優先 |
| MMR/RapidOCR | 最新production warm telemetry11.978/12.013秒/3pages、cold11.414秒。初回13.05秒/266.46秒E2E | classifier/OCRは既にjob内で再利用。ページ013に3件、014に6件の実skip指定 | 閾値/retry省略は未評価。モデル内部のexclusive費用・大きな高速化余地は未確定。専用Issue化しない |
| base/final numbering・artifact | 最新production base0.780–0.845秒、final0.789–0.858秒、artifact0.084–0.090秒 | 3ページcohortでは小さいcoarse stage。geometry処理全体のCPU hotspotを意味しない | invalid cProfile結果を除くと、native移植を正当化する支配的な純Python loopの証拠がない。native化Issueは作らない |

## 最新の同条件E2E比較

全て同じ3ページ・モデル・閾値、trace OFF、fresh container、UID1000。warm各2回、cold各1回。
warm B/P/O/O/P/Bは同じcompiler-cache seedの私有copy。coldはそれぞれ別の空Inductor/Triton cacheで、OS/driver cacheはflushしない。
単独候補の事前warm速度/品質/resource/実Phase C gate後に、組合せwarm2回・cold1回を実施した。

| 条件 | warm実測2回（秒） | warm中央値（短縮率） | cold実測1回（短縮率） | RAM最大GiB / device VRAM最大MiB |
| --- | --- | --- | --- | --- |
| production | 247.064 / 242.446 | 244.755（基準） | 359.970（基準） | 6.675 / 3464 |
| source 2-worker | 224.243 / 223.228 | 223.736（8.59%） | 349.407（2.93%） | 8.959 / 6605 |
| OMR再利用 | 227.500 / 228.198 | 227.849（6.91%） | 362.361（−0.66%、改善せず） | 4.794 / 3451 |
| 組合せ | 217.818 / 216.267 | 217.042（11.32%） | 336.847（6.42%） | 8.931 / 6593 |

組合せの追加短縮はsource並列単独比2.99%。独立した改善率やcomponent時間を加算していない。
OMR coldの遅い観測も除外せず保持する。cohort後半の組合せと前半の対照には時間帯差の限界もある。
2回/1回から信頼区間・全入力での改善・production採用を保証しない。

single-page cache反復3組は別cohortで、cold230.822–243.139秒（中央値233.242）、warm108.449–112.382秒（中央値111.652）。
初回single cold219.45/warm103.25/trace ON104.22秒と初回multi266.46秒も履歴として保持するが、今回値とpoolingしない。
単一/複数ページはページ集合・cache形状履歴が違い、両者の比をページ並列の因果改善率にしない。

## 正確性・失敗・未確定事項

12回のE2Eはordered original/x4 predictions、decoded staff/connector masks、OMR予測、detector geometry、
manifest順序、base/final番号・movement metadata、MMR mapping/targets/skips、filters/補正関連が一致した。
実際のPhase Cで手動0・2ページ目reset1・3ページ目継続を再生し、Phase A/Cの小節線remove/add編集も全12回一致。
これらのreplayには既存の有効なdetector/MMR出力を再利用し、timed E2Eの推論省略には用いていない。

OMR exit7、exit0だが予測欠損、2-worker source exit7は故障点到達・上位への失敗伝播・最終番号非公開・source child終了を確認した。
OOM・hang・forced kill・user cancelの復旧/latency、root E2E、他shape/ページ数、長文書のstate/メモリ増大はNot run。
shared modelやthresholdを変えて品質を補償しておらず、全入力accuracyは未保証。実装Issueのgateとして残す。

完全なGPU process attribution/powerと厳密なCPU/GPU待ち帰属はWSL/clock制約でBlocked。
全benchmarkは直列で外部GPU競合を観測していないが、OS全体の排他性を証明したわけではない。
P1に短いGPU-free pytest execがあり、host CPU無競合も主張しない。cgroup RAMはfile cacheを含み、CPU-sはwallと混同しない。

## 失敗・無効化した証拠の扱い

| 証拠 | 判定・理由 | 最終結論での用途 |
| --- | --- | --- |
| SR compile無効化 | final番号等は一致したが、x4 source予測/decoded maskが変化しstrict semantic gate Failed | 採用不可。別の閾値/指標で救済しない |
| eager batch2 / compiled batch2 | eager speed gate Failed。compiled固定tileでも5%改善gate Failed | 今回の条件で後続Issueを作らない。full-page効果未検証 |
| 初回parallel47.54秒 vs retained sequential68.85秒 | 異なるharness/観測層の探索値 | 同条件component ABBAと今回E2Eで置き換え。初回比率を因果証拠にしない |
| cProfile call accounting | root欠落・wallを超すcumulative等で定量値のvalidity Failed | hotspot順位の根拠から除外。無効ログ自体は保持 |
| GPU/host絶対時刻をhour offsetで合わせた診断 | 校正差があり撤回 | summary-v1-driver-clock.jsonを履歴保持し、最終CPU/GPU待ち値には使わない |
| historical process samplesの暗黙選択 | Codex P2で修正済み、run-local優先・legacyは明示flagのみ | 今回runに別試行の観測を付けない。元run再scoreと回帰testを保持 |

## 証拠・再現性の索引

固定runtime sourceは`2ac7d5245fe65dbfa2093b4e0d60119c58192f86`、最終整理時のdevelopは`658e2e6e`。
その差分はdocs/translation検証のみ。configは[dense_full_pipeline](../../configs/dense_full_pipeline.yaml)、
入力はShostakovich-Sym5-Va page013 / pages012–014、GPUはRTX4060 8188MiB、driver610.88、8 logical CPUs、UID:GID1000:1001。
Imageは`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`、
runtime fingerprintは`d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97`。
torch2.14.0+cu130 / CUDA13.0 / cuDNN92400 / ORT GPU1.24.4。image build labelとmounted production sourceのidentityは区別する。

| 仮説・記録 | script/commit → 結果 → 判定 |
| --- | --- |
| 初回E2E・モデル内部診断 | [初回profile](issue447-initial-profile.md)、[初回詳細](issue447-initial-results.md)、[初回JSON](issue447-results.json)。f29f1864/b5e03b2c、analyze.py/component_poc.py → trace OFF/ONと単体内訳 → 上記の層別診断 |
| cache反復・同条件source・compiled tile | [継続詳細](issue447-deepening.md)、[JSON](issue447-deepening.json)。c052d09a/812486d6、deepening_components.py/deepening_analyze.py → cache3組・source ABBA・tile gate → #454と候補選定 |
| 実E2E・補正/故障 | [E2E詳細](issue447-e2e-candidates.md)、[JSON](issue447-e2e-candidates.json)。harness488193d2、OMR実行前hook修正99098a97、record991282f6 → e2e_candidate_matrix.py、omr_reuse_poc.py、e2e_*replay/fault/summarize.py → 12run/補正/故障 → #458/#459 |

[元contract](../../tools/issue447/contract.json)、[継続contract](../../tools/issue447/deepening_contract.json)、
[E2E contract](../../tools/issue447/e2e_candidates_contract.json)、[補足validation](../../tools/issue447/e2e_supplemental_contract.json)を保持する。
各runのargv/config/cache inventory/script snapshot/hash、source/input/model identity、resource samplesは`logs/issue447/`内。
`runs/<label>/provenance.json`と`e2e-candidates/matrix.jsonl`、`validation/commands.json`から実行を辿れる。
大きなmodel/data/raw出力はgitへ追加しない。入力/selected OMR/CNN重み・image内SR/HOMR重みのpost-checkも一致した。
元の出力を上書きせず、新しいlabel/保存先で再現する。

## 最終検証と人による確認

最終整理のtested commit/commandsとCodexレビュー結果はPR #455の最新validation報告、および
`logs/issue447/finalization/`のreview/validation記録に保持する。production差分がないため大規模再計測やfull68は行わない。
前段の56 tests/12 E2E/補正・故障の結果は各記録の元commitに属する履歴であり、今回の再実行Passedとは呼ばない。
今回実行する必要最小限のCPU/static検証はPassed/Failed/Blocked/Not runを分けて報告する。

人が確認する点は、元ACと上記判定の妥当性、後続#454/#458/#459のscope/数値gate、限定入力/UIDの制約を了承して調査を閉じられるかである。
PRをレビュー可能にすることはmerge/Issue closeの承認やproduction採用を意味しない。
