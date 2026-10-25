# 実験モデル選択とproduction preflightの分離（#448 調査・設計）

本書は開発者向けの設計提案であり、実装済みの操作仕様ではない。
現行調査対象は `9ccd57fb`（develop）。runtime、model bytes、設定、thresholdは変更していない。
実装は [#450](https://github.com/M763468/PDFScoreBar/issues/450) で行う。
現行の正規契約は [モデル契約](../MODEL_ARTIFACT_CONTRACT.md)、
[モデル登録手順](../MODEL_ARTIFACTS.md)、[検証方針](VALIDATION_POLICY.md) を参照する。

## 結論と用語

候補checkpointの登録には既存の `pdfscorebar.model_artifact.v1` と共有cacheを再利用できる。
ただし、全モデルを安全に候補選択して実行する共通入口はまだない。
**開発専用の明示的なexperiment selection manifestとrunnerを追加する**方式を推奨する。
productionのpreflightを緩めるフラグや、候補ごとのpreflight本体書換えは追加しない。

- **production selected identity**: レビュー・採用済みのversion/provenance/digestと設定の組。
- **experiment candidate**: 未採用の別version。登録・整合性検証できても採用済みとは限らない。
- **runtime compatibility**: image-owned依存・patch・assetと実行sourceの互換性。
- **source provenance**: 実際に実行したsource/configのidentity。image build時と異なっても
  runtime互換性が保たれる場合があり、両者を同一視しない。
- **preflight PASS**: 必要条件が揃い、対象runtimeで候補をload/最小実行できた状態。
  experiment評価PASS、production採用PASSとは別に記録する。

## 現行主要チェックの棚卸し

「共通」は実験でも維持する要件、「production」は採用済み選定または配布の追加要件。
既存コードが既にすべての共通要件を満たす、という意味ではない。

| チェック・目的 | 現行根拠 | 適用と候補での扱い |
| --- | --- | --- |
| image存在・immutable ID固定、asset contract label | `docker/distribution.py:main`、`scripts/docker_image_resolver.py`、`scripts/docker_runtime_validation.sh` | 共通。mutable tagだけを実験identityにしない。explicit imageを別imageに自動置換しない |
| runtime fingerprint一致 | `docker/runtime_contract.py:RUNTIME_CONTRACT_FILES, runtime_fingerprint, run_preflight` | 共通。Dockerfile/dependency/provider patch/image-owned CNN生成に関わる入力を保持。異なるruntimeは別build/identityが必要 |
| source fingerprint記録 | 同 `SOURCE_CONTRACT_ROOTS, source_fingerprint, run_preflight` | 共通のprovenance。source mismatch自体は現在のpreflightの拒否条件ではない。runtime fingerprintとは別物 |
| frozen配布のschema、path安全性、選択inventory、hash、release provenance | 同 `validate_distribution_provenance`、`docker/distribution.py:source_identity` | production/配布で必須。Gitありならtracked集合・dirty、展開配布なら実inventoryも検証。配布内の候補追加/編集で回避せず、開発checkoutを使う |
| config/input/assetの存在、外部symlink mount診断 | 同 `_require_file, _resolve_input_path, run_preflight` | 共通。hostにあるだけではcontainerから利用可能とは限らない。現行はconfig全体のschema/意味検証ではない |
| artifact schema/version/architecture名・SHA形式・安全なcache相対path | `src/common/model_artifacts.py:load_model_artifact_manifest` | 共通。現行architectureは非空文字列の検査であり、対応architectureや実tensorの検証とは別 |
| 必須weight存在・SHA検証、明示import・atomic publish | 同 `resolve_model_artifact, import_model_artifact, materialize_model_artifact` | 共通。digestは選択versionのidentity。候補自身のmanifestに照合する。size/provenanceを一般loaderが強制検証するわけではない |
| OMR-DLN選定version一致、RO mount | `scripts/docker_runtime_validation.sh:verify_explicit_omr`、`docker/distribution.py:main` | productionは固定manifestと照合。候補は専用selectionを使用。環境変数でpathを変えるだけでは候補選択にならない |
| SR x2/x4のSHA、image-owned配置 | root `Dockerfile` のdownload/hash/copy、`src/common/model_artifacts.py:resolve_realesrgan_weight` | 共通integrity＋production選定。build時にhash検証、runtime preflightは存在検査。任意候補SRは現行generic manifest経路に統合されていない |
| CNN manifest SHA・EfficientNet-B0 checkpoint・threshold一致・NMS無効 | `src/pipeline/detection/dense_orchestrator.py:_resolve_verified_cnn_artifact, _validate_verified_cnn_manifest, _run_cnn_scoring` | 共通のarchitecture/scoring契約＋production設定。別manifestを指定可能で、D27のdigestだけにhardcodeされてはいない |
| maintained HOMR marker・必要path・source pin/direct_url照合 | `docker/runtime_contract.py:_validate_production_provenance`、`src/pipeline/detection/profile_contract.py`、`maintained_homr_worker.py` | productionはmaintained契約必須。候補runtimeにも同等の明示identityが必要。markerを削るのでなく別profile/adapterが必要 |
| HOMR実model hashの記録 | `src/pipeline/detection/maintained_homr_worker.py:model_provenance` | 共通provenanceに再利用可能。ただし記録された実hashと、承認済み期待hashとの照合は別。preflightで全weightのdigestを照合しているとは言えない |
| required moduleのimport origin | `docker/runtime_contract.py:RUNTIME_MODULES, run_preflight` | 共通。ただし存在確認だけではversion・I/O・load成功を保証しない |
| CUDA可用性・ONNX CUDA provider一覧 | 同 `run_preflight` | 共通の必要条件。全sessionの実providerやCPU fallback不在を保証しない。候補runnerは実session確認を追加する |
| MMR path存在・OCR provider | 同 `run_preflight`、`src/measure_numbering/rapidocr_provider.py:create_mmr_rapidocr` | 現行MMR weightはraw path。preflightはSHA未照合。OCRはCUDA未確認でもwarning後継続する経路があり、実験のno-fallback保証として流用不可 |
| 精度・semantic regression・production smoke | `docs/dev/VALIDATION_POLICY.md`、`configs/smoke_test.yaml`、関連smoke scripts | preflight外の別gate。必要なdataset・metric・toleranceを実験前に固定し、全gateを報告する |

補足: `run_preflight`単独ではOMR-DLNはpath resolver＋存在検査であり、採用済みSHA検証は
host launcherが担う。CNN raw pathとmanifestを両方preflightが見ても、dense本実行はraw pathを拒否する。
preflightだけの成功をend-to-end適合と解釈しない。

## モデル別の選択可能範囲

| 種類 | 現在できること | 実験入口に必要な最小差分 |
| --- | --- | --- |
| CNN | 別のv1 manifestを共有cacheへimportし、別configの `detection.cnn_model_manifest` で指定。EfficientNet-B0、`production_contract.cnn_threshold`一致、NMS=falseが必要 | selectionから明示注入し、candidate provenance・cache衝突・load/実provider・結果identityを検証。`production_contract`という既存fieldは採用証明ではなくscoring契約として互換adapterで扱う |
| OMR-DLN | generic importは別manifestにも対応。workerは `OMR_DLN_MODEL_PATH` を読むが、canonical launcherはproduction manifestで検証する | 候補manifestから解決・SHA検証・RO mountし、workerへ渡す専用経路。measure detectorのarchitecture/class mapping/出力座標互換性も検証 |
| HOMR | maintained profileとinstalled sourceが固定。歴史的Stage-E componentは隔離済み | 新runtime/profile adapterと全ONNX asset inventoryが必要。初期実装は候補交換を明示拒否 |
| Real-ESRGAN | directory overrideはあるがgeneric選択manifestではなくimage-owned release bytes | model constructor/scale/I/Oと期待hashのadapterが必要。初期実装は候補交換を明示拒否 |
| MMR/OCRなど | MMR raw path、package-owned OCR assets/provider設定 | 個別asset identityとprovider契約が必要。初期実装は候補交換を拒否し、継続利用分も実hash/runtime identityを記録する |

CNNだけなら現行configで試せるが、generic artifact loaderはprovenance必須性、architecture実体、
cache pathとmodel/versionの一対一性を強制しない。全候補に対する安全な入口としては不十分。
既存shared cacheの優先順位（明示root → `PDFSCOREBAR_MODEL_CACHE` → XDG → user cache）は変更不要。

## 方式比較と推奨契約

| 方式 | 評価 |
| --- | --- |
| production manifest/global defaultを候補ごとに変更 | 不採用。採用済みidentityやimage-owned CNN fingerprintに影響し、研究と配布の判定を混同する |
| arbitrary path/環境変数＋skip-preflight | 不採用。selected digest検証、依存runtime、再現性を統一できない |
| 各モデルのconfig overrideだけで運用 | CNNの限定試行には使えるが、OMR固定launcher・HOMR pin・結果provenanceを解決しない |
| artifact v1＋明示selection＋開発専用runner | 推奨。artifact登録/cacheは共有し、選定policyと実行結線を分離する |

提案selectionはversion付きschemaで、run ID、候補role→artifact manifest、training/source provenance、
scoring/I/O契約、immutable image ID、runtime fingerprint、要求provider、config/input identity、
評価契約参照、出力先を束ねる。manifest自体のhashと各artifactのexpected/actual hashを保存する。
省略roleは「その時のdefault」へ再解決せず、選択時のproduction manifest/profileとbytesをsnapshotする。
初期対応は同じimage/runtimeでload可能なCNNとOMR-DLNだけとし、未知role/architecture/runtime変更を拒否する。

検証と実行は同じ解決済みselectionを使用する。modelはversion別cacheからROでmountし、
cache path/roleの衝突、root外escape、異なるbytesへの同じversion再利用を拒否する。
既存 `import --force` を候補登録の通常操作にせず、production cacheを上書きしない。
mount後に実際のファイルを再照合し、検証とloadの間の差替を検出する。
state_dictのshape、class/出力座標、最小推論、sessionの実providerが揃うまではPASSを出さない。
CPU利用が実験契約で明示許可される場合も要求providerと実providerを照合し、暗黙の代替は拒否する。

失敗はnonzero＋機械可読の理由を返す。missing/corrupt/unknown schema、provenance不足、
unsupported architecture/runtime/provider、load不適合、未確認provider、hash変更はすべて停止条件。
部分成功をPASSとして保存せず、登録成功・preflight・評価・採用を独立した状態にする。

## 入力・操作・出力案

現行で実行可能なのは次の登録・照合。manifestはrepository配下に置く必要がある
（CLIの `_find_project_root` が祖先のrepository rootを探す）。hashは正確な元checkpointから計算し、
training commit/config/data/checkpoint provenanceを別manifestの `provenance` に記録する。

```json
{
  "schema_version": "pdfscorebar.model_artifact.v1",
  "model_id": "barline-cnn",
  "version": "issue450-candidate-01",
  "architecture": "efficientnet_b0",
  "distribution": {"mode": "operator-supplied", "asset": "candidate.pth"},
  "sha256": "<exact checkpoint SHA-256: replace before import>",
  "cache_path": "barline_cnn/issue450-candidate-01/candidate.pth",
  "provenance": {"training_commit": "<commit>", "training_config_sha256": "<digest>", "dataset_identity": "<identity>"},
  "production_contract": {"cnn_threshold": 0.4965248107910156}
}
```

このJSONはplaceholderを含む説明例。thresholdはcheckpoint交換だけを比較する場合に固定する値で、
新しい候補への最適値・採用済み精度を保証しない。threshold探索は別の事前宣言した実験にする。

```bash
python3 -m src.common.model_artifacts import \
  experiments/issue450/candidate.json /path/to/candidate.pth
python3 -m src.common.model_artifacts verify experiments/issue450/candidate.json
python3 -m src.common.model_artifacts path experiments/issue450/candidate.json
```

将来runnerの操作案（**未実装。現在実行できるコマンドではない**）:

```text
experiment-runner preflight --selection experiments/issue450/selection.json
experiment-runner run --selection experiments/issue450/selection.json
```

毎checkpointで変えるのはcandidate version/digest/provenance、selection、必要なら実験config。
preflight本体、production選定manifest、global default、配布inventoryは変更不要。
新worktreeでは同じmanifest/selectionと共有cacheを使い、同じbytesを再importしない。
依存runtime/architectureが変わる場合は新adapter/imageの実装・検証が必要であり、無条件には再利用できない。

出力案は `logs/issue<N>/experiments/<run-id>/` にselection/config snapshot、source commitとdirty diff digest、
input identity、image ID、runtime fingerprint、全model hash、実session providers、preflight結果、
評価contract/resultを保存する。checkpointそのものは共有cache等の保持場所に置き、Gitへ追加しない。
missingなら明示import、hash mismatchなら元checkpoint/manifest identityを確認し、新versionを割り当てる。
runtime mismatchならbase/image provenanceを比較して適合imageを選び、必要な場合だけ別imageをbuildする。
unknown providerならsession設定・runtimeを修正し、検証をskipして進めない。

## productionへの昇格

1. 評価前にsource/candidate、baseline、dataset、metric、semantic gate、tolerance、seed/configを固定する。
2. 同一入力で候補を実行し、accuracyと下流semantic regressionを全gateで比較する。
   preflight成功は評価成功を意味しない。失敗後のthreshold変更・dataset縮小は別実験として記録する。
3. accepted結果とレビューが揃った場合だけ、別PRでproduction selected version/provenance/digestを更新する。
   公開可能なartifactは新Releaseへpublish→fresh download→空cache import/materialize→SHA照合する。
   operator-suppliedモデルは取得・import契約とlicense境界を維持する。
4. image-owned asset/runtimeに影響すればimageをbuildし、canonical preflight/GPU smoke、影響する
   accuracy/semantic評価、engine契約と配布inventory/provenanceの検証を行う。
5. release/mainへの昇格は [ブランチ方針](../BRANCH_POLICY.md) に従う別承認。
   古いversion/cache/rollback用assetは自動削除しない。

## 受入条件・文書連携・調査限界

実装とテストの受入条件は [#450](https://github.com/M763468/PDFScoreBar/issues/450) に集約した。
候補共存/新worktree再利用、破損・不適合・provider fallback拒否、production identity維持、
同じselectionの検証→実行結線をfixtureと専用runtimeで確認する。
モデル数値挙動が変わる検証では [検証方針](VALIDATION_POLICY.md) の評価gateを適用する。

[#446](https://github.com/M763468/PDFScoreBar/issues/446) の開発ガイドは本書を設計提案として参照し、
実装後の操作仕様は既存モデル契約/開発ガイドへ統合する。日英同期・配置方針は同Epicに従い、
本調査で既存英語契約を重複翻訳したり最小配布へ研究用ファイルを追加したりしない。

歴史的根拠: #329 / PR #331（version別SHAとoperator import）、#352 / PR #353
（共有cacheとruntime/source fingerprint分離）、#398 / PR #401と
[scope clarification](https://github.com/M763468/PDFScoreBar/issues/398#issuecomment-5969279832)
（productionと歴史的Stage-E componentの分離）。過去のGPU/精度結果は今回再実行していない。
`MODEL_ARTIFACT_CONTRACT.md` のmaintained HOMR inventoryは古いcommitを記載しているが、
現行Dockerfile/profileは `457e7c6518a10ba755db2e60883419e56c4d7369`。
本書ではsource/profileを優先し、古いarchive hashを現行weightの保証として使用しない。
