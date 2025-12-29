
# 記述例
---
## 2025-12-29 End barline recovery (prototype)

**作業目的 / 方針 / 位置づけ**
- 残り10件のFNのうち、end barline を最初の対象として回復するための後処理を追加。
- 検出器本体は変えず、homr evaluator の post-processing として「右端候補 x + 縦線検出 + 右側stem排除」を試行。

**作業時間**
- 2025-12-29 00:30:57 JST - 2025-12-29 00:57:01 JST

**変更したファイル（概要のみ）**
- `src/homr_eval_scripts/homr_evaluator.py`（end barline recovery の追加、overlay に END_RECOVERED ラベル付与）

**試した結果（出力ディレクトリのみ）**
- 省略

---
# 実際の作業記録