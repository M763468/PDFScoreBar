# Issue #454: SR compiler-cache lifetime investigation

> この文書は初回調査の履歴。deployment未確定を理由とする延期判断は、
> [maintained launcher実装](issue454-implementation.md)で撤回した。

## 初回の採用判断 (2026-10-29、撤回済み)

**production統合は見送る。Issueはopenのまま、deployment設計が具体化した時点で再評価する。**
ユーザー確認により、実deploymentはまだ存在せず構想段階である。
短命Docker jobをdeploymentの実態として扱うことはできない。
既存launcherから改善可能性は認められるが、deploymentでの有効性は未確認である。
productionのモデル・閾値・compile方式・launcher既定動作は変更しない。

対象は `origin/develop` の `35783ed8` (#447 / #455 merge済み)。
[Issue #454](https://github.com/M763468/PDFScoreBar/issues/454) 本文と最新コメント、
`AGENTS.md`、validation/environment/worktree policy、現行sourceを確認した。

## 実行経路と観測

| 経路 | 寿命・UID | cache保存・再利用と改善可能性 |
| --- | --- | --- |
| `scripts/docker_runtime_validation.sh` | preflight/pipeline/accuracyを別々の `docker run --rm` で起動。既定はimageのUID、明示 `DOCKER_EXTRA_ARGS` により変更可能 | compiler-cache mount/env指定なし。cacheはcontainer writable layerの寿命に限定され、job間reuseを保証しない。短命jobを将来採用する場合に有力 |
| Makefileの直接 `docker run --rm` 経路 | disposable job、既定UID指定なし | 同様に永続cache契約なし。検証launcherと区別してdeployment時に統一が必要 |
| `src/pipeline/core/python_env.py` | host上のheavy stepは既存 `pdfscore_pipeline_gpu` に `docker exec`、container内はmain venvでsubprocess | 同じcontainer/UID/環境ならdisk cacheが残り得る。子process終了とcontainer終了を混同しない |
| `PipelineJobExecutor` | 同期one-job adapter。Docker起動・終了やservice lifecycleを所有しない | deployment未決定。長寿命serviceなら既存layerでのreuseをまず測定する |
| ローカル `pdfscore_pipeline_pytest_dev` | image `5311cf22ab01…`、実行UID:GID `0:0`、2026-10-22から稼働、manager checkoutとOMR weightをbind | 開発環境。compiler-cache mount/envなし。`/tmp/torchinductor_root` と `torchinductor_uid_1000` は各4 KiB、調査時のfile列挙は空。名前やdirectory存在だけでhitとは言えない |

ローカルのproduction named containerは稼働していなかった。開発containerを本番の証拠にしない。
imageのConfig.User未指定は既定root。実行UID1000の#447結果をroot経路に外挿しない。
共有tag `pdfscore_pipeline_gpu` の `5311cf22…` は現行runtime contractと非互換。
resolverは既存の互換image
`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`
を選択した。共有tag、既存container、モデル、データ、cacheは削除・置換しなかった。

## 既存実験の再利用

[#447最終結果](issue447-results.md) と [反復詳細](issue447-deepening.md) を参照した。
UID1000、同じRTX4060/runtime、single-pageの3組ではcold中央値233.242秒、warm111.652秒、
中央値の比による短縮52.13%、paired saving中央値122.373秒だった。
strict source/mask/detector/番号/MMR gatesは対象ページで一致した。
**これは今回の候補の測定でもproduction改善率でもない。** OS/driver cacheはflushされていない。
root、長寿命service、未知のshapeやdeploymentまで品質を保証しない。
compile無効化PoCはsemantic gate不合格なので代替として採用しない。

## 候補設計と試作

実験候補commit `f5859011` を作成してfocused検証したが、deployment不在の確認後に
production統合を最終diffから取り下げた。試作は未採用であり、製品仕様として扱わない。
候補patchはローカル `logs/issue454/candidate/f5859011.patch` に保持する。

再開時に検討する契約:

- operatorが明示して事前作成した、ローカルfilesystem上の私有rootのみ利用する。
  自動download、既存cache移行、暗黙の別cacheへのfallbackは行わない。
- immutable image/runtime/compiler、torch/Triton/CUDA/cuDNN、GPU/driver、weight SHA-256、
  SR設定・compile mode、source digest、実行UID/GIDをidentityに含める。
  image由来のcompiler toolchainを含め、mutable runtime改変は認めない。
  source全体hashは保守的で、無関係なsource変更でもcoldになるtradeoffがある。
- rootを実行UID所有・0700にする。rootとnon-rootのnamespaceや所有権を混在させない。
  読み込むcompiler artifactは実行可能な信頼済みデータとして扱う。
- 同一identityの全SR処理にnonblocking exclusive flockを保持し、競合は明示的busyで終了。
  別identity間のGPU schedulingはdeploymentの責任とする。cache lockはGPU競合防止を意味しない。
  NFS/distributed lock、複数host間共有は対象外。
- 初回は空namespaceのみ。identity manifestと全artifact inventoryのSHA-256を再利用前に照合。
  symlink、権限不足、manifest不整合・破損・異常終了dirty markerを検知したら停止する。
  compiler error suppressionを禁止し、失敗を成功として記録しない。
- 成功後にinventoryを更新し、run resultにidentity、namespace、before/after inventoryと
  compiler countersを出す。directory reuseと実際のhit/miss/recompileを別々に記録する。
  countersが取れなければunknownとし、hitを主張しない。
- **無効化:** jobを停止/排他した後に新しい空operator rootを選択する。旧rootは保持する。
  identity変更時は別namespaceを選択する。既存manifestの書換えで旧cacheを流用しない。
  retention容量/期間と手動cleanup権限はdeployment operatorが決定する。
  自動evictionや既存cacheの削除は今回実装しない。

PyTorch 2.14公式の[compile time説明](https://github.com/pytorch/pytorch/blob/v2.14.0/docs/source/user_guide/torch_compiler/compile/programming_model.reducing_compile_time.md)
をContext7で確認し、process間cache reuseの可能性を確認した。
試作のintegrity/lock方式はPyTorchの保証ではなくapplication側の追加契約である。

## 事前固定した比較契約と再開条件

[比較契約](issue454-contract.json) は今回の性能結果を見る前に保存した。
root/non-root、single/multi-pageを別cohortとし、それぞれcold/warm 3組、trace OFFのDocker
E2E中央値20%以上短縮を目標とした。strict SR/source geometry/staff/connector、ordered
page/system/measure、numbering/MMR/filters、実際のcorrection replayを必須とする。
CPU/RAM/GPU/VRAM/I/O、compiler hit/missとidentityを残し、既知のGPU競合runは採用しない。

実deployment不在の確認後、待機中matrixを推論開始前に中止した。
これは契約を緩めたPASSではなく、**性能・品質の採用gateは未達成/未実行**という判断である。
再開時はdeploymentのlauncher/service寿命・UID・mount・同時job数を確定し、
長寿命経路が既にreuseするかを測定してから、この契約の適合性を事前に確認する。
将来契約を変更する場合は旧契約を保持し、結果を見る前に承認する。
full68は速度測定だけを目的に再実行しない。出力が変わり得る実装を採用する際は
validation policyに従い、smokeと影響範囲の精度回帰を追加する。

## 今回の検証記録

最終成果物はdocs-only。runtime変更は取り下げ済みなので最終diffのruntime testは不要。
試作時の検証は以下に分離する。working directoryは専用worktree
`.worktrees/issue454`。候補patch SHA-256:
`269814876a941ed24d8b26cf68c2ce245d66601a04bd243f5e9ee2361bf960d7`。

| Check | 今回の状態 | Command / evidence |
| --- | --- | --- |
| 候補focused | Passed | `docker exec --user 1000:1001 -w /workspace/.worktrees/issue454 -e PYTHONPATH=/workspace/.worktrees/issue454 pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python -m pytest tests/test_sr_compiler_cache.py -q`; 6 passed, exit 0。image `5311cf22…`、manager bind配下のnested worktree。GPU未使用 |
| 候補fast suite | Passed | 同じexec/interpreterでMakefileの `FAST_TESTS` と `tests/test_sr_compiler_cache.py` を実行。128 passed, exit 0、`logs/issue454/preflight/fast-tests.log` |
| 候補focused再確認 | Passed | 同じexec/interpreterで `tests/test_sr_compiler_cache.py tests/test_issue447_profiling_tools.py -q`。28 passed, exit 0。これらはcheckpoint作成前のworking candidateに対する結果。最終の取り下げ済みruntimeに対する再実行ではない |
| shell/help/compile | Passed | `bash -n scripts/docker_runtime_validation.sh`、`make help`、`bash scripts/docker_runtime_validation.sh --help`、候補Pythonへの `python3 -m py_compile`。exit 0。script直実行は非executableのためpermission denied、maintainedなbash起動で再試行済み |
| GPU smoke初回 | Blocked | `PDFSCORE_SR_COMPILER_CACHE="$PWD/logs/issue454/cache/root-smoke" make verify-gpu-smoke`。評価PDFがworktreeにないためpreflight exit 2。`logs/issue454/validation/gpu-smoke-blocked/` |
| GPU smoke再試行 | Passed (smokeのみ) | 前項に `DOCKER_EXTRA_ARGS='-v /home/masaki_muramatsu/ws_PDFScoreBar/data/evaluation2:/workspace/data/evaluation2:ro'` を追加。exit 0。互換image `5c5979a2…`、root、直接worktree mount。85 GT / 85 matched、hard FP=0、FN=0。`logs/issue454/validation/gpu-smoke-retry/` と `logs/issue454/validation/smoke_test_detection_20261029T141123Z/` |
| 候補の総合品質・cache hit/performance採用判定 | Not run / 未達成 | smoke実行中に候補のprovenance/counterコードを編集し、その後統合を取り下げたため、smoke成功を固定candidate全体の品質証明に使わない。root/non-root反復、multi-page semantic/correction回帰、精度維持の採用gateは未達成 |
| E2E性能matrix | Not run | 固定36 jobを待機させたがdeployment不在確認後に待機shellを中止。benchmark jobの推論は開始していない |
| full68 | Not run | 最終docs-only、計測目的の再推論はIssue scope外 |

smokeのdefault出力は実行後に上記Issue rootへ移動した。captured command/log中の旧
`logs/system/` / `logs/full_pipeline_runs/` pathは実行時の記録として保持している。
候補cacheと既存モデル・データは削除していない。

残存リスクは、deployment未決定、root E2E性能未測定、shape履歴によるrecompile、
manifest全hashのI/O cost、排他時の待ち/再試行方式、容量retention、compiler内部fallbackの
観測網羅性である。今回の試作を無検証で復活させず、再開時に全gateを満たす必要がある。
