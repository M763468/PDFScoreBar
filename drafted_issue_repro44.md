## ブランチ運用
- Base branch: investigate/sr-optimization
- Branch name: fix/reproduce-issue44-recall
- PR base: investigate/sr-optimization

## Goal
現在のパイプライン（SR x4構成）において、Issue #44 で達成されていた Recall 100%（Prokofiev page 1 等）が再現できない問題を修正する。
特に、`probe_scan` における「幅の広い BBox の分割（wide split）」ロジックが正しく機能していない、あるいは退行している原因を特定・解消する。

## Done
- [ ] Prokofiev page 1 において、SR x4 設定で Recall 100%（FN 0）が再現されている。
- [ ] 密集した二重線が `probe_scan` または `wide_split` ロジックによって正しく 2 本に分離されている。
- [ ] 退行の原因（設定漏れ、ロジックの不具合、DPIの影響など）が特定され、ドキュメント化されている。

## Notes
- Issue #25 の調査中に、現行の x4 実験結果（Recall 97.65%）が過去の #44 の成果（Recall 100%）に及ばないことが判明した。
- `homr` のプロキシ縮小だけでなく、後続の救済ロジックの不備が疑われる。
- この Issue が解決するまで Issue #25（SR最適化）はペンディングとする。
