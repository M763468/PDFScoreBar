# 手動補正レビューワークフロー

<!-- translation: {"original":"manual_correction_review_package.md","source":{"sha256":"12dd91cb143f228159274caa75f67687d9269a10a896f8872bb1f569f7d759bf"},"state":"reviewed"} -->

[English / 原文](manual_correction_review_package.md)（英語正本）

翻訳元: same PR / SHA-256 `12dd91cb143f228159274caa75f67687d9269a10a896f8872bb1f569f7d759bf`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

この開発者・運用担当者向けリファレンスは、現在の config-first の手動補正ワークフローを説明します。一つのパイプライン実行を既存の手動 GUI に接続し、パッケージ内に補正を保存して、補正を使ってパイプラインを再実行し、補正済みの小節番号付き最終 PDF を生成できます。

これは config-first の開発・運用リファレンスであり、新しい公開 `pdfscorebar` コンソールではありません。サポート対象の利用者向け配布ワークフローは[ユーザーガイド](../USER_GUIDE.ja.md)を参照してください。ここでは `make run-pipeline`／`src.pipeline.main` と既存のレビューヘルパー、GUI を使用します。

## 1. レビューパッケージを出力する

手動補正レビューの出力を明示的に有効にします。

```yaml
outputs:
  review:
    manual_correction_package: true
    # optional; relative paths are resolved from the internal run_dir
    root: review
```

通常のパイプラインを実行します。

```bash
make run-pipeline CONFIG=<config.yaml>
```

既定ではパッケージは内部パイプライン実行ディレクトリの下に出力されます。

```text
<run_dir>/
  review/
    manual_correction_input.json
    pages/<page_id>/
      source.png
      numbering_final.json
      review_overlay.png        # optional pre-rendered evidence
      mmr_overrides.json
      barlines_review.json
    corrections/
```

`outputs.review.root` でパッケージのルートを変更できます。

- 相対パスは `<run_dir>` を基準に解決されます。
- 管理された呼び出し元が既にレビュー用ディレクトリを所有している場合、絶対パスも使えます。
- マテリアライザーには、選択された元の実行から得られた numbering／MMR／barline 成果物が引き続き必要です。manifest に記録された厳密な `image_path` は楽譜ごとの実行ディレクトリ外（たとえばバッチ共有の `input_images/`）にあってもよく、別の実行を探さずにパッケージへコピーされます。

handoff は GUI に必要なページ識別情報と座標空間の関係を記録します。通常の手動レビューは、無関係な `logs/` の実行から画像、番号付け、MMR、小節線のパスを組み合わせるのではなく、この handoff から開始してください。

PDF から直接描画する場合、各ページには任意の `page_size_points: [width, height]` も PDF ポイント（1 インチあたり 72 ポイント）で記録されます。レンダラーは描画に使用した同じ元データから crop／回転後の表示サイズを取得し、manifest、review handoff、公開パッケージ、補正スナップショットがそれを保持します。最終 PDF はラスタライズ DPI や目標ピクセルサイズが変わっても元 PDF を再度開かずにこの寸法を使います。古いパッケージでは利用可能なら画像の DPI を使い、なければ 300 DPI を仮定した警告を出します。このフォールバックでは元の用紙サイズを保証できません。明示的な寸法が不正なら拒否されます。

`--skip-existing` で描画済み PDF 画像を再利用する場合、実行の `inputs/pdf_render_provenance.json` が現在の PDF のバイト列、選択ページ、ページサイズ、キャッシュ画像のハッシュに一致するときだけ、その幾何情報が受け入れられます。検証済みの記録がない既存画像キャッシュは、レビューパッケージを作成する前に `--skip-existing` を付けず再描画しなければなりません。

レビューパッケージは元の実行で detector が生成した成果物を忠実に表示しますが、それ自体は本番精度の証拠にはなりません。見える見落としや誤検出を本番の回帰と解釈する前に、元の manifest が現在の `dense_full_pipeline` detector 契約と本番モデルの manifest／閾値を使用していることを確認してください。標準の `make verify-gpu-smoke`／`make run-smoke` 経路はこれを自動的に確認し、1 ページの detector 結果を正規 GT に対して判定します。ワークフロー専用または旧 smoke 成果物から本番 detector の精度に関する結論を出してはいけません。

## 2. handoff から利用者向け補正アプリを開く

標準 Docker パイプラインでレビューパッケージを生成した場合は、同じ管理対象 Docker ランタイムで GUI を起動します。bind mount された worktree 上のパイプライン成果物はコンテナユーザーの所有の場合があり、ホスト側の GUI プロセスに `review/corrections/` の書き込み権限があるとは限りません。

以下の Docker 例は、`<review_root>` が `/workspace` にマウントされたリポジトリ内にあると仮定します（既定の `<run_dir>/review` を含む通常の場合）。管理された呼び出し元がリポジトリ外の絶対 review root を使う場合、そのディレクトリを別途コンテナ内のパスへ bind mount し、`--handoff` にはコンテナから見えるパスを指定してください。handoff が参照する保持済み元成果物にも、記録されたパスでアクセスできる必要があります。

```bash
docker run --rm -it --network host \
  -v "$PWD":/workspace \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python tools/review_correction/server.py \
  --handoff <review_root>/manual_correction_input.json \
  --port 8010
```

その後 `http://127.0.0.1:8010` を開きます。

現在のホストユーザーが既に書き込めるレビューパッケージであれば、軽量なホスト起動も有効です。

```bash
python3 tools/review_correction/server.py \
  --handoff <review_root>/manual_correction_input.json \
  --port 8010
```

利用者向け補正の入口は次のように動作します。

- GUI を提供する前に厳密な同一パッケージのレビュー契約を検証します。
- 元画像、最終番号付け、MMR 証拠、レビュー用小節線が存在することを要求します。
- 描画済みレビュー overlay があれば受け入れますが、必須ではありません。手動 GUI は基礎成果物から有効な小節／小節線／手動状態の overlay を描画します。
- handoff のレビュー用ディレクトリを GUI のルートとして使います。
- `--handoff` と `--port` のみを受け付け、loopback に bind します。
- handoff に宣言された成果物のみを提供し、宣言された `review/corrections/` 配下の出力先にのみ書き込み、要求ごとに解決後のパスを再検査します。
- 現在のページ単位の `manual_outputs` ルーティングを維持します。

任意パスを使う旧 `manual_config_builder.py` はサポート対象外です。管理対象の手動ワークフローは、上記の検証済みパッケージ内 `review/manual_correction_input.json` handoff から開始します。

### 任意の楽章境界の証拠

通常のレビューパッケージでは detector の証拠なしでも手動境界を使えます。**Movement boundary** を選び、新しい楽章の最初のシステムを選択して境界を確定します。判断とパッケージ内の確定済み入力は即座に保存され、**Generate corrected PDF** を使用すると、そのシステムの前で番号が 1 に戻ります。手動境界の削除も確定済み入力を更新します。保存されたレビューのハッシュはその入力を現在の判断に結び付けます。失敗または古くなった保存は適用前に解消する必要があります。

手動レビューで証拠がない場合を含め、すべての handoff ページは一つの共通 `correction_outputs.movement_boundary` パスを使う必要があります。既定値は `corrections/movement_boundaries_review.json` です。他の補正種類ではページごとの出力を使えますが、カスタム設定でも楽章レビューパスは共通にしてください。handoff 検証は補正の保存や適用より前に異なるパスを拒否するため、あるページの保存で共有の確定済み入力内の別ページの楽章判断が置き換わることはありません。

Detector の提案をレビューするには、同じレビューパッケージに レビュー専用の楽章境界証拠成果物を添付します。

```bash
python -m tools.movement_boundary_review attach \
  --handoff <review_root>/manual_correction_input.json \
  --evidence <run>/movement_boundary_evidence.json
```

attach は証拠をパッケージにコピーし、パッケージ内のパスを handoff に記録します。候補の承認や番号付けの変更は行いません。その後 **Movement boundary** 補正種類にも detector の候補が表示されます。楽章境界は常に**対象システムの直前**を意味し、そのシステムの最初の小節から新しい楽章が始まります。レビュアーはシステム内のどこをクリックしても対象にでき、1 始まりのシステム番号を直接入力することもできます。**boundary** または **no boundary** の確定時に楽章判断は即座に保存され、この種類に別の Save 操作はありません。楽章 UI は無関係な Select／Draw／Save コントロールを隠し、保存済みの判断が選択されたときだけ消去コントロールを表示します。キャンバスには **Suggested boundary**、**Confirmed boundary**、**Checked: no boundary**、**Boundary used by current numbering** の利用者向け状態が表示されます。Pages 一覧にも未確認の提案や保存済みの楽章判断があるページが示されるため、楽譜全体のレビューでページを手探りで開く必要はありません。**Finish movement review** はすべての提案境界のレビュー後にのみ有効になり、次の番号付け実行用の境界入力を作成します。GUI に現在表示されている楽譜は変更しません。

### 手動 GUI クイックガイド

利用者アプリでは左にページ一覧、上部に **Save this page** と **Generate corrected PDF**、右側のコンテキストパネルに補正タスクと保存／結果の状態を配置します。ページを変更すると未記録の編集が自動保存され、PDF 生成には全ページの保存済み補正が使われます。拡大したページは **Move page** モードでドラッグできます。

Overlay の初期状態:

| Overlay | 初期状態 | 用途 |
| --- | --- | --- |
| Measures | オン | 通常の小節の幾何を表示します。 |
| Barlines | オン | 現在の小節線の幾何を表示します。 |
| Labels | オフ | 通常の overlay ラベルを表示します。楽譜の混雑を減らすにはオフにします。 |
| Original grouping | オン | 基礎／自動 MMR 状態を表示します。 |
| Manual state | オン | 未記録の手動編集を表示します。 |

便利なレビュー表示:

- **小節線のみ:** Measures オフ、Barlines オン、Labels オフ、Base MMR state オフ、Manual state オフ。
- **小節のみ:** Measures オン、Barlines オフ、Labels オフ、Base MMR state オフ、Manual state オフ。
- **未記録の小節線削除:** Manual state をオンにしたまま Barlines をオフにできます。削除予定は通常の小節線レイヤーとは独立して表示されます。

選択中の対象と有効な下書きは、通常の overlay レイヤーを隠していても表示されます。選択対象は別途強調されるため、レビュー対象を見失わずに overlay の密度を下げられます。

MMR／小節線／小節補正の典型的な流れ:

1. 右側のコンテキストパネルで補正タスクと変更を選びます。
2. 対象を選択します。小節線編集ではさらに Select／Draw モードが表示されます。
3. 編集を作成し、キャンバスとタスク別一覧で未記録の変更を確認します。
4. 不要な変更なら編集を消去します。
5. **Save this page** でこれらの補正を記録します。

楽章境界レビューはより単純です。システムを選択し、**boundary** または **no boundary** を確定すると判断は即座に保存されます。すべての提案境界のレビュー後、**Finish movement review** で次の番号付け実行が消費する境界データを作成します。証拠のない手動境界では、判断のたびにこの確定結果が保存され、別の完了操作は不要です。

表示される Page／System／Measure の識別子はレビュアーが読みやすいよう**1 始まり**です。永続化される補正対象は従来の内部**0 始まり**インデックスを維持し、GUI は保存スキーマを変換しません。

キャンバス操作:

- 拡大・縮小: マウスホイール。
- 移動: Space＋ドラッグまたは中ボタンドラッグ。
- 前／次のページ: 固定ヘッダーのボタンまたは左右矢印キー。
- Delete／Backspace: 該当する場合、現在選択中の未記録の補正を削除します。

利用者アプリはページ移動、楽譜表示の制御、タスク操作、補正状態を分けています。任意の証拠、注釈理由、来歴は **Details and evidence** にあります。破壊的な操作は削除可能な補正を選択したときだけ表示されます。

## 3. 補正を保存する

### 共通の補正状態

レビューアプリはページと補正種類ごとの状態、およびパッケージ全体の件数を示し、混在するレビュー状態を可視化します。管理されたラベルは **Edit not recorded**、**No correction recorded**、**Correction recorded**、**No corrected result yet**、**Corrected result is current**、**Recorded corrections changed since this result**、**Generating corrected result**、**Needs attention** です。ページや補正種類が同じ状態でない場合、パッケージサマリーは **Review has different correction states** を使います。

MMR 小節範囲、小節構築、小節線の編集はレビュアーが記録するまで未記録です。楽章判断は境界あり／なしを確定すると記録済みになり、別の記録操作はありません。最終確定した楽章境界入力も補正の識別情報の一部です。

記録と補正済み結果の生成は別です。アプリは handoff、宣言された元成果物、利用可能なら元 manifest、補正ファイルの内容識別子を比較します。補正済み結果が最新とみなされるのは、元データと記録済み補正の全体がその実行で消費した識別子と一致している間だけです。記録済み補正の編集や削除により、古い補正済み PDF が存在していても以前の結果は stale になります。

記録または適用の失敗はエラーとして報告され、以前の記録済み補正ファイルと最後に成功した補正結果の識別子は保持されます。状態メタデータは補正ペイロードとは別に `corrections/.correction_state.json` に保存され、エンジンのペイロードスキーマを変更しません。サーバーは `GET /api/state` でこの契約を公開します。利用者アプリは `POST /api/state/pending` で未記録の下書きをサーバーに報告し、`POST /api/state/pending/clear` で消去します。

既存 GUI はレビューパッケージの `corrections/` ディレクトリに補正を一時保存します。現在の補正対象は次のとおりです。

```text
review/corrections/
  mmr_measure_spans.json
  measure_construction_overrides.json
  barline_construction_overrides.json
```

これらは GUI の staging ファイルです。楽章境界の判断は一時保存してから保存する操作を使わず、判断ごとに即座に保存されます。GUI は次のパスも使用します（証拠ファイルは添付した場合のみ存在します）。

```text
review/
  movement_boundary_evidence.json
  corrections/
    movement_boundaries_review.json
    movement_boundaries.json
```

`movement_boundaries_review.json` は明示的な承認／却下／手動レビュー操作を保持します。候補レビューでは **Finish movement review** が `movement_boundaries.json` を `issue268.movement_boundaries.v1` として書き込み、確定した境界のみを含めます。境界なしと確認された位置はレビュー記録に残り、番号付けの入力にはなりません。この最終確定では番号付けの再実行やレビュー GUI に表示される楽譜の変更は行いません。証拠がない場合、各手動判断は保存されたレビューのハッシュとともに同じ確定出力を直接更新します。

パイプラインは次の正規ファイルを消費します。

```text
review/corrections/
  measure_overrides.json
  barline_overrides.json
```

適用ヘルパーは staging から正規形式への変換を行い、上書きを明示的に要求しない限り既存の正規ファイルの置き換えを拒否します。

## 4. 補正を適用し、再実行して補正済み最終 PDF を生成する

管理対象のパイプラインランタイムで既存の適用ヘルパーを使います。次のコマンドは GUI コマンドと同じ workspace を仮定します。すなわち `<review_root>` は `/workspace` にマウントされたリポジトリ内です。外部の絶対 review root の場合は、そのパッケージの bind mount を明示的に追加し、コンテナから見える handoff のパスを指定してください。handoff 内の保持済み元成果物パスにもコンテナ内からアクセスできる必要があります。

OMR-DLN が共有ホストキャッシュに登録されている場合、選択した検証済み成果物を manifest に宣言されたランタイムパスへマウントします。

```bash
OMR_HOST="$HOME/.cache/pdfscorebar/models/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt"
OMR_RUNTIME="/opt/pdfscore-external/omr-dln-measures/phase1-validated-v1/YOLOv8m_Measures.pt"

docker run --rm --gpus all \
  -v "$PWD":/workspace \
  -v "$OMR_HOST:$OMR_RUNTIME:ro" \
  -w /workspace \
  -e PYTHONPATH=/workspace \
  -e OMR_DLN_MODEL_PATH="$OMR_RUNTIME" \
  pdfscore_pipeline_gpu \
  /opt/venv_pipeline/bin/python -m src.pipeline.review.apply_corrections \
  <review_root>/manual_correction_input.json \
  --generate-final-pdf
```

最終出力名を明示する必要がある場合は `--output-name <name>` を使います。正規の補正ファイルが既に存在し、意図的に置き換える場合は `--overwrite` を追加します。

ヘルパーは次を行います。

1. handoff を検証します。
2. GUI の staging ファイルを正規形式に変換します。
3. 該当する場合、既存の補正入力を引き継ぎます。
4. レビューした元の実行から保持した成果物に再実行を固定します。
5. PDF 描画、HOMR、Real-ESRGAN、OMR-DLN、probe 生成、CNN scoring を再実行せず、レビュー済み小節線成果物に新しい小節線補正を適用します。
6. 変更された小節線に直接触れる小節以外では以前の自動 MMR 結果を再利用します。
7. 触れた小節に限って MMR を選択的に再実行し、明示的な手動 MMR 補正が既にある小節は除外します。
8. 必要な箇所のみ最終番号付けを再生成し、開始番号がまだ有効な変更のないレビュー済み最終ページはそのままコピーします。
9. `--generate-final-pdf` が指定された場合、補正済み最終番号付けから補正済み最終 PDF を描画します。

小節線を削除した場合、選択的 MMR の範囲はその小節線に接するレビュー済みの 2 小節と、結合後の補正済み小節です。小節線を追加した場合、分割されるレビュー済み小節と、新しい小節線の両側にできる 2 つの補正済み小節です。この局所的な構造変更の範囲外にある小節は以前の MMR 結果を維持します。

補正済み実行の config は来歴として `correction_rerun.mode=retained_artifacts_selective` を記録し、新規の `pdf_to_images`／`detection` ステップを無効にします。したがって補正の適用は、番号付けの再生成だけのために detector／SR／CNN の推論に依存してはなりません。

補正済み実行は次を出力します。

```text
<corrected_run_dir>/
  final/
    <output-name>_score_numbered.pdf
  review/
    correction_summary.json
    corrected_final_summary.json
```

最終 PDF は行頭番号を記したクリーンな成果物です。補正の来歴とレビュー／デバッグメタデータは `final/` の外に残ります。

## 元コマンドのメタデータ

`outputs.review.source_pipeline_command` は任意です。存在する場合、追跡用メタデータとして `manual_correction_input.json` にコピーされます。現在の config-first 入口はシェルコマンドを自動的に再構成しません。

## スコープ境界

このワークフローは既存のレビューパッケージ、GUI、補正ヘルパー、再実行経路、最終レンダラーをそのまま使用します。次は行いません。

- 第二の補正ワークフローや新しい公開 `pdfscorebar` CLI の追加。
- detector、HOMR、MMR、grouping、小節線、番号付けの精度に関する動作変更。
- 楽章境界の暗黙の推測や、未レビュー候補の番号リセットへの変換。楽章レビューは明示的かつパッケージ内であり、確定済み export は通常の補正再実行と別です。

## レビューアプリケーションで記録済み補正を適用する

`src.pipeline.review.apply_corrections` に必要な依存関係を備えた管理対象 Python ランタイムで、パッケージ単位のサーバーを実行します。

```bash
python3 tools/review_correction/server.py --handoff /path/to/run/review/manual_correction_input.json
```

先に編集を記録してください。楽章判断は即座に保存されますが、detector の証拠が添付されている場合は適用前に楽章レビューを完了してください。**Generate corrected PDF** を選ぶと、正規の保持済み成果物エンジンを呼び出し、最終 PDF を明示的に生成します。ブラウザーは実行中にアプリケーション状態をポーリングします。PDF リンクは補正済みエンジン実行と最終 PDF の両方が成功した後にのみ表示されます。記録済み補正を変更または削除すると以前の結果は stale になりますが、そのリンクは以前の結果として識別され、引き続き利用できます。試行に失敗しても最後に成功した結果は保持されます。

サーバーは空の JSON オブジェクトを伴う `POST /api/apply` を受け付けます。ブラウザーからパス、設定、実行名、上書きオプションを指定することはできません。パッケージごとに許可される適用操作は一つで、実行中は補正の書き込みと重複する適用要求が拒否されます。各試行には `review/application_runs/attempt_NNNN/` 以下に単調増加する名前が付けられ、既存の試行は決して置き換えられません。それぞれに宣言されたレビュー／補正入力のコピー、消費した識別子の来歴、補正済みエンジン実行が含まれます。生成された正規補正ファイルはコピー内に残るため、アプリケーションの再試行で記録済み補正が上書きされることはありません。最終成果物は `corrected/final/*.pdf` で、レビュー／適用の証拠はそのディレクトリの外に残ります。`GET /api/result` は保存された内容識別子を確認した後、最後に成功した PDF のみを提供します。

エンジンは最終確定済み楽章データを保存済みレビュー判断と添付証拠があればその証拠に照らして検証します。古い最終確定や、保存済みだが最終確定されていない判断がある場合、最新の楽章レビューを黙って無視せず、対処可能なエラーになります。レビュー済み楽章データがない場合は元実行の楽章入力の従来の意味を維持し、未解決の候補はリセットになりません。

### レビュアー向け文言

専用の利用者 UI は `tools/review_correction/index.html` と `app.js` です。主要な操作、検証、結果のメッセージは `tools/review_correction/strings.js` に集められ、状態ラベルは `tools/review_correction/state.py::LABELS` から取得します。利用者アプリケーションは言語選択で英語と日本語をサポートします。GT／開発者向けの表示は `tools/gt_relabel_gui/` にあり、このローカライズ範囲外です。ブラウザーはパッケージ全体の未記録／記録済み／エラー件数とともに現在のページの詳細のみを表示します。

## ローカライズ

利用者アプリケーションは英語と日本語をサポートし、言語選択はブラウザーにローカル保存されます。GT／開発者向けファイルはローカライズの対象外です。

## 過去の受け入れ証拠

実成果物の受け入れ手順と固定された観測可能な結果のゲートは [利用者補正の受入検証](REVIEW_ACCEPTANCE.ja.md) に記載されています。過去の証拠はクリーンな補正済み `final/` ディレクトリとは別に `logs/issue397/acceptance/` に保持されています。これは現在のリビジョンが実成果物で再検証されたことを主張するものではありません。
