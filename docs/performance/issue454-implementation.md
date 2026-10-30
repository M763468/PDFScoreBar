# #454 maintained launcher implementation

今回のproduction導入はmaintained pipeline/launcherに正式実装しdevelopへ統合できる状態にすること。
実deployment未決定は実装・ローカルE2E検証の延期理由にはしない。
旧[調査判断](issue454-cache-lifetime.md)は経緯として保持し、その採用延期判断は本記録で撤回する。
旧[契約v1](issue454-contract.json)を保持し、[v2](issue454-contract-v2.json)でdeployment確定という
採用条件だけを除いた。20%改善、各UID/入力の3 cold/warm組、資源/semantic gatesは維持する。
代表環境はローカルDocker、将来deploymentの性能保証とは区別する。

## Lifetime / ownership

`PDFSCORE_SR_COMPILER_CACHE` を指定したときのみmanaged cacheを利用する。
指定しない場合のSR処理・モデル・閾値・compile方式はそのまま。
`make run-pipeline CONFIG=...` とcanonical smokeは同じlauncherに統合する。
`--pipeline-only` はpreflight後にcustom configを実行し、smoke専用のaccuracy checkを省く。

operatorはcanonical絶対パス・ローカルfilesystem上の実行UID所有0700 rootを事前に作成する。
例 (non-root、互換imageと外部モデルは通常のresolverで検証する):

```bash
mkdir -m 700 /absolute/private/sr-cache
PDFSCORE_SR_COMPILER_CACHE=/absolute/private/sr-cache \
DOCKER_EXTRA_ARGS='--user 1000:1001' \
make run-pipeline CONFIG=configs/dense_full_pipeline.yaml
```

root実行はroot所有の別rootを事前作成する。既存cacheへのchownや暗黙の移行は行わない。
Docker外からの`docker exec`経路ではhost側環境変数は自動転送されない。
既存長寿命containerを使う場合はoperatorが同じprivate rootをmountし、container側で
`PDFSCORE_SR_COMPILER_CACHE` と実際のimmutable `PDFSCORE_DOCKER_IMAGE_ID` を明示する。
既存containerのcacheを自動発見して取り込むことはしない。

identityはimage/compiler/runtime、GPU/driver、weight digest、SR設定、実行UID/GIDとsource bytes。
source全Pythonファイルhashは保守的で、無関係なsource変更でもcoldになる。
manifest/inventory照合とexclusive nonblocking flockをSR処理全体に適用する。
同一identityの競合は明示的失敗とし、再試行は呼出側の責任。別identity間のGPU schedulingは別の責務。
破損・権限不足・未知の内容・dirtyな前回writer・compiler error suppressionはfail closed。
namespaceのreuseとcompiler counter上のhit/missを区別し、worker resultに両方のprovenanceを保存する。

**無効化:** operatorが新しい空rootを選択する。旧rootは保持し、manifestを編集して使い回さない。
retention容量/期間、job停止後の手動cleanupはoperator管理。自動削除は実装しない。
全writerが同じlock契約を守る私有cacheのみサポートする。NFS/分散cacheや第三者と共有する
実行可能cache、稼働image/runtimeの内部書換えは対象外。

## 固定候補の検証

固定候補は `b75c043f5f02806c2a0bfbb7dd1604d58777f19e`。
imageは `sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`。
RTX4060 8 GiB / driver610.88 / torch2.14.0+cu130 / Triton3.8.0 / CUDA13.0で測定した。
worktreeは `.worktrees/issue454`、各E2Eは直接 `/workspace` にmountしたfresh container。
rootは0:0、non-rootは1000:1001。実行時の全tracked diffは空だった。
元のRealESRGAN_x4plus weight SHA-256、SR設定、compile mode、全source digestはrun-local identityに残す。
最終報告の追加変更はdocs/集計器/テストのみで、評価候補から `src`・launcher・Makefileは変更していない。

### 性能と資源

各条件3 cold/warm組、主指標はtrace OFFのDocker起動から終了までのE2E wall。
identity/lock/inventory確認も含み、observer終了処理は別計測。OS/driver cacheはflushしない。
#447と同じ保持済みrender画像からpipelineを開始し、共通のhost準備/preflight、PDF render、
serviceのPDF exportは主指標に含まない。`make run-pipeline`全体のwall短縮率とは区別する。
[全観測と資源集計JSON](issue454-results.json) に各runのCPU/RAM/GPU/VRAM/I/Oを保持する。

| UID / 入力 | cold中央値 [範囲] 秒 | warm中央値 [範囲] 秒 | 中央値比の短縮 | paired saving中央値 秒 |
| --- | --- | --- | --- | --- |
| root / page013 | 232.047 [221.935–232.511] | 99.534 [97.701–101.126] | 57.1% | 131.385 |
| root / pages012–014 | 348.418 [347.499–369.610] | 224.880 [222.048–225.438] | 35.5% | 125.451 |
| non-root / page013 | 223.917 [223.516–226.291] | 104.708 [103.894–105.734] | 53.2% | 119.622 |
| non-root / pages012–014 | 359.791 [357.642–364.530] | 241.060 [240.203–242.142] | 33.0% | 119.588 |

全4 cohortで事前固定した20%以上短縮を満たした。これは現在のmaintained pipelineで
managed cacheを空から使う場合と再利用する場合の比較であり、未稼働のdeploymentの測定ではない。
別のページ集合、compile方式、source並列化/OMR再利用候補の効果と加算しない。

cold全12 jobでFX graph miss=3/hit=0、warm全12 jobでhit=3/miss=0。
全jobでcompiled-graph gateを通過し、graph breakなし。
最大sampled VRAMは3460 MiB（7 GiB screen内）、cgroup memory peak最大4.906 GiB（cap16 GiB）。
CPU-s中央値はroot single 327.68→183.75、root multi 579.99→443.58、
non-root single 329.24→191.93、non-root multi 599.52→464.89。
物理readはOS page cacheの影響で多くが0であり、論理I/Oやdecode workが0とは解釈しない。
cgroup RAMにはfile cacheを含み、CPU/I/O final sampleはprocess終了直前までの観測である。

`provenance-audit.json`で全24 jobのcommit・実image ID・16 GiB cap・compiled gateを確認した。
GPU process名はWSL上でNot Foundとなるが、観測PIDは各jobのprocess samplesに全て対応した
（`gpu-pid-audit.json`）。他の稼働containerはidleの開発用containerのみで、既知の外部GPU競合なし。
これは完全なhost GPU排他や厳密なkernel busy時間の証明ではない。

### semantic / quality

SR digestとdecoded pixels、ordered source predictions、decoded staff/connector masks、
最終detector geometry、ordered pages/systems/measures、base/final numberingとmovement metadata、
MMR targets/skips/geometry、filters/correction statsを、scopeごとのroot cold referenceに対して
全24 jobで厳密比較した。従来契約のrun pathとdisplay-only OCR score comment以外に許容差はない。
全項目一致。#447の保持済み固定補正座標を再利用して12 multi-page出力に実補正を適用し、
barline削除/追加、manual zero、movement reset、ページ間連続性、補正後出力も全件一致した。
canonical GPU accuracy smokeはGT85/一致85、hard FP0/FN0/soft0。

### 検証記録

共通prefix `D` は
`docker exec --user 1000:1001 -w /workspace/.worktrees/issue454 -e PYTHONPATH=/workspace/.worktrees/issue454`
（Git依存suiteには `GIT_DIR=/workspace/.git/worktrees/issue454` と
`GIT_WORK_TREE=/workspace/.worktrees/issue454` も付与）、containerは
`pdfscore_pipeline_pytest_dev`、interpreterは `/opt/venv_pipeline/bin/python`。
この開発imageは `5311cf22…`、GPU/E2E/再集計には上記互換image `5c5979a2…`を使った。
以下のartifact rootは `logs/issue454/final/`。

| Check | 今回の状態 | Command / exit / evidence |
| --- | --- | --- |
| 最終候補fast/SR/Docker境界 | Passed | `D ... -m pytest <Makefile FAST_TESTS> tests/test_sr_compiler_cache.py tests/test_issue284_sr_batch_contract.py tests/test_docker_runtime_contract.py -q`; 180 passed、exit0、`validation/fast.log` |
| root cache focused | Passed | 同じexecを `--user 0:0` にして `-m pytest tests/test_sr_compiler_cache.py -q`; 18 passed、exit0、`validation/focused-root.log` |
| 実Docker権限/破損/異常終了/排他 | Passed | `python3 tools/issue454/docker_negative.py`; exit0、`negative/results.json`。別containerでbusy拒否、writer終了後reuse、UID混在拒否を確認。専用fixtureのみ変更 |
| shell/help | Passed | `bash -n scripts/docker_runtime_validation.sh`、`bash ... --help`、`make help`; exit0、先行attemptの `logs/issue454/implementation/validation/`。以後launcher差分なし |
| 固定候補GPU smoke | Passed | `PDFSCORE_SR_COMPILER_CACHE="$PWD/logs/issue454/final/cache/root-smoke" DOCKER_EXTRA_ARGS='-v /home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2:/workspace/data/evaluation2:ro' make verify-gpu-smoke`; exit0、`validation/gpu-smoke.log`、`validation/smoke-artifacts/` |
| 固定24 E2E job | Passed | `bash tools/issue454/run_matrix.sh`; exit0、`matrix.log`、`runs/*/{provenance,result,container-inspect}.json` とresource samples |
| strict semantic/resource/performance再集計 | Passed | `docker run --rm --user 1000:1001 --mount type=bind,source="$PWD",target=/workspace --mount type=bind,source=/home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2,target=/workspace/data/evaluation2,readonly -w /workspace -e PYTHONPATH=/workspace --entrypoint /opt/venv_pipeline/bin/python <image> -m tools.issue454.analyze`; GPU指定なし、exit0、`analysis.json`、`validation/rescore/analysis.log` |
| correction replay | Passed | 同じGPUなしDocker commandのmoduleを `tools.issue454.correction_replay` に変更; exit0、`correction-replay/summary.json`、`validation/correction.log` |
| 集計器修正test | Passed | `D ... -m pytest tests/test_issue454_analysis.py -q`; 2 passed、exit0、`validation/rescore/tests.log` |
| 初回集計 | Blocked | 同じanalyzer commandがsingle-pageに存在しないcombined番号JSONを要求してexit1。`validation/rescore/original-blocked.log` に保持。`src/pipeline/orchestrator.py` の既存契約に従い、singleは完全なper-page番号JSONを比較するよう修正し、同じ保持出力を再集計。比較項目・許容差・対象は変更なし |
| full68 | Not run | compile/model/閾値/数値処理は変更せず、今回の合意された代表入力semantic/補正gateとcanonical精度smokeを通過。計測だけのfull68再推論はIssue scope外。全データセットの精度保証は主張しない |

smoke wrapperとpipelineのdefault出力は検証後Issue rootへ移動した。captured log内の
`logs/system/` / `logs/full_pipeline_runs/` pathは実行時の記録として保持する。

先行attemptは別root `logs/issue454/implementation/` に保持した。
`32388a83`のGPU smokeはDynamoが自動設定するcache envとの衝突判定でFailed。
明示設定をDynamo初期化前に検査する `b1686627` はsmokeを通過したが、counterを記録するだけでは
無compile/部分compileを成功扱いし得るため、反復途中でdriverを止め、実行中jobの結果まで回収した。
最終候補ではguardを追加して別の新規rootで全24 jobを測定した。旧値は最終統計に混ぜない。
#447の性能/品質はHistorical evidenceであり、今回のpassには流用していない。

## 適用範囲と残存リスク

ローカルDockerで、既定方式を維持したSR compiler-cache永続化の性能・品質・失敗時動作を検証した。
将来deploymentのUID/mount、quota/retention、別identity間のGPU schedulingとbusy時retryはoperatorが決める。
長寿命containerが既にdefault cacheを再利用する場合の追加利益、別GPU/driver/shape/長文書の効果は未測定。
PyTorch内部counterに依存するためruntime更新ではidentityが変わり、counter/品質契約の再確認が必要。
source全体hashによる保守的なinvalidateとinventory全hashのI/O costを含む今回の性能結果を、
任意のdeploymentや全入力への改善率/品質保証には一般化しない。
