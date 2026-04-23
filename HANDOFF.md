# Session Handoff (Epic #120 Rebuild Roadmap)

## 1. 統合ブランチとマージの全体方針 (Roadmap)
Epic #120（90a278cを起点とした高精度パイプラインの再構築）は、すべてのスモールステップPRを段階的に **`rebuild/issue120`** ブランチ（統合ブランチ）に集約していく方針で進めています。

全体のロードマップは以下の通りです。
*   **Step 1 (完了 / PR #127)**: 前提となるCNNスケーリングバグ(`max_h`)の修正と、今後の精度維持のGateとなるGolden Baselineデータ・検証スクリプトの追加。
*   **Step 2 (完了 / PR #128)**: Phase 1 後半（In-process化、Batch Orchestrator、Docker/Env統合）。
*   **Step 3 (完了 / PR #129)**: Phase 3（ネイティブフィルタリングの実装とBox Tightening）。
*   **Step 4 (完了 / PR #131)**: Phase 2 前半（丸め誤差、Tall Band対策などのサイレントバグ・ロジック修正）。
*   **Step 5 (未着手)**: Phase 2 後半（PDFページ指定やimport整理などの純粋なリファクタリング・機能改善）。
*   **Final**: すべてのステップが `rebuild/issue120` に統合され、精度 `TP=3580, FP=0, FN=1` が完全に維持されていることを確認した上で、最終的に `develop` または `main` へ一括マージして Epic #120 を完了とします。

## 2. なぜ Phase 3 (フィルタリング) を Phase 2 (ロジック修正) より先に移植したのか？
当初の Issue Map では Phase 2 (バグ修正) → Phase 3 (100% Recallフィルタリング) の順序が想定されていましたが、コードの依存関係上の理由から順番を意図的に逆転させました。

*   **理由**: Phase 2 の「Tall Band対策（長い五線を分割して希釈を防ぐロジック）」のコミット群は、Phase 3 で新たに作成される `candidate_filters.py` 内の関数 **`split_box_vertically`** に直接依存しています。
*   そのため、もし先に Phase 2 を移植しようとすると `ModuleNotFoundError` 等でパイプラインが壊れ、スモールステップごとのGolden Baseline検証（FP=0, FN=1 の維持）が不可能になってしまうためです。

## 3. ネイティブ推論の実行と精度判定の正しい手順 (Gate条件の確認方法)
各コミットやPR段階での精度検証において、単に `PYTHONPATH=. .venv_pdf/bin/python tools/repro_accuracy/verify_golden_baseline.py` をデフォルト引数で実行すると、あらかじめキャッシュされたGolden Baselineの静的JSONデータを読み込むだけで、**作業中の最新コードによる推論結果が一切評価されません**（コードが壊れていても常に成功と誤判定してしまいます）。
必ず以下の手順で**実際の推論（ネイティブ実行）を走らせ、その結果を評価プログラムに送って判定**してください。

### 【正しい検証手順】
1. **推論キャッシュを無視して最新コードでネイティブ推論を実行する**
   既存の推論キャッシュを破棄し、現在のコードで新たに推論結果を生成させます。
   ```bash
   sed -i 's/skip_existing=True/skip_existing=False/g' experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py
   rm -rf logs/issue53_full_eval_rescue_v1
   PYTHONPATH=. .venv_pdf/bin/python experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py > artifacts/step_eval.log 2>&1
   ```

2. **出力された推論結果の評価を確認**
   上記のスクリプトは最後に自動で `re_evaluate_global.py` を呼び出し、ターミナルに評価サマリを出力します。その出力結果の最下部にある `GLOBAL TOTAL` の行が、以下の値と完全に一致していることを確認してください。
   ```bash
   PYTHONPATH=. .venv_pdf/bin/python tools/re_evaluate_global.py --config logs/issue53_full_eval_rescue_v1/eval_config.yaml
   ```
   出力が `GLOBAL TOTAL                        | -     | 3580  | 0     | 1     | 1     | 0     | 100.0% | 100.0%` となることを確認。

3. **スクリプトの一時変更を戻す**
   ```bash
   git restore experiments/issue53_probe_rescue/evaluate_full_rescue_v1.py
   ```

### 【本テスト（`evaluate_full_rescue_v1.py`）で検証されるスコープ】
このネイティブ実行テストは「精度の検証」に特化しているため、パイプラインのすべてのステップを実行するわけではありません。

*   **テストされる範囲 (In Scope)**:
    *   **Probe Scan**: 既存のシード(Bands)と画像からの候補枠の新規生成
    *   **Candidate Filtering**: 五線譜・音部記号マスクやヒューリスティクスに基づく候補の事前フィルタリング
    *   **CNN Scoring**: CNNモデルを用いた候補枠のスコアリング
    *   **Box Tightening**: インク情報に基づくトリミング（`trim_box_to_ink`）や NMS（非最大値抑制）
    *   **Evaluation**: 最終候補と正解データ（GT）の Greedy Matching による Recall/Precision 算出
*   **テストされない範囲 (Out of Scope)**:
    ※以下は計算コスト削減のため、事前に生成されたデータ（キャッシュ）を読み込むか、実行をスキップします。
    *   PDFから画像への変換 (`pdf_to_images`)
    *   OMR推論 (`HOMR` などの初期検出)
    *   超解像処理 (`Real-ESRGAN`)
    *   OMR-DLN推論
    *   Hybrid Consensus（各検出結果の統合）
    *   小節番号認識 (`MMR`) と最終的な番号付与

## 4. Next Steps for the Next Session
次回のセッションを担当するAIアシスタントは、必ず以下のプロンプト指示に従って作業を進めてください。

### 【次セッションへの指示プロンプト】
> 本セッションでは、Epic #120 のすべてのスモールステップ（Step 1 〜 Step 5）が `rebuild/issue120` に統合されたことを受け、最終的なパイプライン全体の E2E (End-to-End) 検証と、メインブランチへのリリース準備を行います。
> 
> **タスク1: E2E パイプラインの完全実行と精度検証**
> これまでは計算コスト削減のため、`evaluate_full_rescue_v1.py` を用いた部分的な推論テストを行っていましたが、Step 5 (Phase 2 後半) のインメモリ画像対応などがパイプラインの前半・後半処理（PDF変換、HOMR、Real-ESRGAN、Hybrid Consensus、MMRによる小節番号付与など）に悪影響を与えていないかを証明する必要があります。
> 
> 1. `rebuild/issue120` ブランチの最新状態であることを確認してください。
> 2. `data/evaluation2/` などの入力データは残しつつ、E2Eテスト用のキャッシュを破棄または分離した状態で、パイプラインのメインエントリーポイント (`python src/pipeline/main.py --config <E2E用の適切な設定ファイル>`) を実行してください。（フルパイプラインの実行となるため、設定ファイルやコマンドはプロジェクトの現状に合わせて適切に選択・調整してください）
> 3. E2E実行がエラーなく完走することを確認してください。インメモリ画像処理が各ステップに正しく伝播しているかが最大の焦点です。
> 4. E2E実行後、最終出力に対して `tools/re_evaluate_global.py` 等を用いて評価を行い、**精度が `TP=3580, FP=0, FN=1` に保たれていること** を絶対のGate条件として確認してください。
> 
> **タスク2: 結果に基づくコンティンジェンシープラン**
> - **【シナリオA: 精度維持 (成功)】**: E2E検証が成功した場合、Epic #120 全体の成果を総括したリリースPRを `develop` または `main` ブランチ宛に作成してください。
> - **【シナリオB: 精度劣化・クラッシュ (失敗)】**: もし精度が劣化した場合、またはエラーでパイプラインが停止した場合は、PRの作成は行わず、「Epic #120 E2E統合後の精度劣化・エラー調査」という新しい調査Issue（またはそれに準ずる検証計画）を起票・記録し、次ステップでの調査に繋げてください。決して不完全な状態でマージを進めてはいけません。