# 開発用モデルの探索・正式比較とproduction選定（#448）

CNNとOMR-DLN候補は、既存configの明示パスで試せる。
探索のたびにversion/SHA/provenanceを登録したり、production manifestを編集したりする必要はない。
[PR #451](https://github.com/M763468/PDFScoreBar/pull/451) で調査と実装をまとめる。
当初の別selection manifest/専用runner案と独立実装Issue #450は、
[レビュー方針](https://github.com/M763468/PDFScoreBar/pull/451#issuecomment-6400645077) により置き換えた。

現行productionの正規契約は [モデル契約](../MODEL_ARTIFACT_CONTRACT.md)、
[モデル登録手順](../MODEL_ARTIFACTS.md)、[検証方針](VALIDATION_POLICY.md) を参照する。

## 検証の段階

`detection.model_validation` を指定する。省略時は `production`。未知の値はエラー。
`exploration` / `comparison` は `detection.detector_route: dense_full_pipeline` のみ対応する。
route省略（standard）・標準route・未知routeとの組合せは、preflightと直接pipeline実行の入口で拒否する。

| 設定 | モデル選択・検証 | 固定/記録 |
| --- | --- | --- |
| `exploration` | 明示パスの現在のcheckpointを実際にload。対応architecture、tensor shape、I/O、要求deviceを確認。採用済みbytesとの一致は要求しない | 実行時に現在のhashを自動記録。事前登録不要。同じパスの重みを更新して再実行できる |
| `comparison` | 探索と同じ選択・load経路に加え、`model_sha256.cnn` / `model_sha256.omr_dln`との一致を必須とする | 探索結果からhashをコピーして固定。評価の入力・config・runtime・metric・seed・toleranceも実験前に固定する |
| `production` | 従来のCNN manifest/architecture/threshold契約、OMR-DLN selected manifest SHA、maintained runtime、配布inventoryを検証 | 採用済みversion/provenance/integrity契約を維持する |

Preflight成功、pipeline実行成功、精度比較合格、production採用は別の判定。
候補モードのDocker実行はproduction専用のaccuracy smokeを自動流用しない。
正式比較では、事前に宣言した評価コマンドと全regression gateを別途実行する。

## 対応範囲とチェックの整理

| 項目 | 探索・比較 | production/配布 | 根拠・目的 |
| --- | --- | --- | --- |
| CNNパス | `cnn_model_path`を優先。コピー元configにmanifestが残っていても候補パスを使う。未指定ならmanifestから解決 | raw pathを拒否しmanifestを要求 | `dense_orchestrator.py` / `model_selection.py`。候補差替と採用済み選定を区別 |
| CNN architecture | 既存loaderが対応するResNet18 / EfficientNet-B0。binary headとstate_dictのshapeを検証 | EfficientNet-B0を維持 | `steps/cnn_scoring.py`。探索用のEfficientNet-B0固定チェックを除外し、実loadを共用 |
| CNN threshold | configで明示、有限の0〜1。manifestの`production_contract`との一致は不要 | manifest thresholdとの一致を維持 | `dense_orchestrator.py`。threshold探索は比較条件として明示 |
| CNN NMS/crop/geometry | dense経路のNMS=falseなど既存I/O/scoring条件は維持 | 従来どおり | model identityとは別の下流semantic契約 |
| OMR-DLNパス | `omr_dln_model_path`を優先、次に環境変数。明示したmissing/corrupt候補から別モデルへfallbackしない | 同じoverrideでもproduction manifest SHA照合が必須 | `model_selection.py`。Docker launcherに重複していた解決/照合を共通化 |
| OMR-DLN互換性 | native `.pt`、detection taskとbox I/O、明示device、予測I/Oを検証。モデルの意味が「小節」であることは候補作成者が保証する | 従来のselectedモデル | `omr_dln_worker.py`。exported ONNX/TensorRT候補は今回未対応 |
| weight hash/version | 探索は実hashを自動記録、比較だけ指定hashと照合 | manifest選定versionのSHAを検証 | 全候補への事前SHA/version/provenance登録義務は設けない |
| 古い検出出力の再利用 | モデル差替時に古い結果を使わないよう検出のskip-existingを無効化 | 従来どおり | `dense_orchestrator.py`。同じパスで再学習した重みの再実行に対応 |
| HOMR source pin/marker | 現行maintained runtimeをそのまま利用。候補HOMR差替は未対応 | 必須 | `profile_contract.py` / `maintained_homr_worker.py`。対応しないruntimeまでチェックを削って実行可能とは扱わない |
| SR / MMR / OCR | 候補交換の検証は今回の対象外 | 既存設定・assetを維持 | SRはimage-owned。MMR raw pathの存在検査は全weight SHA検証ではない |
| image/runtime互換性 | image存在、immutable ID、runtime fingerprint照合を維持 | 必須 | `scripts/docker_image_resolver.py` / `docker/runtime_contract.py` |
| source provenance | source fingerprintと実行sourceを記録。image build時とのsource一致自体は拒否条件ではない | frozen配布ではinventory/hash/dirty検証を追加 | runtime互換性とsource identityは別概念 |
| provider/device | CNN/OMR候補は`cpu`または`cuda`を明示。既定は`cuda`。CUDA要求からCPUへfallbackしない | 現行CUDA/ONNX/maintained契約を維持 | GPU一覧だけで実load成功とは扱わない。MMR OCRのwarning後fallbackまで候補の保証範囲に含めない |
| input/weight存在・mount | containerから見えることを検査し候補をRO mount | 従来どおり | hostの絶対symlink先がcontainerに見えるとは限らない |
| 配布identity | frozen配布から候補モードを使うことを拒否。開発checkoutを使用する | schema/inventory/path/hash/release provenanceを厳格検証 | `distribution.py:source_identity` / `runtime_contract.py:validate_distribution_provenance` |

共通artifact cacheの優先順位（明示root → `PDFSCOREBAR_MODEL_CACHE` → XDG → user cache）は変更しない。
探索のraw checkpointはcache登録不要。manifestで指定したartifactは従来どおりそのmanifestのSHAを検証する。

## 探索の操作例

`configs/dense_full_pipeline.yaml`等を作業用configへコピーし、次を変更する。
データ/input/outputの設定は元configの用途に合わせる。下は追加・変更するfieldだけの例。

```yaml
run:
  run_id: candidate_01
  output_root: logs/issue448/experiments

detection:
  model_validation: exploration
  cnn_model_path: /absolute/path/to/candidate.pth
  cnn_threshold: 0.5
  cnn_device: cuda
  omr_dln_model_path: /absolute/path/to/measure_candidate.pt
  omr_dln_device: cuda
```

CNNの元manifestは残っていてもよい。`cnn_model_path`を削除するとmanifest選択へ戻る。
片方のモデルだけを試す場合、もう片方は既存manifest/cacheまたは採用済みパスを利用できる。
新しいweightを同じパスへ保存した後、configやpreflight本体を編集せず再実行できる。
探索時も実行中のcheckpoint書換えは避ける。実行の前後で変更を検出した場合は結果を無効として停止する。

```bash
bash scripts/docker_runtime_validation.sh --config experiments/my_candidate.yaml --preflight-only
bash scripts/docker_runtime_validation.sh --config experiments/my_candidate.yaml
```

既存launcherが候補パスを解決し、CNN/OMRをRO mountして同じconfigでpreflightとpipelineを実行する。
外部PDF等のmountは従来どおり `DOCKER_EXTRA_ARGS` で追加する。
HOMR/SRのruntime互換性が変わらなければ、checkpoint更新のためのimage再buildは不要。
候補用の新しいselection manifestや専用runnerはない。
直接 `src/pipeline/main.py --config ...` を実行する場合も同じ選択policyを使うが、
外部pathのmountとimage provenanceの記録は呼出し側の責任。Docker preflightの実load/I/O確認は別途必要。

## 正式比較・再現

候補実行の `<run-dir>/model_selection.json` には、選択したCNN/OMRのパスと実SHA、
config、入力画像SHA、source/runtime fingerprint、launcherから渡されたsource commit/image IDを記録する。
`status: selected` は観測記録であり、pipelineや精度評価の成功宣言ではない。
検出sourceのmanifest/result、pipeline log、評価resultも同じIssue rootに保持する。

```python
import json
import yaml

config = yaml.safe_load(open("experiments/my_candidate.yaml"))
observed = json.load(open("logs/issue448/experiments/candidate_01/model_selection.json"))
config["detection"]["model_validation"] = "comparison"
config["detection"]["model_sha256"] = {
    role: model["sha256"] for role, model in observed["models"].items()
}
with open("experiments/fixed_comparison.yaml", "w") as output:
    yaml.safe_dump(config, output)
```

実行時はimmutable image IDを `DOCKER_IMAGE` に指定し、source commit＋dirty diff、入力集合、
config、baseline、metric、semantic gate、tolerance、seedを評価前に固定・保存する。
`model_sha256`は2モデルのbytes照合であり、これだけで全実験条件の再現性が成立するわけではない。
欠けたhashや変更済みcheckpointは比較モードで停止する。threshold探索後の結果は別実験として扱う。

## production昇格と失敗時対応

1. 同一入力で候補を評価し、accuracyと下流semantic regressionの全gateを確認する。
2. accepted結果とレビューが揃った場合だけ別の採用変更でproduction version/provenance/digestを更新する。
   公開可能なartifactは新Releaseへpublishし、fresh download・空cache materialize・SHA照合を行う。
   operator-suppliedモデルは取得/import契約とlicense境界を維持する。
3. image-owned asset/runtimeに影響すればimageをbuildする。canonical preflight/GPU smoke、
   必要なaccuracy/semantic評価、engineと配布provenanceの検証を行う。
4. mainへのrelease昇格は [ブランチ方針](../BRANCH_POLICY.md) に従う。古いcache/rollback assetは自動削除しない。

missing/corrupt候補はpath/checkpointを修正する。shape/task/device不適合は対応形式で作成し直す。
比較hash不一致はモデルか比較対象が変わったことを意味するため、既存の比較結果を上書きして合格扱いにしない。
runtime mismatchはbase/image provenanceを比較して適合imageを選び、必要な場合だけbuildする。

## 設計の根拠と文書連携

#329 / PR #331はversion別SHAとoperator import、#352 / PR #353は共有cacheとruntime/source fingerprintの分離、
#398 / PR #401はproductionと歴史的Stage-E componentの分離を定めた。今回もこれらのproduction契約を維持する。
過去のGPU/精度結果は今回の検証結果とは分ける。
`MODEL_ARTIFACT_CONTRACT.md`のmaintained HOMR inventoryは古いcommitを記載しているが、
現行Dockerfile/profileは `457e7c6518a10ba755db2e60883419e56c4d7369`。
古いarchive hashを現行weightの保証として使用しない。

[#446](https://github.com/M763468/PDFScoreBar/issues/446) の開発ガイドは本書を現行操作への参照先とし、
日英同期・配置方針は同Epicに従う。本書の追加だけで英語版翻訳が完了したとは扱わない。
