# Handoff: Resolution Scaling Fix & Baseline Regression Investigation

## Status Summary
- **Primary Goal Accomplished**: The systematic regression where tall barlines were lost at high resolutions (600dpi/1200dpi) due to a 400px hardcoded limit in `predictor.py` is **FIXED**.
- **Verification Result**: 
    - Verified on 64 pages across all `evaluation2` datasets.
    - **0 Tall FNs (>=400px)**: Every single full-page/system-connecting barline is now successfully detected.
    - Global Recall (Cands reaching scoring): **93.9%**.
- **Issue Discovered**: The current `v10` pipeline achieves **98.0% Recall (344/351)** on `Shostakovich-Festival_Overture_Va`, failing to reproduce a historic "100% Recall" (351/351) baseline reportedly reached in earlier PRs (e.g., #25).

## Current Fix Context
- **Modified File**: [predictor.py](file:///home/masaki_muramatsu/ws_PDFScoreBar/src/pipeline/detection/predictor.py)
- **Change**: `ThinBarlineConfig` now scales `max_height`, `std_thresh`, and `min_ink` by the `sr_scale` factor.
- **Outcome**: Restored reachability to the scoring layer for all layouts.

## Missing 7 Barlines on Festival Overture
Our debug script `tmp/debug_fns.py` identified that the 7 FNs are all:
- **Small barlines** (110-130px height).
- **Not related to the scaling bug** (which only affected tall barlines).
- **Consistently missed** even in the non-SR baseline (v1).

## Hypothesis for 100% Regression
1. **DPI History**: Historic 100% results (e.g. #25) were achieved using **300 or 360 DPI** source images. The current `v10` uses **600 DPI equivalent** (SRx2 from 360 DPI).
2. **Global Scaling Mismatch**: While `max_height` is fixed, other hardcoded pixel constants in the pipeline (e.g. min_width, ink_threshold, or matching tolerances) may still be at "300 DPI scale," causing subtle rejections at higher resolutions.
    - **Suspect Locations** ([heuristics.py](file:///home/masaki_muramatsu/ws_PDFScoreBar/src/homr_eval_scripts/core/heuristics.py)):
        - `x_bin_width = 8` (Line 673)
        - `max_x_gap_px = 40` (Line 675)
        - `right_band_px = 4` (Line 746)
        - `line_width = 2` (Line 748)
        - `abs(cx_existing - cx_extra) > 2` (Line 270 in [predictor.py](file:///home/masaki_muramatsu/ws_PDFScoreBar/src/homr_eval_scripts/core/predictor.py))
3. **GT Difference**: The current `boxes_sorted.json` might have more rigorous/different targets than the set used during the 300 DPI reports.
4. **Matching Criteria**: Older reports might have used `center_anchor` with a wider tolerance (e.g. 12-15px at 300 DPI, which is physically smaller than at 600 DPI).


## #93の枠内で#25を再現しようとしていた時のResouce
- **Verification Scripts** (located in [tools/repro_accuracy/](file:///home/masaki_muramatsu/ws_PDFScoreBar/tools/repro_accuracy/)): 
    - [verify_v10_accuracy.py](file:///home/masaki_muramatsu/ws_PDFScoreBar/tools/repro_accuracy/verify_v10_accuracy.py) (Full TP/FP/FN Accuracy)
    - [eval_final_metrics_smart.sh](file:///home/masaki_muramatsu/ws_PDFScoreBar/tools/repro_accuracy/eval_final_metrics_smart.sh) (Candidate count summary)
    - [run_eval2_bulletproof.sh](file:///home/masaki_muramatsu/ws_PDFScoreBar/tools/repro_accuracy/run_eval2_bulletproof.sh) (Batch pipeline runner)
- **Debug Artifacts**: `logs/hybrid_generalization/verify_fixed_v10/`


## ユーザーからの指摘
- そもそもこれらの作業はepic issue #5のためのもの。
- #25の終了後、epic issue #13をマージしてepic issue #5のための作業を続けている途中で、依然の結果が再現できないことが判明した。
  - 単純なパラメータ調整だけでは解決しない可能性。：リファクタリングに失敗して実装意図を変えてしまっている可能性。
  - また、Antigravityにやらせたら、返還dpiを600にしていた→#25あたりまでは300か360だったはず。（この影響が大きい可能性も高い）
- 100%再現は必須：どこでおかしくなったかをマージコミットごとに実験することで追跡してほしい
  - #25かのマージはpr #77で行われている。ここで書いてある通りの内容が再現できるかまず確認。
  - 全編を回すと一回に数時間かかるが今回は仕方ないのでやってほしい。（すべてを順に行うのではなく、二分探索でおかしくなった部分を探していけば少し楽なはず）
  - ログはartifacrsにファイル出力することで見ないようにする。（コンテキスト汚染を防ぐため）：必要なのはエラー時の確認のみ。
  - 最終的に#93の目的を達成しかつ、#25の100%再現を達成する。
  - コンフィグファイルやパスの仕様が変わってこまごまと修正したいたのもできるだけ辞めたい。
- ブランチ戦略も検討する必要がある
  - 本来なら作業用ブランチを作るが、各マージコミットの状態で同じ条件で調査するためには直接のコミットにチェックアウトして実験するのが望ましい
  - configファイルはどのコミットに対応したものかわかる形でstashしながら持っていく？or各実験を行うコミットをコピーする専用の実験用ブランチを作る？
  - いずれにせよ、現在の作業ブランチを汚染しない形で一時的な実験を続ける必要がある。
- 作業としては以下で進めてほしい
  1. dpiが以前と明らかに違うので、上記の「固定値」を画像サイズ比で計算するように変更して実験
  2. それでだめなら一度#25のコミットにチェックアウトして、そこで動作確認
  3. 移行、大きなマージコミットで動作確認を続け、どこでおかしくなったかを特定
  4. 最新のコミットに戻り、「おかしくなった点」を直す。
  5. 再度動作確認。