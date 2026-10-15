# Issue #416 本番修正案と追加検証

最新の本番実装・残存FNの受容判断は [IMPLEMENTATION.md](IMPLEMENTATION.md)。
以下は実装前の調査記録として保持する。

2026-10-15、`develop@016e181861270f1adc753778ef71422fa51f2716`。
[初期調査](README.md)の結果を保持したまま、GPU・MMR/OCR・最終番号/PDFまで検証を追加した。
本番の `src/`、モデル、GT、matcher、設定は変更していない。
本書は小さな修正PRへ分けるための具体案。#410のmain昇格条件を追加・変更しない。

## 推奨する修正

**複数五線bboxを五線別strokeへ正規化し、番号処理の幾何を保つ重複整理を別変更として加える。**
片側だけ長いbboxと二重線の一般分割は、今回試した規則では新しいFPが出るため採用しない。

### 変更1: 合意入力とCNN候補の五線別正規化

対象箇所:

| ファイル / 関数 | 変更内容 |
| --- | --- |
| 新設 `src/common/barline_strokes.py` | page座標のbbox、五線領域、検証済みunit_sizeを受ける純粋な正規化関数。親bboxと五線indexの由来も返す。モデルやGTは参照しない。 |
| `src/pipeline/detection/profile_sources.py` / `ProfileHybridDetector.run` | baseline staff maskから既存`StaffExtractor`と同じ五線領域を得て、元HOMRの長いbboxを五線別片へ分ける。既存SR/OMRとのIoU>0.5合意はそのまま使う。合意の弱い複合bboxを無条件に復活させない。 |
| `src/pipeline/detector_routes/candidate_generation.py` / `_run_one` | inventoryからの候補を同じ座標・五線別stroke契約で扱う。生成後の幾何・候補数・parent/staff対応を診断sidecarへ保存する。 |
| `src/pipeline/detector_routes/dense_full_pipeline.py` / rescue完了後 | rescueで再び生成された複合bboxにも、CNN前の同じ正規化を適用する。合意前だけの修正では18件の長い候補を取り残すため、最終候補境界でも必要。 |
| `src/pipeline/steps/cnn_scoring.py` | 正規化後bboxを既存preprocessingで新規採点する。親bboxのscoreは移さない。モデル・閾値・X recenterは変更しない。 |
| `src/pipeline/mmr_support_reuse.py` / 呼出元 | 修正後のPhase-A topologyからsupportを新規生成する。元geometryで作ったsidecarをキャッシュ流用しない。既存生成関数の数値ロジック変更は不要。 |

最初の実装に含める規則は、**2五線以上にそれぞれ2unit以上交差する候補だけ**を
各五線bboxとのY交差へ分割するもの。今回の検証で使った既存`StaffExtractor`の領域と
unit_sizeを引き継ぎ、別のstaff抽出法へ同時変更しない。不明な座標frame・unit_sizeは明示的に失敗させる。

元HOMRのmask・connector semanticsは保持する。長い検出bboxだけをFPとして一括削除すると
Sym5/page_021の下側五線が失われる反例がある。正規化した上下strokeで境界支持を保ち、
既存connector maskと原画像によるsystem構築は継続する。

この成分実験は、既存候補を正規化し、正規化した元HOMRの合意片を追加する範囲である。
**合意前のseedを変更した後、走査・filter・rescueをすべて再実行した実装そのものではない。**
したがってPRでは、保持HOMR/SR出力から下流detector全段を再生成するbaseline/candidate比較を追加する。
元HOMR/SRの重い推論自体は、入力とモデルが変わらなければ再実行せずよい。

### 変更2: 同一strokeの重複整理と幾何代表の固定

`src/pipeline/steps/cnn_scoring.py` の採用候補境界で、別関数として導入する。
既存の広いNMSを有効にする変更ではない。

- X中心距離<=0.1unitかつvov>=0.8の候補だけを同一strokeの重複候補として扱う。
  番号処理の1.2unitは「物理時間境界」の重複整理なので、独立stroke評価へ流用しない。
- 代表bboxは `MeasureNumberer.number_system` と同じ
  `(x1, -width, y1, y2, x2)` 順で決める。最高score順にすると14ページの小節境界が変わった。
- 代表bbox自身の実測CNN scoreを保持する。別bboxの最大scoreを付け替えない。
- 生の全scoreと、抑制した候補から代表への対応は診断用に残す。
  detector matcherへ渡す予測は整理後、候補供給/FN分類の診断には整理前も保存する。
- 同じXでも別五線の候補は統合しない。double/end/repeatの別strokeも保持する。
  今回の合成テストは1x/2x/4xと、近接した別stroke/同Xの別五線を含む。

この規則でsoftは257→121。初期baselineの100より21多い点は未解決の費用として残す。
重複をさらに減らすためにX距離を広げたり、独立stroke GTをまとめたりしない。
[prototype.py](prototype.py) はこの比較の実験実装で、本番からはimportされない。
同ファイルのsingle-tailとdouble分割は不採用の実験を含むため、そのまま本番へコピーしない。

### 別の修正として調べるもの

- `ExistingBarlines.has_existing` のY被覆条件。上側1五線の既存候補で上下band全体を
  抑制する実例を9件で確認した。正規化後の候補とscan bandを五線identityで対応させる案を優先する。
  `closest_existing_band`も同じY契約を使う必要があり、抑制閾値だけ変える修正では不十分。
  本番全段での候補数/FP/処理量を評価するまでは、既存抑制の単純無効化は導入しない。
- Sibelius/page_001のID3/4: connector尾部と1五線だけにかかるbbox。
  staff領域の外枠ではなく、持続する五線線分やstrokeのink端によるY根拠が必要。
  下記の失敗例をnegative controlへ固定し、2件だけを救う後付け閾値調整にしない。
- 二重線5件: merged bbox3件と左stroke不足2件を分けて扱う。
  原画像/maskの線別連結成分・斜行・太さを確認し、音符の符幹との区別を含むproducer修正へ進める。
  今回の列profile法ではID16/17だけ救え、3件は残り、新しいFPも出た。

## 固定契約での全68ページ比較

GT3567、center_anchor、vov>=0.5、X距離<=0.5unit、CNN閾値
`0.4965248107910156`、同じEfficientNet-B0重み。入力画像・GT・元出力hashは固定。
実験を追加する前に各規則を`experiment-contract.json`へ保存し、以前の結果を上書きしていない。

| 実験 | TP | hard FP | FN | soft | 物理小節数 | 判定 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 元保持 | 3535 | 11 | 32 | 100 | 3287 | 原基準を保持 |
| 複数五線正規化 v1（GPU） | 3560 | 0 | 7 | 257 | 3287 | 成分候補として有望 |
| v1 + 最高score代表の重複整理 | 3560 | 0 | 7 | 121 | 3287 | 14ページで幾何変化。幾何固定案を優先 |
| **v1 + 番号処理と同じ幾何代表** | **3560** | **0** | **7** | **121** | **3287** | **修正案の第一候補** |
| v2: 片側>=2unitの尾部もclip | 3562 | 2 | 5 | 260 | 3287 | **不採用: 新規FP2** |
| v2 + 最高score重複整理 | 3562 | 2 | 5 | 119 | 3287 | **不採用: 同じ新規FP2** |
| 原保持 + 列profileによる二重線分割 | 3537 | 12 | 30 | 220 | 3287 | **不採用: 新規FP1** |

v1の392新cropを元推論と互換なimage/RTX4060で再採点し、前回CPUとの採否・指標が全68ページ一致。
v1では67ページの五線所属/小節bboxが元保持と一致し、Sym5/page_005の下側divisi五線だけが
正しく小節領域へ復帰する。幾何代表の重複整理はv1と68ページ完全一致。

### 新しい回帰を除外しなかった記録

v2の新規FPはSym5/page_022の `[1513,1245,1517,1306]` と `[3491,1245,3495,1306]`。
元候補はそれぞれY=1050..1306でCNN score約0.01577/0.00044。
粗いstaff外枠でYを切ると1245..1306の短い片になり、CNN採用側へ変わっても独立stroke GTと
幾何一致しない。両位置は元画像にも接続小節線があるが、**新しい評価FPとしてそのまま計上する**。
元の合計FP11より少なくても、このページのFP0→2は回帰。小節数0差を理由にpassへ変えない。

二重線profile法はID16/17を救うが、Sibelius/page_008に新FP `[1453,3140,1454,3247]` を作る。
新FNは0だが、FP11→12/soft100→220のため採用しない。

## 変更1・2の受入条件

これは当該修正の受入条件であり、#410/main昇格条件ではない。

1. 現行固定68ページの旧指標を再現し、HOMR/SR保持出力から合意・候補・filter・rescue・CNNの
   baseline/candidate全段を比較する。全ページ別TP/FP/FN/soft、候補数と処理量を残す。
2. 変更1の目標はTP3560/FP0/FN7の再現と、新規hard FP/FNが0であること。
   変更2はそのTP/FP/FNを悪化させず、全68ページで変更1の五線所属/小節bbox/基礎番号を保持すること。
   soft121は今回の観測値。今後softが増える場合も必ず報告し、precision改善と取り違えない。
3. 元mask/connectorを残し、Sym5/page_005の下側五線を含む4小節領域を回復する。
   Sym5/page_021で下側五線を落とさない。数だけでなく、五線と物理小節の所属を検査する。
4. 変更後geometryからMMR supportを再生成し、同一モデル/明示CUDAで全68ページのMMR/OCRを比較する。
   受理済み#414のTP171/FN3/誤読3/FP0に新しい回帰を加えない。GT177と既知6件を除外しない。
5. 認識skipと実適用増分、ページ連続性、per-page/combined/実PDFの段頭番号を照合する。
   #415独立段頭サンプルとmovement reset等の既知限界を保持し、絶対番号の全曲正解とは表現しない。
6. 実装時に通常のtargeted tests、test-fast、canonical GPU accuracy smokeと配布surface検査を実施する。
   新共通モジュールを採用する場合はrelease manifest/依存宣言も更新し、開発toolを製品依存にしない。
   本調査だけで本番全段/GUI/配布の検証が済んだとはしない。

## 検証記録

追加の詳細と再現コマンドは [VERIFICATION.md](VERIFICATION.md)。
未commitの検証prototype・テスト以外に本番差分はなく、Issue/PRの作成・更新、push/mergeは行っていない。
