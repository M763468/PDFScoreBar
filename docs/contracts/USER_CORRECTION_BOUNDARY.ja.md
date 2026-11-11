# 利用者の補正と GT ツールの境界

<!-- translation: {"original":"USER_CORRECTION_BOUNDARY.md","source":{"sha256":"730913dc692dfab490a65e62b583f88322ca021bb55c2b3dbe5896c858a2ae18"},"state":"reviewed"} -->

[English / 原文](USER_CORRECTION_BOUNDARY.md)（英語正本）

翻訳元: same PR / SHA-256 `730913dc692dfab490a65e62b583f88322ca021bb55c2b3dbe5896c858a2ae18`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

この開発者向けリファレンスは、利用者向け補正ツールと GT ツールの責務と永続化の境界を説明します。通常の利用者操作は[ユーザーガイド](../USER_GUIDE.ja.md)を参照してください。

サポート対象の利用者向け補正アプリケーションは `tools/review_correction/server.py` です。検証済みの `review/manual_correction_input.json` パッケージを一つ開きます。handoff はページ、読み取り可能な成果物、補正の出力先を指定します。サーバーは手動レビュー UI とその UI に必要なルートだけを公開します。`127.0.0.1` で待ち受け、そのローカルアドレスを HTTP host として受け入れ、書き込みには同一 origin の JSON リクエストを要求します。ファイルの要求と書き込みのたびに、シンボリックリンクを含む解決後のパスを再検査します。記録された補正はそのパッケージの `review/corrections/` に残ります。適用の試行とコピーされた入力は `review/application_runs/` に分離され、補正済み最終 PDF は各試行の `corrected/final/` に置かれます。

通常 PDF と書き込み入り PDF では、楽章リセット後も含めて行頭番号 1 を表示しません。アウフタクトの 0 と後続の行頭番号は表示対象です。最終サマリーと番号レイヤーの sidecar は、意図的に非表示にした段 ID を描画済みラベルと分けて記録します。
通常 PDF は五線を基準とする 9pt の位置の近傍を優先し、空きがなければ左余白と五線左端の上方を探します。上下の探索は基本位置から上に 45pt、下に 12pt までで、ページ境界と印刷インクからの間隔を守ります。表示対象の番号に安全な位置がなければ配置エラーを報告し、新しい番号付き PDF と sidecar は公開しません。

`tools/gt_relabel_gui/server.py` は別の開発者向け入口です。`gt`、`rest`、`relabel` モードは正規 GT／評価データや relabel テンプレートを編集する場合があります。旧 `manual` モードと任意の config／root オプションは開発者専用の互換機能であり、利用者の補正セッションを開くサポート対象の方法ではありません。GT エディターの動作はここでは変更されません。

| 対象 | 責務 |
| --- | --- |
| `tools/review_correction/application.py` | パッケージに結び付いたエンジン呼び出し、変更されない記録済み入力のコピー、衝突・同時実行の防止、検証済み最終 PDF の検出 |
| `tools/review_correction/state.py` | ページ／種類ごとの状態、記録済み補正と成功した補正結果の内容識別子 |
| `tools/review_correction/server.py` | 利用者アプリケーションの入口、HTTP ルートの許可リスト、パッケージ内の永続化境界 |
| `tools/review_correction/index.html`, `app.js`, `strings.js` | 専用の利用者向けレビュー画面と管理された文言 |
| `src/pipeline/review/manual_correction_handoff.py` | 共通の handoff 検証と GUI ページ設定 |
| `src/pipeline/review/movement_boundary_review.py` | 共通のレビュー証拠と確定済み出力のヘルパー |
| `tools/gt_relabel_gui/server.py` | GT／評価の編集、relabel、開発者向け probe、旧 manual 互換の入口 |
| `tools/gt_relabel_gui/index_gt.html`, `app_gt.js`, `index_rest.html`, `app_rest.js`, `index.html`, `app.js` | GT／rest／relabel の開発者向け UI アセット |
| `tools/gt_relabel_gui/*config*.json`, `build_*config.py`, `prepare_rebuild_eval2.py` | GT／評価の設定データと開発者向け config ビルダー |

両アプリケーションは低レベルの handoff／描画の考え方を共有しますが、入口、ルート群、保存先は別です。利用者向けサーバーは GT ハンドラーを呼び出しません。この境界は補正ペイロードや detector、MMR、grouping、正規 GT データを変更しません。

### 記録の責務

`ReviewPackage.record_correction` は、すべての補正種類に共通するパッケージに結び付いた記録操作を担当します。指定された保存先と項目の形を検証し、共有ファイル内の他ページを保持し、補正ファイルをアトミックに置き換えた後、そのページ／種類の未記録編集と記録エラーを消去します。書き込みに失敗した場合、以前の記録内容と未記録編集は保持されます。

MMR／小節／小節線の明示的な保存と楽章の確定は UI の起点だけが異なります。どちらも `/api/save` と同じ記録操作を呼びます。楽章の最終確定は別のエンジン由来入力の生成ステップであり、第二の補正永続化モデルを導入しません。

状態サマリーの件数は独立した軸です。ページ／種類は記録済みかつ未記録編集ありにもなります。`recorded_identity` は記録されたページ項目のハッシュであり、そのページ／種類に記録済み補正がなければ、他ページ用の共有ファイルが存在しても `null` です。エラー件数は、適用失敗と記録エラーが重なった場合を含め、各ページ／種類を一度だけ数えます。

利用者向け状態アダプターは保存完了時に、保存開始時のページ／種類の下書きと比較します。保存中に行った編集は未記録のまま残り、自動保存後に新しい未保存編集が残っていればページ移動を停止します。楽章の最終確定では、ボタンの状態から完了を推測せず、失敗を含め実際のリクエスト終了後に状態を更新します。これらのアダプターは利用者向けのみであり、GT／開発者向けハンドラーや補正ペイロードを変更しません。

正規の適用エンジンは、明示的に空の境界集合を含め、最終確定したレビュー済み楽章ペイロードを正確に `corrected_pipeline_config.json` に記録します。この消費された入力の来歴は適用統合の責務です。実成果物の受け入れでは、第二の楽章入力解釈を導入せずに消費された入力を検証します。
