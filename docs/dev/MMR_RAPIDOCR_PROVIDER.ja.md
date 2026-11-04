# MMR RapidOCR のプロバイダモード

<!-- translation: {"original":"MMR_RAPIDOCR_PROVIDER.md","source":{"sha256":"e2beffe5d804edc10f51d624e3ed91cb9602784a19f2750bc4cc11a70394e30d"},"state":"reviewed"} -->

[English / 原文](MMR_RAPIDOCR_PROVIDER.md)（英語正本）

翻訳元: same PR / SHA-256 `e2beffe5d804edc10f51d624e3ed91cb9602784a19f2750bc4cc11a70394e30d`。状態: `reviewed`。原文との意味・制約・例外と日本語の可読性を確認済み。

MMR OCR は、MMR の番号付けの経路でだけ RapidOCR を使います。

既定のプロバイダモードは `auto` です。

- ONNX Runtime が `CUDAExecutionProvider` を提供している場合、MMR RapidOCR は `det_use_cuda=True`、`cls_use_cuda=True`、`rec_use_cuda=True` で作成されます。
- それ以外の場合、MMR RapidOCR は既定の `RapidOCR()` コンストラクタにフォールバックします。

このヘルパーは、ローカルでの確認用に明示的なモードもサポートします。

- `auto`: 既定の、CUDAが使えれば使う挙動。
- `cpu`: 既定の `RapidOCR()` コンストラクタを強制します。
- `cuda`: CUDA用の引数を要求し、作成後に `CUDAExecutionProvider` が確認できない場合は警告します。

未知のモード値は拒否されます。ヘルパーは `src/measure_numbering/rapidocr_provider.py` です。

## モードを選ぶ場所

- 通常のパイプラインのMMRバッチ（`src/pipeline/steps/numbering_phases.py`）は、`mmr.rapidocr_provider` を読みます。既定値は `auto` です。
- 補正の適用時に使う選択的なMMRの再実行（`src/pipeline/review/apply_corrections.py`）は、元の実行のconfigから `mmr.rapidocr_provider` を読みます。既定値は `auto` です。

これは MMR OCR の作成だけに限定されます。HOMR のタイトル検出、SR、CNN のスコアリング、小節線の検出は変わりません。そのため、関連する検証の範囲は、検出器の契約全体の実行ではなく、ローカルでのMMRの作成と番号付けステップのテストです。
