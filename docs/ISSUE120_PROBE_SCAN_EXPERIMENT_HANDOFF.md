# Issue 120: Probe Scan 改善実験に向けたハンドオフドキュメント

## 1. 実験の背景と目的

現在進行中の **Issue 120 (FN / 検出漏れ改善) のPhase 4最終確認** において、標準的な閾値設定でパイプラインを評価したところ、**254件のFN（検出漏れ）** が残存していることが判明しました。
この「254件のFN」が具体的にどのような性質のものか、および過去に報告された「FN 20件」との関係等についての詳細な分析は、既存ドキュメント [ISSUE120_RESIDUALS_RE_EVALUATION.md](./ISSUE120_RESIDUALS_RE_EVALUATION.md) にまとめられています。

前回の再評価にて、これら最終的な小節数カウントに悪影響を及ぼしているFNの根本原因が、Phase 1における**「トールバンド希釈（Tall Band Dilution）」**および**「五線譜の激しいカスレ」**にあることが判明しました。

- **トールバンド希釈:** 余白や他パートの影響で、Probe Scanの探索範囲（Y軸のBand領域）が実際の小節線の高さよりも過大になってしまう問題。これにより、インクが濃い完璧な小節線であっても、計算上の絶対インク率（面積比）が0.85の閾値に届かずに棄却されていました。
- **激しいカスレ:** インク自体が疎らであり、正解領域だけを切り出してもインク率が低いケース。（※ただし、カスレが原因と思われるFNについてはまだ深く検討できていません。GTの付与ミスの可能性も含まれているため、後日改めてより詳細な調査と対応を行います。）

これまでのアプローチ（右端アライメント等のRescue）は有効でしたが、このBandの計算式に起因する根本的な見逃しに対しては無力です。本実験の目的は、Probe Scanのインク率評価機構を修正し、これらのFNを**新たなFPを生み出すことなく**救済することです。

---

## 2. 根本原因解決に向けた2つの実装修正方針（提案）

Phase 1の初期検出漏れをなくすため、以下の2つのアプローチを比較・提案します。どちらのアプローチを採用するかによって、修正するコードの範囲とリスクが異なります。

### アプローチA: BandのY軸範囲をより正確に捉える方法（スキャン範囲の適正化）

現在のProbe Scanは、五線帯のマスク（`staff_mask`）の上下端をそのままスキャンのY軸範囲として使用しています。これを実際の「小節線の高さ」に近づけるアプローチです。

- **実装設計:**
  1. `detect_probe_scan` 内部でX軸を走査する際、列ごとに「インクが存在する最上端のY座標と最下端のY座標」を動的に探索します。
  2. または、その列の近傍にある既存のシード（`existing_boxes`）の高さの中央値を局所的に計算し、スキャン範囲の上下端を動的に切り詰めます（現在はページ全体あるいは五線帯全体のグローバルな中央値に依存しています）。
- **メリット:**
  - 現在の「面積比（Area Ratio）」の概念や閾値（`min_ratio: 0.85`）をそのまま流用できます。分母が適正化されるため、インクが濃い（黒い）小節線は確実に閾値を超えるようになります。
- **デメリット・リスク:**
  - 掠れ（途切れた小節線）や、斜めに傾いた線の処理が複雑になります。
  - 上下の他記号（スラーや文字など）と縦に繋がってしまっている場合、結局Y軸範囲が長くなってしまい、希釈問題が再発するリスクがあります。

### アプローチB: 面積比（他の分母）を使う方法（相対ピーク/連続性の評価）

現在の「インク画素数 / (幅 × 高さ)」という面積ベースの絶対インク率への過度な依存を減らし、縦線（小節線）に特化した別の指標（分母）を評価に組み込むアプローチです。

- **実装設計 (B-1: 垂直連続性ベース):**
  - 指定したY軸範囲（Band）の中で、「縦方向に連続してインクが存在する最大の長さ（Run-Length）」を計算します。
  - 評価指標 = `(最大連続インク長) / (Bandの高さ)` とし、これが一定割合（例: 0.5）を超えていればピークとみなします。
- **実装設計 (B-2: X軸の相対ピーク・尖度ベース):** *※こちらを強く推奨*
  - 現在のコードにはすでに `scan_x_peak_ratio` という「周辺列のインクピクセル数に対する、自列のインクピクセル数の相対比（コントラスト）」を計算するロジックが存在しますが、これは現在一部のRescue時のみで使われています。
  - これを主要な判定基準に引き上げます。具体的には、絶対的なインク率の閾値（`min_ratio`）を 0.30 程度まで大幅に緩和してカスレや希釈を通過させつつ、**「ただし絶対インク率が 0.85 未満の候補については、`scan_x_peak_ratio`（周辺に対する相対的な尖度）が 1.5 倍以上であること」** といった条件を追加し、FPを防ぎます。
- **メリット:**
  - Bandの高さ（分母）が過大であっても、そのBand内での「周辺とのX方向のコントラスト」を評価するため、トールバンド希釈の影響を全く受けません。
  - 既存の `scan_x_peak_ratio` の計算ロジックを流用できるため、実装の変更が最小限で済みます。
- **デメリット・リスク:**
  - 絶対インク率の閾値を下げるため、相対ピーク条件の設定を誤ると五線を跨ぐノイズを拾いやすくなります。

---

## 3. 次セッションでの実験・評価手順

上記アプローチ（特にB-2を推奨）のいずれかを決定後、以下の手順で実装と検証を進めます。

1. **実装の修正:**
   `src/pipeline/probe_detector/__init__.py` の `detect_probe_scan` 内にある、以下の棄却ロジック付近を修正します。
   ```python
   # 現状のコード (1100行目付近)
   if check_ratio < min_ratio:
       # 即座に棄却 (scan_ratio_low)
   ```
   ここを、選択したアプローチに基づいて「絶対インク率が低くても、相対ピークが強ければ救済する」あるいは「スキャン範囲を動的に再計算する」ロジックに置き換えます。

2. **ローカルでの小規模テスト (Smoke Test):**
   問題が顕著であった `Shostakovich-Festival_Overture_Va` の `page_008` 等に対して、作成したデバッグスクリプト（`tools/debug_probe_scan_miss.py`）を実行し、GTの小節線が候補として抽出されるようになったか、また不要な候補（FP）が激増していないかを確認します。

3. **68ページフル E2E パイプラインの実行:**
   ```bash
   make run-pipeline CONFIG=configs/evaluation2_e2e_verification_full_v12_restore.yaml
   ```
   を実行し、すべてのテストデータに対して新たな Probe Scan のロジックを適用します。

4. **結果の評価:**
   - CNNフィルタリング後の結果を評価ツール（`tools/eval2_full_summary_generator.py` 等）で集計します。
   - 目標は、現在の **FN 254件 を大幅に削減**しつつ、**FPが0件（またはそれに近い水準）を維持**することです。
   - `tools/eval2_measure_count_kpi.py` を用いて、最終的な小節数カウントKPIが改善されていること（不足していた91小節が回復していること）を確認します。

---

## 4. 2026-05-09 実験結果: Low-ratio X-peak Rescue

### 実装内容

アプローチB-2を opt-in 実装として追加しました。

- 対象: `src/pipeline/probe_detector/__init__.py`
- 新規パラメータ:
  - `scan_x_peak_low_ratio_rescue`
  - `scan_x_peak_low_ratio_min`
  - `scan_x_peak_low_ratio_min_run_ratio`
- config 伝播: `src/pipeline/detection/config.py`
- 再現用スクリプト: `tools/debug_probe_scan_miss.py`

既存挙動を壊さないため、デフォルトでは無効です。`configs/evaluation2_e2e_verification_full_v12_restore.yaml` でも、実験結果を受けて `scan_x_peak_low_ratio_rescue: false` に戻しています。

### 局所検証

対象例:

- Score: `Shostakovich-Festival_Overture_Va`
- Page: `page_008`
- GT: `[1045, 3669, 1049, 3786]`
- 出力: `logs/issue120_probe_scan_xpeak_low_ratio/page_008_gt0_xp315_lr070_run050/summary.json`

実行コマンド:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/debug_probe_scan_miss.py \
  --xpeak-min 3.15 \
  --low-ratio-min 0.70 \
  --min-run-ratio 0.50 \
  --output-dir logs/issue120_probe_scan_xpeak_low_ratio/page_008_gt0_xp315_lr070_run050
```

結果:

| 条件 | candidates | target_gt_hit | 主な status |
| :--- | ---: | :---: | :--- |
| baseline | 68 | false | `accepted=44`, `x_alignment_active_injected=24` |
| xpeak low-ratio rescue | 83 | true | `scan_ratio_low_xpeak_rescued=24` |

比率スナップショット:

- `band_height=172`
- `gt_height=117`
- `ratio_at_gt=0.7311`
- `xpeak_at_gt=3.5674`

局所的には、トールバンド希釈で `min_ratio=0.85` に届かない候補を rescue できることを確認しました。

### 対象スコア9ページの実パイプライン検証

全68ページの前に、対象FNを含む `Shostakovich-Festival_Overture_Va` 9ページで実パイプラインを実行しました。

config生成:

```bash
PYTHONPATH=.:external/homr .venv_pdf/bin/python tools/create_eval2_full_restore_configs.py \
  --output-dir logs/issue120_probe_scan_xpeak_low_ratio/eval2_full_configs_v3
```

実行時は生成configの `run.output_root` を `logs/full_pipeline_runs/issue120_probe_scan_xpeak_low_ratio_v3` に変更し、以下を実行しました。

```bash
make run-pipeline \
  CONFIG=logs/issue120_probe_scan_xpeak_low_ratio/eval2_full_configs_v3/Shostakovich-Festival_Overture_Va.yaml
```

注: detection/CNNまでは完了しましたが、後段の numbering aggregation で `numbering_base.json` が存在しないため pipeline は exit code 1 になりました。このため、今回の判定は生成済み detection/CNN 出力に対して `tools/eval2_full_detection_report.py` を実行して行いました。

レポート生成:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/eval2_full_detection_report.py \
  --manifest logs/issue120_probe_scan_xpeak_low_ratio/eval2_full_configs_v3/manifest_shostakovich_festival.json \
  --run-root logs/full_pipeline_runs/issue120_probe_scan_xpeak_low_ratio_v3 \
  --gt-root data/evaluation2/annotations \
  --images-root data/evaluation2/images \
  --output-dir logs/issue120_probe_scan_xpeak_low_ratio/report_shostakovich_festival_v3 \
  --max-crops-per-type 50
```

比較結果:

| run | pages | layer | TP | FP | FN | precision | recall |
| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: |
| baseline root (`logs/full_pipeline_runs/evaluation2_full_v12_restore`) | 9 | filtered_cnn_json | 350 | 1 | 1 | 0.9972 | 0.9972 |
| xpeak low-ratio rescue v3 | 9 | filtered_cnn_json | 350 | 18 | 1 | 0.9511 | 0.9972 |

結果として、対象ページの候補段階ではFNを回収できたものの、対象スコア9ページのCNN後評価ではFN改善がなく、FPが `1 -> 18` に増加しました。

### 結論

`scan_x_peak_low_ratio_rescue` は、トールバンド希釈の代表例を候補段階で救済できる一方、現在の条件では対象スコア全体でFPを増やすため、メインパイプライン設定には採用しません。

今後この方向を続ける場合は、単純なX方向ピーク比ではなく、以下の追加制約を先に設計・検証してください。

- 低ratio rescue候補をCNNに渡す前の局所 staff membership / notehead overlap フィルタ
- 小節カウントに影響する孤立FNだけを狙うページ・段コンテキスト
- rescue候補を active alignment / gap rescue のアンカーにしない制約の維持
- full 68ページでの `FP/FN` と `measure_count_kpi` の同時評価

---

## 5. 2026-05-09 追加: Targeted Residual Replay Harness

### 目的

full pipeline は時間がかかるため、次の detector / filter 制約を試す前に、既存の中間生成物だけで最終残差を再分類するハーネスを追加しました。

- 追加スクリプト: `tools/issue120_targeted_residual_replay.py`
- 入力:
  - `tools/eval2_full_detection_report.py` が生成した `residuals.csv`
  - 既存 run root 配下の `intermediate/probe_scan/*`
  - 必要に応じて full-run manifest
  - GT: `data/evaluation2/annotations`
- 出力:
  - `residual_replay.csv`
  - `summary_by_stage.csv`
  - `summary_by_stage.json`

このハーネスは pipeline を再実行せず、以下の3段階 JSON を読みます。

- `pipeline2_no_peak_candidates.json`
- `pipeline2_no_peak_scored.json`
- `pipeline2_no_peak_filtered_cnn.json`

FN については単純な最近傍一致だけでなく、評価器と同じ `greedy_barline_match` による one-to-one matching も確認します。これにより、「候補は最終filteredに残っているが、別GTとの greedy 競合で FN になった」ケースを `survived_filtered_unmatched_greedy` として分離できます。

### 再現コマンド

baseline root の Shostakovich Festival 9ページ:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/issue120_targeted_residual_replay.py \
  --residuals logs/issue120_probe_scan_xpeak_low_ratio/report_shostakovich_festival_baseline_root/residuals.csv \
  --run-root logs/full_pipeline_runs/evaluation2_full_v12_restore \
  --manifest logs/issue120_probe_scan_xpeak_low_ratio/eval2_full_configs/manifest_shostakovich_festival.json \
  --output-dir logs/issue120_targeted_residual_replay/shostakovich_festival_baseline \
  --residual-type all \
  --residual-layer filtered_cnn_json
```

xpeak low-ratio rescue v3 の Shostakovich Festival 9ページ:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/issue120_targeted_residual_replay.py \
  --residuals logs/issue120_probe_scan_xpeak_low_ratio/report_shostakovich_festival_v3/residuals.csv \
  --run-root logs/full_pipeline_runs/issue120_probe_scan_xpeak_low_ratio_v3 \
  --manifest logs/issue120_probe_scan_xpeak_low_ratio/eval2_full_configs_v3/manifest_shostakovich_festival.json \
  --output-dir logs/issue120_targeted_residual_replay/shostakovich_festival_v3 \
  --residual-type all \
  --residual-layer filtered_cnn_json
```

過去の `issue120_final_v1` residual trace から先頭20件をサンプル分類:

```bash
PYTHONPATH=. .venv_pdf/bin/python tools/issue120_targeted_residual_replay.py \
  --residuals logs/issue120_final_residuals/residual_trace.csv \
  --run-root logs/full_pipeline_runs/issue120_final_v1 \
  --output-dir logs/issue120_targeted_residual_replay/issue120_final_v1_sample \
  --residual-type FN \
  --max-rows 20
```

### 今回のハーネス実行結果

`logs/issue120_targeted_residual_replay/shostakovich_festival_baseline/summary_by_stage.csv`:

| type | score | trace_stage | count |
| :--- | :--- | :--- | ---: |
| FN_cnn | Shostakovich-Festival_Overture_Va | survived_filtered_unmatched_greedy | 1 |
| FP | Shostakovich-Festival_Overture_Va | survived_filtered | 1 |

`logs/issue120_targeted_residual_replay/shostakovich_festival_v3/summary_by_stage.csv`:

| type | score | trace_stage | count |
| :--- | :--- | :--- | ---: |
| FN_cnn | Shostakovich-Festival_Overture_Va | survived_filtered_unmatched_greedy | 1 |
| FP | Shostakovich-Festival_Overture_Va | survived_filtered | 18 |

`logs/issue120_targeted_residual_replay/issue120_final_v1_sample/summary_by_stage.csv`:

| type | score | trace_stage | count |
| :--- | :--- | :--- | ---: |
| FN | Shostakovich-Festival_Overture_Va | candidate_absent | 6 |
| FN | Shostakovich-Festival_Overture_Va | cnn_low_score_or_post_filter | 1 |
| FN | Shostakovich-Festival_Overture_Va | survived_filtered | 1 |
| FN | Shostakovich-Sym5-Va | candidate_absent | 6 |
| FN | Shostakovich-Sym5-Va | cnn_low_score_or_post_filter | 1 |
| FN | Shostakovich-Sym5-Va | survived_filtered | 2 |
| FN | Shostakovich-Sym5-Va | survived_filtered_unmatched_greedy | 3 |

### 方針への反映

今回の結果から、次の実装候補は「候補生成だけを広げる rescue」よりも、残差タイプごとに制約を分けて検証する方が安全です。

1. `candidate_absent`: probe scan の局所 rescue 対象。ただし v3 のように FP が増えやすいため、staff membership / notehead overlap / alignment anchor 禁止を同時に評価する。
2. `cnn_low_score_or_post_filter`: detector ではなく CNN threshold または post-filter の対象。候補生成を広げる前に、スコア分布と高さ・staff単位条件を確認する。
3. `survived_filtered_unmatched_greedy`: 候補生成やCNNではなく、近接 duplicate / GT matching / logical measure boundary の問題。detector rescue では改善しない可能性が高いため、measure-count KPI への影響を優先して確認する。

次の実験では、まずこのハーネスで対象 residual の `trace_stage` を確認し、`candidate_absent` だけに限定して局所制約を試してください。その後に対象スコア単位の `tools/eval2_full_detection_report.py`、最後に68ページ full pipeline と `tools/eval2_measure_count_kpi.py` で採否を判断します。
