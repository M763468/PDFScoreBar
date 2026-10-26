# Issue #441: 共有された書き込み済みPDFを土台に修正を再開する

[GitHubレビュー入口・公開検証スナップショット](ISSUE441_REVIEW.md)から、
ローカル成果物を開かずに手法・結果・コード・テストを確認できる。

**後続の可読性レビュー対応:** [全段9pt・段への近接・保存後失敗時の確定処理](ISSUE441_PR445_REFINEMENT.md)。
以下の8〜10ptと保存手順は初回実験の記録。現在の実装は上記の対応記録を参照。

2026-10-25。ユーザーの指示により、共有PDFそのものを利用対象として
「番号を置き直す」「保存済み修正から再開する」両方を設計・実験した。
原譜由来であることはこの入力を対象外にする理由ではない。
**書き込み済み原譜＋既知のsource対応＋選択した修正状態**を、正式に扱う入力モードとする案。

## 推奨方式と今回できたこと

**元の背景画像・729注釈・MediaBox・CropBoxを残し、番号だけを独立したPDF content streamへ追加する。**
現在のCropBox内の空白を探して配置し、次回はPDFScoreBar自身の番号streamだけを入れ替える。
白塗り、手書きの意味推定、書き込み画像の再合成、CropBox拡張は行わない。

共有された15ページに、この方法で**全160番号を8〜10 ptで配置できた**。
さらに保存済みattempt 1とattempt 12を別々の新レビューセッションへ復元し、
実際の下流再apply、MMRの追加修正、取消、番号レイヤーの置換まで実行した。
これは以前の背景画像同士の交換だけのPoCから進めた実験である。

| Gate | 今回の結果 |
| --- | --- |
| 全番号がCropBox内 | 2つの修正状態と編集・取消後の各出力で160/160。CropBox・MediaBoxは元と同一 |
| 元データの保持 | 背景画像のbytes不変、729注釈の属性・外観・座標等が一致 |
| 元の画素の保持 | 144 DPI描画で元RGBのいずれかが250未満の全画素を比較し完全一致 |
| 修正の継承 | attempt 1 / 12ともraw corrections identity一致、全ページ・全小節の番号列が各保持済み結果と一致 |
| 追加MMR修正 | 内部page=1, system=10, measure=9のspanを5→6。表示上の第3ページ先頭番号158→159 |
| 取消 | raw修正を元へ戻し、全ページの全番号列がbaselineと完全一致 |
| 旧番号の除去 | 自分のstreamだけを除いた描画が元の書き込み済みPDFと完全一致してから次状態を追加 |
| 再読込 | 2つの新packageを再作成し、current結果・修正identity・成功PDFを復元できた |
| 原本・過去結果 | 元データはread-only mount、出力はissueログ専用mount。元PDF digestも前後一致 |

従来の固定gutterで134/160 bboxがCropBoxにかかった結果は
[過去の実サンプル確認](ISSUE441_MOBILESHEETS_SAMPLE.md)として残す。
新方式は別の配置実験であり、以前の結果を遡って合格に変更しない。

## 1. 書き込み済みPDFの扱い

共有PDFのMediaBoxは720×936 pt、CropBoxはページごとに異なる。
背景は保持済み元PDFと15ページとも一致し、Ink 705・Circle 9・Stamp 15が独立して存在する。
元PDFとの対応が証明できるため、保持した認識・幾何と選択修正を利用できる。

**「PDFScoreBarの番号付き出力に書き込んだPDF」であることを、再開の必須条件にはしない。**
入力を次の2モードに分ける。

1. **書き込み済み原譜から開始（今回の共有PDF）:** 既存の書き込みをすべて残し、選択checkpointの
   正しい番号を新しく配置する。元から印刷された数字や手書き数字はユーザーの内容として保持する。
2. **PDFScoreBar番号付きPDFから再開:** 旧番号の生成結果または自分の番号streamを識別し、
   旧番号を除いた上で新番号へ更新する。既存ラスタ出力は従来A方式との照合が必要。
   来歴不明の数字を手書きか番号か推測して消さない。

修正状態のcheckpointと入力PDFの出所は別に記録する。
元の楽譜に注釈が付いた今回の入力へ、attempt 1でもattempt 12でも適用できる。
特定のPDF書き出し結果とcorrection checkpointが同一attemptであることを要求しない。

## 2. CropBox内での安全な番号配置

実験開始時に固定した配置・受入条件は次のとおり。検出・OCR・MMRの閾値は変更していない。

- 出力番号は8〜10 pt。基本サイズはtop staff高さの0.20倍を8〜10 ptへ制限し、8 ptまでの
  fallbackを最初から候補に含めた。これより縮めて成功数を稼がない。
- 座標は保持済みsource image pixels → MediaBox points → CropBox相対座標へ変換する。
  行のtop staff近傍を探索し、前の行との中間より上へは移動しない。
- 新番号bboxと余白がCropBox内に入り、他の新番号と重ならないこと。
- すべての既存注釈のbboxとの重複も拒否する。可視の画素が白くても、白い注釈を無視しない。
- 書き込みを含む元ページを144 DPIで描画し、候補領域は全RGBが250以上の近白色領域に限定。
  字形だけでなくfont metricsと余白を含む矩形を検査する。
- 出力を再度描画し、元ページのRGBいずれかが250未満の**全画素**が不変であることを確認。
  この画素条件は「近白色紙面への新規印字」のgateであり、不可視の書き込みを復元する推定ではない。
  元背景bytesと注釈オブジェクトも別に保持・照合する。
- 安全な位置がない場合は出力を成功扱いしない。元入力・過去結果を保持し、将来GUIでは
  手動配置または表示範囲変更を利用者が明示選択する案とする。

全160番号が最初の配置実験でこの条件を満たした。代表的なpage 3とpage 10を目視確認した。
全ページの実印刷による読みやすさや利用者受入は未確認だが、番号の切れ・書き込みへの上書きで
合格数を増やしてはいない。

コード: [`crop_label_layer.py`](../../tools/issue441/crop_label_layer.py)。
番号streamは`PDFScoreBarNumbers` markerで識別し、sidecarへstream digest・xref・元Contents・
入力/出力PDF digest・配置・番号を記録する。
再更新時はsidecarとPDFを検証し、自分のstreamだけを外す。
取り外した全ページ描画が元の書き込み済みPDFと一致しなければ、別の内容を消した可能性として拒否。
その後、新しい番号レイヤーを配置する。画像全体を再符号化しないので4000×5200 pxの背景を保つ。

これは現在の実験出力とsidecarを対象とした更新方法である。
MobileSheetsで再exportされxref・stream・markerが変化した入力を、そのまま受け入れる検証器は
未実装。外部で加えた正当な書き込みを捨てるfallbackは不可とし、今後は保存したsource/result
identityと番号要素を照合して、新しい入力のユーザー注釈をすべて保持する設計が必要。

## 3. 保存済み修正を引き継いだ再開実験

コード: [`annotated_resume_experiment.py`](../../tools/issue441/annotated_resume_experiment.py)。

1. attempt 1 / 12の`input_review`から宣言済みsourceとraw correctionだけを別packageへcopy。
   元のconsumed corrections identityと一致することを検証した。
2. 旧`/results/<job>/...`は指定した既知job root内へ固定prefixで対応付ける。
   source manifestをコピーし、保持済みnumbering baseもコピーして、元state/resultはコピーしない。
   元identityと再配置後identityを別にprovenanceへ記録する。
3. `ReviewPackage`と`CorrectionApplication`の既存経路で実際に再apply。
   新packageのbaselineが各保持済み結果の全小節番号列と一致した。
4. attempt 12で既存MMRのspan 5→6を`record_correction`で保存。
   current結果がなくなり、各stateがstaleとなっても、過去の成功結果は保持された。
5. 再applyで後続番号が1増加し、書き込み済みPDFの番号レイヤーを交換。
   第3ページの先頭は158→159になった。
6. 同じSave経路でMMRを元に戻し、もう一度applyして全番号列を完全復元。
   PDFの番号レイヤーも交換し、3回の出力を通して729注釈・背景・CropBox・元の濃い画素が不変。
7. 新packageを再読込し、修正identityとcurrent結果・成功PDFが復元できることも確認。

取消時も既存Saveを通すため、対象ページのitemsがJSON末尾へ移動し、raw correction identityは
初期の`48b3...`から`b858...`へ変化した。修正項目集合と全番号列は元に戻っているが、
過去のidentityを無理に再使用しない。再読込では**最終保存されたidentity**とcurrent結果が
一致することを確認した。これは意味上の取消であり、初期JSONのbyte同一性を主張しない。

復元した修正はMMRと小節線変更を含む。元packageにない楽章境界を実データへ追加した試験や、
小節構成の全操作を試したわけではない。既存のraw保存とconsumer契約を維持している。

## 4. 利用者導線と実装境界

実装する導線は以下を推奨する。

1. **「書き込み済みPDFから再開」**へ今回のPDFを渡す。
2. 元jobと特定の保存済み修正状態を選択。source一致と、原譜/番号付き結果のモードを表示。
3. **元のトリミングと書き込みを保持**することを既定にし、新sessionへ修正を復元。
4. レビュー表示は書き込み済みPDFの描画を使用し、geometry/consumer用のclean source画像とは
   別の表示artifactにする。認識へ書き込み画像を差し戻して再検出する設計にはしない。
5. MMR等を追加修正・取消・Save/Apply。staleと過去成功結果を区別する。
6. CropBox内の番号プレビューを確認し、新PDFと状態を保存。
   配置不能ならその行を示し、手動配置/表示範囲変更を明示選択してもらう。

今回の実験packageは既存レビューserverから読み込める形式だが、upload・checkpoint一覧・
書き込み済み背景のGUI表示・番号配置UIはまだ製品実装していない。今回実証したSave/Applyは
既存の実クラスを呼び出したもので、ブラウザ操作・download導線の受入を済ませたとはしない。
MSFの内部注釈をPDFScoreBarで編集する設計や、Swap Fileへの自動操作は不要。
新しいcheckpoint/再開contextと、実験した番号レイヤーを1本のFeature PRへ段階的に統合する。

## 5. 実行環境と証拠

Base: `48cc8e376bb3efdf96b348884f8084394c936838` + 今回の実験コード/テスト。

- `crop_label_layer.py` SHA-256: `46345b5e0a0c3f829dbc903f4bda10f2cff7c74ae19a02e4996d96bb27f79486`
- `annotated_resume_experiment.py` SHA-256: `d9375fb1b8887bfcd0d51607ce7ce1a3e656ad97b1fa97c1521c75ecf00f9343`

互換imageは`sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a`。
host resolverでruntime compatibility一致を確認した。元の共有pytest imageは現在のruntime契約と
不一致だったため、pipeline再applyには使わず、ローカルの互換imageを選択した。
manager checkoutは`/workspace:ro`、書込先はissueログだけの別mount。UID/GID 1000:1001。

下流再applyは保持済み認識を使うが、**MMR OCRの再計算は含まれる**。
`--gpus all`で起動し、4回の実engineで`text_rec`の実providerが
`['CUDAExecutionProvider', 'CPUExecutionProvider']`であることを記録した。
provider検査wrapperは本物のengineを返し、CUDA不使用を検出したら失敗にする。
detector/HOMR/SR/OMR-DLNの上流再推論やFull68は行っていない。

```bash
docker run --rm --gpus all --user 1000:1001 \
  -v /home/masaki_muramatsu/ws_PDFScoreBar:/workspace:ro \
  -v /home/masaki_muramatsu/ws_PDFScoreBar/.worktrees/issue441/logs/issue441:/workspace/.worktrees/issue441/logs/issue441 \
  -w /workspace/.worktrees/issue441 \
  -e PYTHONPATH=/workspace/.worktrees/issue441 -e PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /opt/venv_pipeline/bin/python \
  sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a \
  tools/issue441/annotated_resume_experiment.py \
  --job /workspace/temp/pdfscorebar-results/job-5969eee679e540d282e23fb3ecdfe205 \
  --pdf '/workspace/temp/issue441/exported_by_mobilesheets/Nielsen-Sym4 Vn2 書き込み.pdf' \
  --output logs/issue441/annotated-resume/resume-02
```

再実行時は未作成の出力先を指定する。
`resume-02/summary.json`、`resume-02/restart_check.json`、`resume-02.log`、各sessionの
`resume_provenance.json`・apply attempt・sidecarをローカル保持。
個人PDF・MSF・修正JSON・PNGはGitHubへ追加しない。

| 検証 | 今回の状態 |
| --- | --- |
| 15ページ160番号、CropBox/注釈/濃い画素/背景bytes保持 | Passed: `layout-01`と`resume-02`の各出力。代表page 3/10を目視 |
| 2つの状態の復元・baseline再apply | Passed: corrections identityと全ページ全小節番号列一致 |
| MMR追加・stale・再apply・取消 | Passed: 5→6、後続158→159、取消で全番号列が元に復帰 |
| 旧番号レイヤーの除去・反復更新 | Passed: 除去後は元PDF全描画と一致、新番号text列も各行と一致 |
| 再読込 | Passed: `restart-02.log` / `restart_check.json`。両sessionとも最終保存identityとcurrent、成功PDFが一致。取消前後で修正項目集合も一致 |
| focused test | Passed: `python -m unittest discover -s tests -p test_issue441_annotated_layer.py -v`、5件。空きなし、白い不可視注釈、改変PDF、改変stream digest、更新時の旧番号除去を確認 |
| 静的確認 | Passed: 新規3 Pythonファイルの`ruff check`、`git diff --check` |
| 初回再apply環境 | Blocked/無効: `resume-01`はGPUを渡さずCPU fallbackを検出。専用コンテナを停止し受入証拠から除外。`resume-02`でGPUと実providerを確認して再実行 |
| 初回再読込harness | Failed: `restart-01`は取消後identityを初期identityと比較した。Saveによる項目順変化を確認し、最終保存identityとの一致と意味上の項目集合復元を別に検証。失敗ログは保持 |
| browser/UI・実印刷・MobileSheetsでの再export往復・全修正タイプのE2E | Not run: 今回は設計と実データ実験。製品GUIは未統合 |
| Full68 / 上流GPU smoke / test-fast | Not run: 製品pipeline source/閾値は未変更。保持済み15ページの下流実験とfocused testで今回の契約を検証 |

今回の依頼に対して、共有PDFを使った具体的な再開・再配置方法と実験成果物を得た。
親IssueのGUIを含む製品機能すべてが完了したという扱いにはしない。
