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

結果とexact command/provenanceは完了後に追記する。旧試作のsmoke成功は今回のpassに流用しない。
