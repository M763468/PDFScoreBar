# Issue #416 追加検証記録

最新の本番実装・残存FNの受容判断は [IMPLEMENTATION.md](IMPLEMENTATION.md)。
以下は実装前の調査記録として保持する。

2026-10-15。判断と本番修正案は [PRODUCTION_FIX_PROPOSAL.md](PRODUCTION_FIX_PROPOSAL.md)。
基準: `develop@016e181861270f1adc753778ef71422fa51f2716`。
元推論 `a65d9541777ae492137c24b6ce0f5f5692881945` の固定Full68を使用。
GT/matcher/threshold/modelを変更せず、初期実験と不採用結果も保持した。

## Runtimeとモデル

- image: `sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc`
- runtime compatibility fingerprint:
  `d73cfaa3096e662faca36d85f425553ebeb258f912a7bd424827425caaac2f97`
- RTX4060、container Python3.12、`/opt/venv_pipeline/bin/python`。
- GPU preflight: PASS、torch CUDA利用可、ONNX RuntimeにCUDAExecutionProvider。
- barline CNN SHA-256:
  `f41a9b578396493a83e39ed284b1781f65d6adec8f624e6b7234e917c919c5cd`
- MMR CNN SHA-256:
  `f163fa2a7679d12c0f4fe6fc2fadc7ed1f144035779a18b83a303bfa6d35903a`
- MMR source SHA-256:
  `d7b996584f6593d26ad9f84617e20c233552120a903db577dc19a04302c4d2c7`
  受理済み#414評価のsource hashと一致。RapidOCRは明示`cuda`で作成し、det/cls/recの全providerを検査した。
- 稼働中pytest containerの古いimage `5311cf22...` はruntime互換性不一致で使用しなかった。
  compatibleな上記imageを選び、既存container・image/tagは変更しなかった。
- 非rootでの最初のCNN試行はimage内root専用weightを読めず失敗。同じmanifest hashの
  共有model cacheをそのパスへread-only mountし、実行時にhashを再検証した。weightの代替はない。

## 成分と下流の結果

成分全68ページのTP/FP/FN/softと不採用理由は修正案の比較表に記載。
GPUでv1の392新cropを採点し直し、初期CPU候補との採否は全ページ一致した。

| 下流検証 | 正規化 v1 | v1 + 最高score重複整理 | v1 + 幾何を保つ重複整理 |
| --- | ---: | ---: | ---: |
| 物理ページ / 小節 | 68 / 3287 | 68 / 3287 | 68 / 3287 |
| 新規MMR/OCR推論 | 全68ページ | 全68ページ | 同一入力を検証してv1を再利用 |
| MMR GT177: TP / FN / 誤読 / FP | 171 / 3 / 3 / 0 | 171 / 3 / 3 / 0 | 171 / 3 / 3 / 0 |
| 既存#414とのsemantic override差分ページ | 0 | 0 | 0 |
| 認識skip→実適用の誤り | 0 | 0 | 0 |
| ページ連続性の誤り | 0 | 0 | 0 |
| GTに対する局所番号増分の誤り | 6（既知） | 6（同一6件） | 6（同一6件） |
| 実PDFのpage数 / 段頭label数 | 68 / 637 | 68 / 637 | v1の68 / 637を再利用 |
| 実PDFの埋込画像pixel照合 | 全68ページPASS | 全68ページPASS | 等価性を検証して再利用 |
| OCR call数 | 829 | 825 | 829の保持出力を再利用 |

OCR回数と経過時間は保持しているが、GPU作業が一部重なったため性能比較の根拠にはしない。
最高score重複整理は幾何が14ページ変わるため全68ページを別に実推論・出力した。
そのsemantic overrideは全件同じだったが、回避できる幾何変化を製品へ持ち込む理由はない。

幾何代表案は、全68ページの`numbering_base`と再生成MMR supportがv1と等価であることを検査した。
**さらに、整理後のbarlineから本番`_final_numbering_from_retained_geometry`を実行し、
全68ページの最終JSONがv1の実出力と完全一致することを確認した。**
同じ原画像と最終JSONに基づくため、v1の実MMR/OCRとpixel検証済みPDFを有効な証拠として再利用した。
新しいgeometryへ古いsupportを無条件にコピーしたものではない。

host/containerでsupport provenanceのmaskパス表記だけが違う場合は、参照ファイルのSHA-256一致を
確認してその一項目を同じhostパスへ解決した。他のsupport要素は完全一致を要求した。
最初の厳密比較はこのパス表記差で停止し、修正後に上記68ページを完走した。

### 独立サンプルと残存誤り

既存#415の原画像hash/物理bbox/期待値を変えずに、段頭サンプル18件を再確認。
13一致・5不一致で、既知のFestival2件とShostakovich第III楽章3件が残る。
GT177に対する局所誤りは次の6件。元の基準から除外していない。

| score/page | compact system / measure | 認識skip | GT skip |
| --- | --- | ---: | ---: |
| Festival/page_001 | 0 / 0 | 36 | 6 |
| Festival/page_001 | 0 / 2 | 0 | 3 |
| Festival/page_002 | 3 / 2 | 6 | 1 |
| Festival/page_004 | 2 / 2 | 0 | 2 |
| Festival/page_009 | 0 / 0 | 0 | 2 |
| Sibelius/page_003 | 2 / 6 | 110 | 3 |

consumer/PDF一致は間違った認識値も一貫して描画することを含む。全曲の絶対番号正解や
全movement境界の認定には使わない。今回の検証は小節線修正の新規MMR/適用回帰がないという証拠であり、
既知6件を修復したという結果ではない。#410の受容判断・実GUI補正検証は別の契約として残る。

## 実行と成果物

このworktreeの `logs/issue416/verification-20261015/` に集約。
ignoredローカル成果物でGitHub添付ではない。GPUプロセスは元checkoutを`/workspace`へmountし、
`PYTHONPATH=/workspace/.worktrees/issue416`を設定した。入力rootとコードrootを明示的に分離した。

元checkoutから実行（全て最終実行exit0）:

```bash
DOCKER_IMAGE=sha256:2706623aae2e4e6b104d3787ecf295fe6eea3c9dc2fee3b641da4b10a1c009bc \
  bash scripts/docker_runtime_validation.sh --preflight-only
```

GPUの各scriptは、上記imageに`--gpus all --user 1000:1000`、元checkout bind mount、
`PYTHONPATH`を指定して `/opt/venv_pipeline/bin/python -u` で実行:

```text
/workspace/.worktrees/issue416/logs/issue416/verification-20261015/gpu_experiments.py
/workspace/.worktrees/issue416/logs/issue416/verification-20261015/downstream_validation.py gpu_v1
/workspace/.worktrees/issue416/logs/issue416/verification-20261015/downstream_validation.py gpu_v1_dedup
```

CNNのscriptのみ、digest検証済みの共有CNN cacheを
`/opt/pdfscore-assets/barline_cnn_smoke.pth:ro`として追加mount。
正規化と重複整理の比較は同じimage/model/providerを使い、GTを生成へ参照しない。

CPUの成分整理・等価性検査は元checkoutの`.venv_pdf/bin/python`で実行:

```text
.worktrees/issue416/logs/issue416/verification-20261015/dedup_v1.py
.worktrees/issue416/logs/issue416/verification-20261015/dedup_geometry_v1.py
.worktrees/issue416/logs/issue416/verification-20261015/stable_downstream.py
```

主な記録:

- `experiment-contract.json`: 新実験定義を実行前に記録。旧契約/旧結果は別rootで保持。
- `gpu-provenance.json`, `preflight.log`: runtime/model/prototype/runner identities。
- `gpu_v1/`, `v2_overhang/`, `v2_dedup/`, `double_stroke/`,
  `gpu_v1_dedup/`, `gpu_v1_dedup_geometry/`: 全68ページの指標/予測/幾何/抑制先。
- `gpu-experiments.log`, `dedup-v1.log`, `dedup-geometry-v1.log`: 原指標と全variant。
- `downstream-gpu_v1/`, `downstream-gpu_v1_dedup/`: 新MMR support/認識/実最終JSON/PDF/PDF hash/GT監査。
- `downstream-gpu_v1_dedup_geometry/report.json`: 全68ページbase/support/実最終番号の等価性と再利用根拠。
- `downstream-gpu_v1_dedup_geometry/row-start-samples.json`: 固定サンプル18件の独立照合。
- `prototype-evaluated.py`: GPU実験時点のprototype bytesをhash一致で保存。
  review用ファイルは後でformat・幾何代表オプション・不採用tail規則の明示opt-inを追加した。
  当初hashの再現にはこの保存版と`gpu_experiments-evaluated.py`を参照する。
  現在のGPU runnerはtail規則を明示的に有効化し、同じv2実験を再現する。
- 各downstreamの`input-sha256.json`: 消費入力を記録し、処理後にも再検査。

検証prototypeは [prototype.py](prototype.py)、合成controlは [test_prototype.py](test_prototype.py)。
worktreeでの実行:

```bash
PYTHONPATH=. ../../.venv_pdf/bin/python -m pytest -q tools/issue416/test_prototype.py
```

prototype11件PASS。既存の番号/scale/system-identity/provider等を含むtargeted32件、
MMR support/provider/OCR57件もPASS（targeted32件には当初のprototype9件を含む）。
Ruff check/format、compile、相対リンク/whitespace、成果物間整合性を検査した。

## 残る検証と本番適用の境界

- src/config/model/GTを変更していないため、本番変更用の`make test-fast`とfresh GPU accuracy smokeは
  今回実行していない。GPU preflight・実成分推論・全68 MMR/OCR/番号/PDFを上記の範囲で検証した。
- 新規SR/HOMR全推論は未実施。モデル/入力不変の保持出力を使う調査なので、再実行は不要。
- 本番へ組み込んだ合意→候補生成→filter→rescue全段は未実装・未検証。
  成分実験の数値をそのまま本番の達成値としない。修正PRで保持入力から全段を再生成して評価する。
- GUIでの発見・保存・適用、配布surfaceの検証は、この調査では代替していない。
- 本番修正の残るgateと、#410で人が確認・補正して使う製品を受容できるかの判断を混同しない。
