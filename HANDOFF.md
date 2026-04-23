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
> 本セッションでは、Epic #120 に関連する後続のスモールステップPRの作成を行います。
> まず最初に `HANDOFF.md` を読み、全体のロードマップとコンフリクト発生の背景（Phase 2 と Phase 3 の適用順序の逆転）、および**正しい推論検証の手順（キャッシュ破棄）**を完全に理解してください。
> 
> **タスク1: Step 5 (Phase 2 リファクタリング) の PR作成**
> 1. `rebuild/issue120` を pull して最新化し、新たにブランチ(`rebuild/step5-phase2-refactor`)を作成してください。
> 2. 退避ブランチ (`rebuild/baseline-90a278c-fixed`) から、残りの純粋なリファクタリング（`694e1a2`, `f6cdb78`, `489bb93`, `06c0684`, `2a7441e`）のコミットを Cherry-pick してください。
> 3. **重要: コンフリクトが発生する場合があります。** コンフリクト発生時はパニックにならず、前後の文脈を読んで手動で安全に解消してください。
> 4. コンフリクト解消後、必ず「3. ネイティブ推論の実行と精度判定の正しい手順」に記載された手順に従って `evaluate_full_rescue_v1.py` による実際の推論を実行し、出力されたサマリから直接 **精度が `TP=3580, FP=0, FN=1` に完全に維持されていること**を絶対の Gate 条件として確認してください。（`verify_golden_baseline.py` のデフォルト引数での実行はキャッシュの検証になるため厳禁です）
> 5. 精度維持が確認できたらPRを提出してください。その際にPRのマージ時に自動でIssue #122をcloseできるようにしてください。
> 6. PRのレビューコメントがついたら追加で修正作業をしてください。(マージはユーザー側で実施します。勝手に行ってはいけません。)