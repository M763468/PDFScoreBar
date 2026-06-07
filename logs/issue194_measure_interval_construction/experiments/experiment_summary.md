# Issue #194 局所実験結果報告書 (Local Experiment Summary)

本報告書は、小節間隔構築（measure interval construction）およびシステムグループ化（system grouping）に関する 3 つの局所実験（A, B, C）の結果をまとめ、#194 で採用可能な小修正と、リスク軽減のために follow-up イシューに逃がすべき設計変更を切り分けたものです。

---

## 局所実験 A: page_053 first interval guard (採用候補)
- **対象**: `page_053` (`Va__Prokofiev_Symphony5_page_007`)
- **問題**: インデントされた最初の段（Sys 1）の先頭にある非小節領域（音部記号・調号部分）が、`measure 1` として誤認識されてしまっている。
- **試した条件**:
  - **条件 A1**: `first_measure_width < 0.5 * median_measure_width` (Resolution-independent)
  - **条件 A2**: `first_measure_width < 1.5 * avg_staff_height` (Resolution-independent)
  - **条件 A3**: `first_measure_width < 200` (Absolute px threshold)
- **実験結果**:
  - `page_053 Sys 1`: `first_width = 179.0`, `median_width = 415.0`, `staff_height = 167.0`
    - 条件 A1 (ratio=0.43): **REJECT** (正常に非小節領域を除外)
    - 条件 A2 (ratio=1.07): **REJECT** (正常に非小節領域を除外)
    - 条件 A3 (179px < 200px): **REJECT** (正常に非小節領域を除外)
  - **他ページでの副作用検証 (page_021, page_022, page_045, page_060)**:
    - 他のすべてのページ・システムにおける本来の第1小節は、**A1, A2, A3 のいずれでも全て正しく「KEEP」**されました。
    - 他ページでの最小比率は、`page_060 Sys 10` の `ratio_to_median = 0.65` であり、条件 A1 の閾値 0.5 を安全にクリアしています。
    - また、`ratio_to_staff_height` の最小値は `page_045 Sys 10` の `1.87` であり、条件 A2 の閾値 1.5 を安全にクリアしています。
- **判定結果**:
  - **採用**: `first_measure_width < 0.5 * median_measure_width` (条件 A1) および `first_measure_width < 1.2 * avg_staff_height` 程度のガード。
  - **理由**: 副作用（正常な小節の誤消去）が一切確認されず、`page_053` の第1小節問題を安全かつ頑健に解決できるため、**#194 での実装修正として採用**します。

---

## 局所実験 B: page_060 false-positive barline / over-split (不採用・follow-up)
- **対象**: `page_060` (`Va__Prokofiev_Symphony5_page_015`)
- **問題**: x=580 付近の False Positive（誤検出）の小節線（音符の stem）により、本来 1 小節であるべき領域が `R37/R38` に過剰分割されている。
- **実験結果**:
  - `Sys 10` における誤検出小節線 `[580, 4005, 584, 4115]` の特徴をダンプした結果、他の真の小節線と**高さ (110) も y 座標範囲も完全に同一**でした。
  - さらに、CNN スコアは **`0.996486`** と極めて高い確信度で検出されていました。
  - 分割された状態での小節幅は `364px` と `444px` であり、システムの中央値（582px）に対して 0.62倍以上あるため、「interval width が小さすぎる」という比率ルールでは、正常な短い小節（弱起や変拍子）と区別できず、他ページへの副作用（regression）が極めて大きくなります。
- **判定結果**:
  - **不採用 (follow-up に移行)**: #194 での幾何学的ルールベースによる修正は副作用リスクが高いため見送ります。
  - **理由**: 小節線の幾何学的形状（bbox）や CNN スコアのみでは真偽の選別が不可能なため。**expected overrides による個別対応**、または検出器（YOLO/CNN）の stem 誤認識改善（**follow-up / #195 以降**）として対処します。

---

## 局所実験 C: system grouping feature dump (不採用・follow-up)
- **対象**: `page_021`, `page_022` (divisi merge miss)、`page_045` (system merge)
- **問題**: divisi 五線が別システムに分割されている問題と、別システムが誤って 1 つのシステムにマージされている問題。
- **実験結果**:
  - マージしたい divisi の隙間比率 (gap / avg_staff_height) は `1.53` 〜 `1.70`。
  - マージを回避したい別システムの隙間比率は `0.56` 〜 `0.84`。
  - したがって、単純な距離閾値（`DIVISI_DIST_RATIO`）を変更するだけでは、divisi のマージ漏れ改善と別システムの誤マージ回避を両立することはできません（マージのために閾値を広げると、誤マージがさらに悪化するため）。
  - また、`page_021` などの divisi では、五線の左端大括弧（bracket）の位置にアラインした小節線がないため、現在のインク接続チェック（`_check_aligned_connection`）をすり抜けて `DISCONNECTED` と判定されてしまう根本的課題があります。
- **判定結果**:
  - **不採用 (grouping redesign follow-up)**: #194 での修正は見送ります。
  - **理由**: 単純な閾値変更ではジレンマを解決できないため。**expected overrides による個別対応**、または左端ブラケット（bracket/brace）検出器の導入やレイアウト解析レイヤーの再設計（**follow-up**）として対処します。

---

## #194 での対応方針まとめ

1. **実装修正**: 
   - `first_measure_width < 0.5 * median_measure_width` による先頭非小節領域ガード（**局所実験 A**）のみを `src/measure_numbering/numbering.py` に実装する。
2. **GT fixture 修正 (コミット対象)**:
   - `tests/fixtures/expected_overrides_page_035.json` および `tests/fixtures/expected_overrides_page_037.json` の期待される overrides 追加。
3. **Follow-up課題として別イシューに切り出すもの**:
   - `page_060` の stem 誤検出（over-split）問題（検出器モデル/CNNの再学習）。
   - `page_021`/`page_022`/`page_045` のシステムグループ化（divisi マージ）問題（左端ブラケット認識の導入などレイアウト解析の高度化）。
