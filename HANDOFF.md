# Handoff: Issue #117 Resolution and Next Steps

## 1. 達成された目標 (Accomplished Goals)
本セッションにおいて、Issue #117（パイプラインにおける100% Recall/Precisionの再現失敗とFP爆発）の調査と修正を完了しました。
- **精度回復**: `Shostakovich-Festival_Overture_Va` にて、外部ツールに依存しないパイプライン単独での **Recall 100.0% / Precision 100.0% (FP=0)** を達成しました。
- **他データセットでの検証**: `Sym5`, `Prokofiev5`, `Sibelius` 等でも過去最高水準（Recall >98%, Precision >99%）を汎用的に達成することを確認しました。
- **致命的バグの修正**:
  1. **CNN画像ダウンスケールバグの修正**: CNNに1x画像が渡されているにも関わらず、SRスケール（2.0等）で誤って0.5倍にダウンスケールされる致命的なバグを修正。画像と候補座標（1x空間）を独立してスケーリング（`candidate_rescale_factor`の導入）するよう修正しました。これによりCNNの判定精度が劇的に改善しました。
  2. **VOV不一致の修正**: SR空間での候補ボックスが背高すぎる問題を解決するため、インク密度に基づいてボックスをタイトにする `trim_box_to_ink` を実装しました。
  3. **ネイティブ・ヒューリスティックフィルタの実装**: 過去の外部ツールが担っていた強力なFP除去フィルタ（左マージン、音部記号マスク、インク密度など）を `candidate_filters.py` として統合しました。

## 2. 関連ドキュメントと証跡 (Documentation & Evidence)
今回の調査結果、設定の根拠、および再現手順は以下のドキュメントに集約・コミットされています。作業再開時は必ずこれらを参照してください。
- **再現手順ガイド**: `docs/REPRODUCE_V10_RECOVERY.md` (Docker実行手順、検証スクリプトの実行方法)
- **精度低下の真因と実施した修正**: `docs/notes/issue117_resolution.md`
- **全パラメータ網羅調査と「黄金設定」の証跡**: `docs/notes/issue117_parameter_inventory.md` (全設定項目のリストアップと、現在が限界点(Pareto Front)であることの証明)
- **将来の改善ロードマップ**: `docs/notes/issue117_future_works.md` (残存FN解消に向けたアプローチ)

## 3. 次のセッションへの引き継ぎ事項 (Next Steps)
Issue #117 は本セッションで完了（解決）状態に達しています。
現在の `git status` はクリーン（コミット済）です。
次に取り組むべき課題は、極限精度（全データセットで FN=0, FP=0）に向けた根本的な改善（`docs/notes/issue117_future_works.md`）です。

- **CNNモデルの再学習 (DPI-Aware Training)**: 
  残存する数件のFN（特にSibelius等）は、SR画像のアーティファクトによって正解のCNNスコアが0.2〜0.4に落ちていることが原因です。パイプラインから生成された2x SR画像、および `trim_box_to_ink` でタイトに切り出されたパッチ画像を学習データに加え、CNNをファインチューニングしてください。
- **適応的インク密度閾値 (Adaptive Ink Ratio)**:
  `min_ink_ratio: 0.70` はノイズ除去に強力ですが、印刷の薄い楽譜（Sibelius等）では正解の小節線まで弾くリスクがあります。ページ全体のインク分布や既存ボックスの統計量から、動的に閾値を決定するアルゴリズムの導入を検討してください。