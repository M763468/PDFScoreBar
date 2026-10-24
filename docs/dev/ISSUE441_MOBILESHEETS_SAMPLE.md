# Issue #441: 提供されたMobileSheets実サンプルの確認

2026-10-25。[方式比較](ISSUE441_METHOD_COMPARISON.md)後にユーザーが提供した
`temp/issue441/exported_by_mobilesheets/` 内のPDFとMSFを調査した。
原本と既存結果は読取専用で扱い、実験PDF・描画・ログはworktreeの
`logs/issue441/mobile-export/` 内にだけ保持した。個人PDF・MSF・修正JSON・画像はGitHubへ添付しない。

## 結論

**このPDFは独立した注釈を保持している。背景交換で729個すべての注釈を保持できた。**
ただし、背景は保持済みの**元楽譜**そのもので、PDFScoreBarの番号付き結果ではなかった。
今回のサンプルだけでは「番号付き結果→MobileSheetsで書き込み→export→再開」の全経路を
確認したとは扱わない。checkpointの選択・追加修正・再apply・GUIも未実装。

**CropBoxが番号を切り取る問題があるため、現配置での単純交換は全体受入として不合格。**
元の表示範囲を保持した場合、160個の保存済み`label_bbox`のうち134個がCropBoxをはみ出す。
これは13ページに分布する。page 3の描画でも先頭の桁が切れることを目視確認した。
注釈が消えなかったことと、正しい番号がすべて読めることを別々のgateとする。

初回A方式の有効性を実注釈でも確認できたが、対応範囲は
「既知sourceと明示的なcrop座標対応が検証できる場合」まで。
未知のPDF rewriteや任意のannotation構造を成功として受け入れる製品APIではない。

## 入力と確認できた由来

| 入力 | SHA-256 / bytes |
| --- | --- |
| ユーザー提供PDF | `c52167c534ebde75150c7c52c11f7051e864390cfa2103640f631b0644bb89c2` / 8,797,898 |
| ユーザー提供MSF | `219f41cc45eb6b4bc07f1a75164531ea65a2f1a872ca0547855f5f8a396fa9fe` / 6,559,053 |
| 保持済み元楽譜PDF | `944fadcc68ea69e3b97897cd1e9fd3dd2ecd1ba467f426e480ed9e62be46d360` / 6,527,017 |

照合先は既存の`job-5969eee679e540d282e23fb3ecdfe205`の保持済み元PDFと
attempt 1 / attempt 12の番号付き結果。新しい推論は実行していない。

- 実PDFは15ページ、MediaBoxは全ページ720×936 pt、rotationは全ページ0。
- CropBoxは全ページで元のMediaBoxより小さく、ページごとに異なる。
  例: page 1 `[34,76,685,909]`、page 3 `[35,54,684,873]`。
  これは旧3000×3900 pt出力の誤寸法を引き継いだ例ではない。
- ページ背景は各ページ4000×5200 pxの画像1枚。
  保持済み元PDFの対応画像と、抽出した画像のバイト列が15ページとも完全一致した。
  元PDFとpage Contentsも一致。CropBoxの原点offsetを明示的に戻した画像配置も一致した。
- 注釈は **Ink 705、Circle 9、Stamp 15、合計729**。
  Stampは画像を持つappearanceを含み、人工fixtureのInk/Highlight/FreeTextだけとは異なる。
  Stampの中身を意味解析したり、ユーザーの書き込みを番号と見なして削除したりしていない。
- MSFはZIPとしては開けなかったが、保持済み元PDFの**全バイト列**がoffset 32,024から
  存在することを確認した（後続12 bytes）。PDF headerだけを検出したという判定ではない。
  MSFを改変・再生成・アプリへimportしておらず、独自の構造parserは実装していない。
- MSF内にAndroid向け保存先pathの断片がある。ただし、同期元由来の可能性もあり、
  現在のexport元OSや版の確証とはしない。OS・MobileSheets版・export設定は未確認。
  PDFのcreator/producerも空であり、設定値を復元できたとは扱わない。

MSFが曲の共有用ファイルであることは[開発元ガイド](https://www.zubersoft.com/mobilesheets/MobileSheetsPro.pdf)
に記載があるが、この資料から内部の不明byte領域を解析済みとは扱わない。

## 実験とgate

コード: [`tools/issue441/mobile_export_probe.py`](../../tools/issue441/mobile_export_probe.py)。
既存の`phase0_probe.py`の注釈appearance照合を再利用した。

1. **source照合**: 単一画像、ページ数・MediaBox・rotation、元PDFの画像bytesとContents、
   crop offsetを戻した画像配置を検証。未知の別譜面へ画像を貼る実験にはしない。
2. **背景交換**: input PDFのページ辞書・MediaBox・CropBox・annotationを残し、
   attempt 12の番号付き画像だけを交換した。旧結果の3000×3900という紙寸法はコピーせず、
   同じ縦横比の画像を元の720×936 ptの配置へ載せた。inputの注釈をスケールしていない。
3. **注釈保持**: 全729個について、辞書の全key/value、外観描画digest、座標・頂点・
   metadata等を照合。PDF辞書のkey順だけは意味を持たないため順序非依存で比較する。
4. **番号背景**: 独立に作った期待PDFを同じCropBoxで描画し、注釈を除いた背景描画と全画素一致。
   注釈の輪郭や枚数だけで成功を判定しない。
5. **可視性**: retained resultの`label_bbox`をpixel→MediaBox座標へ変換し、
   input CropBoxで包含されるかを別に検査。bboxはexact ink maskではない診断情報。
   134/160が交差または範囲外であり、全番号可視の成功を宣言しない。
6. **失敗時原本保持**: 実PDF/MSF、元楽譜、利用した2結果、番号summaryのdigestを前後で照合し不変。

### 繰り返し背景交換

未整理の生成候補を再入力すると、`get_images()`の要素数が2になり、従来の
「画像リソース1個」ガードが`single image required`として拒否した。
page Contentsでは背景の描画は1回のままで、画像置換が残した未使用リソース名が増えていた。
Stamp appearance内の画像もあるため、全画像検出数を背景描画数とみなすのも不適切。

[PyMuPDF公式資料](https://github.com/pymupdf/pymupdf/blob/main/docs/page.rst)でも、
`get_images()`が表示しない画像エントリを含み得ることが説明されている。
この拒否結果を残したうえで、**自分で生成したコピーのみ**に
`clean_contents(sanitize=True)`を適用する別実験を実施した。
整理前後で全729注釈・座標・CropBox・背景を再検証し一致。
整理済みコピーの背景をattempt 12→attempt 1へ交換しても、再び全729注釈と期待背景が一致した。
既存の番号が二重に残らないことは、交換先背景の全描画一致で検証した。

これは保存済み背景同士の2回交換であり、checkpoint復元・追加編集・新applyの検証ではない。
任意の入手PDFを先にcleanして不一致を隠す方針にはしない。
将来の独立番号Stream/markerを使うC方式ではcleanでidentityを失う可能性もあるため、
ここでのリソース整理を全出力形式へ一律適用しない。

### CropBoxを保持する候補と全ページ表示のプレビュー

- `candidate_attempt12_preserve_crop.pdf`: 元のCropBox・MediaBox・全注釈を保持した候補。
  番号が切れるので全体受入の成功成果物にはしない。
- `preview_attempt12_full_media.pdf`: MediaBoxは720×936 ptのまま、CropBoxをMediaBoxまで
  明示的に拡張した**比較プレビュー**。注釈はMediaBox上の位置を保持し、同じ表示範囲にした
  元PDFの全注釈と比較して一致した。page 3では欠けていた番号の先頭桁が読めることも目視確認。
  これは元のトリミングを変更するため、利用者が選択していない既定動作として採用しない。

製品の選択肢は「番号のために表示範囲を明示的に広げる」または
「CropBox内へ安全に番号を配置し直し、全注釈との重なりを検証する」。後者は未実装。
今回のサンプルで背景交換自体は成立しても、番号可視性を含む出力の受入は残る。
Swap Fileで内部注釈を保持する実機動作も、このPDF試験だけから成功としない。

## 実行記録

Base `602d552227c31f0c61ee5870bab80b15f341db68` + 独立PoC追加diff。
最終実行コードSHA-256は`40779b9f8571c5ed3a4f1e6e4ee3e2a6c546faa8432aa5f75c1eb9a3c00e4e16`。
環境: 既存`pdfscore_pipeline_pytest_dev`、image
`sha256:5311cf22ab0198c3384ada62101f195b0bacf6d2079574167a0edb3f66854005`、
PyMuPDF 1.26.4、UID/GID 1000:1001。manager checkoutは`/workspace`、
worktreeは`/workspace/.worktrees/issue441`。

```bash
docker exec --user 1000:1001 \
  -w /workspace/.worktrees/issue441 \
  -e PYTHONPATH=/workspace/.worktrees/issue441 \
  pdfscore_pipeline_pytest_dev /opt/venv_pipeline/bin/python \
  tools/issue441/mobile_export_probe.py \
  --exports /workspace/temp/issue441/exported_by_mobilesheets \
  --job /workspace/temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205 \
  --output logs/issue441/mobile-export/run-04
```

再実行時は未作成の出力先を指定。ログ・summary・候補PDF・PNGは同じissue root内に保持。

| 検証 | 今回の状態 / 証拠 |
| --- | --- |
| 元PDFへのsource照合・MSF内既知PDFの照合 | Passed: 15ページ一致、MSF内全byte一致。`run-04/summary.json` |
| 全729注釈・元寸法/CropBox・新番号背景の保持 | Passed: `run-04`、exit 0。辞書値・外観・座標、背景全描画一致 |
| 既存CropBoxで全番号が読める | **Failed**: 160 bbox中134が13ページで交差/範囲外。page 3の桁欠けも目視。基準を緩めない |
| 整理前の2回目交換 | **Failed / guard rejected**: `single image required`。失敗した2回目出力は公開せず、原本保持 |
| 生成コピーのリソース整理後の2回目交換 | Passed: 独立した追加実験。全729注釈・期待背景・MediaBox/CropBox保持を確認 |
| 全ページ表示プレビュー | Passed: 別候補として注釈のMediaBox位置を保持。CropBox変更は明示的な比較条件であり、元条件の可視性失敗を取り消さない |
| 初回harness | Failed: run-01は辞書key順変更を誤って属性値変更と扱った。key/valueと外観の照合へ修正。run-02の2回目拒否は保持し、run-03で拒否を記録したまま残りを検証 |
| 静的確認 | Passed: `ruff check tools/issue441/mobile_export_probe.py`、`git diff --check` |
| 実機、OS/版/設定、MSF構造import、Swap File、印刷/再export | Not run: ローカルに操作可能なMobileSheets実機・アプリ環境なし。ファイルから断定できない |
| 番号付き結果をMobileSheetsで再exportする実フロー、checkpoint/GUI | Not run: 提供PDFは元楽譜由来、製品機能未実装 |
| GPU smoke / Full68 / test-fast | Not run: 独立したファイル確認・PDF PoCのみで製品sourceやモデルを変更していない。新規推論を実行していない |

今回の総合判定は**親Issue受入未達**。注釈保持の実証を、全番号可視性・状態復元・実機での
反復ワークフローの成立と混同しない。checkpoint/stateをPDF保持方式と独立して先行できる
既存の境界は維持する。
