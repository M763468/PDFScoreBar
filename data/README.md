# Data ディレクトリ運用ガイド

## 階層構造

```
data/
  training/
    pdfs/            # 学習用 PDF（元データ）
    images/          # 上記 PDF を分割・画像化したページ画像
    annotations/
      page_001/
        raw_boxes.json     # 手動アノテーション直後の矩形群（未ソート）
        boxes_sorted.json  # 小節番号順に整列させた矩形群
  evaluation/
    pdfs/            # 評価対象の PDF（例: 本番スコア）
    images/          # 評価対象 PDF から生成した画像
    annotations/     # 評価用 Ground Truth（page_xxx ディレクトリを想定）
  workbench/
    captures/        # 一時的な切り出しなど試作素材
    drafts/          # 下書き GT や旧版データ（削除前提のバックアップ）
```

### 命名規約
- ページ番号は `page_001` のように 3 桁ゼロ埋めを推奨（既存の `page_1.png` 等は段階的に移行予定）。
- アノテーションファイルは用途に応じて `raw_boxes.json`（手動入力直後）、`boxes_sorted.json`（整列済み）、`labels.json`（属性付き）など明示的に命名する。
- 評価用 GT を追加する際は `evaluation/annotations/page_00x/` に配置し、同一ページ内でバージョン管理が必要な場合は `*_vYYYYMMDD.json` のように日付サフィックスを付与する。

## 運用ポリシー
- `training/` と `evaluation/` の実データは `.gitignore` で非追跡化済み。公開したい Ground Truth などを共有する場合は、該当フォルダの `.gitignore` を調整するか `git add -f` で明示的に追加する。
- `workbench/` は作業途中のファイル置き場として利用し、コミット前に不要なものを削除する。
- Ground Truth 作成フローの例:
  1. ブラウザ版 GT エディタ（`tools/gt_relabel_gui`）で矩形を追加/削除し、`raw` と `boxes_sorted` を保存。
  2. 必要に応じて `sort_measures.py` で再ソート。
  3. 検証スクリプトやドキュメントにリンクを追記。

> Note: `tools/coordinate_annotator.py` は **LEGACY**。ズーム/パンが弱く正確な作業に不向き。

## 既存データの対応表（2024-06-14 時点）
- 旧 `data/training_images/page_1.png` → `data/training/images/page_1.png`
- 旧 `data/ground_truth_page_1_new.json` → `data/training/annotations/page_001/raw_boxes.json`
- 旧 `data/ground_truth_page_1_sorted.json` → `data/training/annotations/page_001/boxes_sorted.json`
- 旧 `data/input_images/page_3.png` → `data/evaluation/images/page_3.png`
- 旧 `data/ground_truth_page_1.json` → `data/workbench/drafts/ground_truth_page_001_legacy.json`

今後の GT 整備やデータ追加もこの構造に合わせて整理すること。
