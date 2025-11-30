# 次回セッションへの引き継ぎノート

## 使い方
- 集中作業の終了時に、完了したこと／未完了事項／次回の起点を追記する。
- 日付見出しは最新を上に配置し、JST タイムスタンプを記載する。
- 参照ログやスクリプトへのリンクはリポジトリ相対パスで統一する。

## デイリー開始チェック
- `現在の優先事項` を読み、今日の着手対象を決める。
- `最近の差分サマリ` に目を通し、直近更新されたログやスクリプトがないか確認する。
- 必要に応じて `セッションジャーナル` の該当日時へ飛び、詳細を把握する（過去ログをすべて読む必要はない）。
- 新しい情報源や仮定があれば、このセクションに追記して次回以降の起点を共有する。
- Agent AI だけで進められないタスクは下部の `Pending Manual Tasks` に追記し、依存条件と次のユーザーアクションを明記する。

## 最近の差分サマリ（最新3件）
- **2025-12-XX (Phase 30 設計):** 文脈ベースの FP 削減策を設計。残存 35 FP を stem 隣接、floating stem 等に分類し、notehead マスク等を利用した3つの新 heuristic (Notehead Proximity, Staff Span, Group Map) を提案。Heuristic 1 (notehead 近接) から段階的に実装・評価する計画を策定。
- **2025-11-30 (oemer 評価):** Phase 28 の `thin_barline_finder` 改善を oemer パイプラインで検証。TP=151, FP=34, FN=1 (Precision=0.816, Recall=0.993, F1=0.896)。homr (TP=152, FP=35, FN=0, F1=0.897) とほぼ同一の FP 数と F1 スコア。oemer の 1 FN は ML モデル起因で heuristic の回帰ではない。ログ: `logs/oemer_eval/20251130_fp_reduction_test/`
- **2025-11-30 (Phase B):** 残存 35 件の FP を詳細分析。全 FP を Group A (削減可能: 1件)、Group B (リスクあり: 2件)、Group C (許容すべき: 32件) に分類。FP=35 は heuristic ベースアプローチの実用的限界と結論。次の優先事項: oemer 移植、コンテキストベース FP フィルタリング探索。
- **2025-11-30:** `thin_barline_finder` に FP 削減策を実装 (高さ閾値厳格化、cluster guard rescue 精緻化、stem 抑制) し評価を実行。FP が 62 から 35 に減少 (−27, 43.5% 改善)、Recall=1.000 を維持。TP=152、FP=35、FN=0、Precision=0.813、F1=0.897。ログ: `logs/20251130T185351JST/`
- **2025-11-29:** `thin_barline_finder` のマルチスタッフ小節線ガードを調整した修正の評価を実行。以前の False Negative は解消され (FN=0, Recall=1.000)、TP=152、FP=62、Precision=0.710、F1=0.831 の結果を得た。FP は前回の 59 から 62 へ微増 (+3)。ログ: `logs/eval_2025_11_29_1764397202/`
- **2025-11-16:** `thin_barline_finder` に左マージン除外と縦列クラスタ抑制を追加し、homr/oemer の page_3 回帰を docker 上で再実行。homr `logs/homr_eval/20251116T220339JST_fn_guard_page3/` は TP=151/FP=59/FN=1 (Precision 0.719 / Recall 0.993 / F1 0.834)、oemer `logs/oemer_eval_regression/20251116T220457JST_baseline/` は TP=151/FP=61/FN=1 (Precision 0.712 / Recall 0.993 / F1 0.830)。左マージンのガター柱が消え、全体の FP は homr で -8、本番 FN は 1 件まで戻した。
- **2025-10-16:** homr 残留 FN {25,65,128,137} を原因別に再分類し、`logs/night_run/20251016T010433JST_fn_analysis/` へオーバーレイと統計を記録。homr/oemer 共通 FP の特徴量抽出 (`logs/night_run/20251016T010918JST_fp_features/`) と抑制ヒューリスティク草案を作成し、回帰テンプレート `tools/run_regression_template.sh` を追加。
- **2025-10-15:** 薄バー補完ロジックを縦分割対応と隣接緩和で強化。`logs/homr_eval/20251015T010556JST_fn_vertical_split_v5`（TP=148/FP=8/FN=4）と `logs/oemer_eval_codex/20251015T010745JST_baseline`（TP=152/FP=6/FN=0）で共通 FN {97,147} を回収。
- **2025-10-14:** 共通 FN 向けヒューリスティク改善と GT 補助ツール導入。関連ログ: `logs/night_run/common_fn_20251014T005323JST/`, `logs/homr_eval/20251014T010752JST_fpfilter/`。
- **2025-10-13:** `common/ort_config.py` を追加し、`transformer_memcpy` 警告制御と細幅バー補完ヒューリスティクを homr/oemer 両方に適用。ログ: `logs/homr_eval/20251013T224304JST_fn_heuristic_v3`, `logs/oemer_eval/20251013T224534JST_fn_heuristic_v3`。
- **2025-10-08:** Docker 依存のダウングレード（scikit-learn 1.2.0 等）と GPU 再評価。ログ: `logs/homr_eval/20251008T195044JST_gpu_sklearn120/`, `logs/oemer_eval/20251008T195311JST_gpu_sklearn120/`, `logs/night_run/fn_hotspots_20251008.json`。

## プロジェクトの目標
楽譜PDFを読み込み、小節番号を付与して新しいPDFとして出力するプログラムを作成する。

## 現在の主要アプローチ
`homr` 評価パイプラインと `oemer` ベースラインを並行運用し、共通のマッチングロジックで精度を比較・改善する。`src/ml_detector/barline_detector.py` は oemer のアーキテクチャを踏まえた派生実装として維持しつつ、評価成果物を `logs/` 配下に統一フォーマットで保存する。

## 現在の優先事項 (2025-12-XX stem-context 設計完了)
1.  **stem-context に基づいた FP 抑制の実装計画**: Phase 30 で設計した Heuristic 1 (notehead 近接リジェクト) を実装し、テストするための具体的な準備を進める。
2.  **homr evaluator への文脈情報 (`notehead_pred`) 受け渡しの調査**: Heuristic 1 の実装に先立ち、`homr_evaluator.py` 内で生成される `notehead_pred` マスクを、`thin_barline_finder` またはその後段のフィルタリング処理に渡すためのアーキテクチャを調査・設計する。
3.  **`thin_barline_finder` のテスト追加**: 別セッションまたはブランチにて、`thin_barline_finder` および小節線マッチングロジック (特にマルチスタッフ小節線ガードとソフトマッチ分類) に対する単体テストを追加する。
4.  **ホーム/oemer の共通 FN ホットスポットの調査**: 残留 FN (gt {25,65,128,137}) の原因調査と homr/evaluator での再評価を継続。`fn_vertical_split_v5` の成果物を起点に、左マージン処理と局所ノイズの切り分けを行う。
5.  **GT 作成支援ツールの活用**: `tools/barline_gt_helper.py` を活用し、今後 GT が必要になった際は `data/training/annotations/` 系のデータに対して追加整備する。
6.  **onnxruntime-gpu 1.24.x の監視と検証**: PyPI 公開を監視し、リリース後は sandbox 手順 (`logs/night_run/ort_1_24_plan.md`) で CUDA Graph/警告挙動を再検証する。

## 現在の課題メモ
- **（完了）未回収 FN:**  
  11/29 の評価で FN=0 を達成し、既知の FN {25,65,128,137} はすべて回収済み。
- **ヒューリスティク起因の FP 抑制:** 追加された縦線 (例: x≈212,179,315) を stem と切り分けるフィルタ（左右濃度差や notehead マスク）を設計する。
- **onnxruntime アップグレード調査:** 1.24 系などで CUDA Graph が有効化されるか、`transformer_memcpy` ノード挿入が改善するかを検証し、更新可否を判断する。
- **GT 作成支援ツールの整備:** 既存検出を下絵にしてクリックで GT を確定できる軽量ツールの運用手順を固める。

## 2025-10-16 01:12 JST
- homr 残留 FN {25,65,128,137} の原因を切り分け、左マージン強制 FP、隣接ノイズ、スタッフギャップの 3 パターンに分類。成果物は `logs/night_run/20251016T010433JST_fn_analysis/` に保存。
- homr/oemer 共通 FP を特徴量分析し、3 種の抑制ヒューリスティクを `logs/night_run/20251016T010918JST_fp_features/notes.md` に整理。
- 長期回帰用の実行テンプレート `tools/run_regression_template.sh` と計画メモ `logs/night_run/regression_plan_20251016T010918JST.md` を用意。GT 拡張後は同テンプレートで homr/oemer バッチ評価を回す。

## 2025-10-14 23:58 JST
- 今回セッションではドキュメントと指示の整備のみを実施し、コード変更や評価ランは行っていない。
- Task 4 と Task 5 は人手作業が前提のため Codex 単独では未着手。ユーザーが作業可能なタイミングを待って再開する。
- 手動タスクの記録テンプレートとして `Pending Manual Tasks` を更新。今後も同様の手順で保留項目を管理する。

### Pending Manual Tasks
- **Task 4 – GT 作成フロー拡張:** `tools/barline_gt_helper.py` を使った GT 追加はユーザー作業が必要。`data/evaluation/images` では page_003（実体は `page_3.png`）のみが楽譜ページであり、今後 GT を増やす場合は `data/training/` 配下のレンダ/アノテーションを対象にする。GT 追加後に homr/oemer 評価ランを実施し、`tools/run_regression_template.sh` の `IMAGES_WITH_GT` / `OEMER_TARGET_PAGES` を更新したうえで結果を `docs/NEXT_SESSION_NOTES.md` と night-run ログへ記録する。
- **Task 5 – onnxruntime 1.24 系監視:** PyPI 監視は自動化されていない。ユーザーが日次で `pip index versions onnxruntime-gpu` などを確認し、リリース後に `logs/night_run/ort_1_24_plan.md` の手順で CUDA Graph/警告挙動を検証する。

## 2025-11-16 22:15 JST
- `thin_barline_finder` に左マージン除外（`left_margin_limit=80`）と縦列クラスタ抑制（`cluster_reject_count=4` / `cluster_reject_span=120`）を追加。これによりガター柱やページ全体を貫く擦り傷で生成される thin_barline 候補を丸ごと無視できるようにした。
- homr/oemer の回帰を docker コンテナ内で再実行。homr `logs/homr_eval/20251116T220339JST_fn_guard_page3/` は TP=151 / FP=59 / FN=1 (Precision 0.719 / Recall 0.993 / F1 0.834)。oemer `logs/oemer_eval_regression/20251116T220457JST_baseline/` は TP=151 / FP=61 / FN=1 (Precision 0.712 / Recall 0.993 / F1 0.830)。いずれも FP を ~10% 減らし、左マージン側の検出は 8→1 本まで減少。
- 新たに 1 件の FN（thin_barline 由来）が発生しているため、cluster ガードが正しい柱まで除外していないかをオーバーレイで確認する。必要に応じて `cluster_reject_*` の閾値を微調整する。
- 残存 FP は x≈410/450/480/500 など縦列ごとに 3–4 本で留まっている。スタッフ間距離に基づく追加ガードや、左右どちらかが濃い場合の notehead 判定強化を次手とする。両パイプラインの `page_3_barline_overlay.png` を用いて局所パターンを再分類したうえで実装候補を決定する。

## セッションジャーナル
詳細な経緯は `docs/DEVELOPMENT_LOG.md` の各フェーズを参照してください。重要な更新は上記「最近の差分サマリ」でハイライトし、過去ログを遡る際は該当フェーズに移動します。
