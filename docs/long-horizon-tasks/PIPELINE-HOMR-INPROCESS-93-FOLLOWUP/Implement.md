# Execution Rules (Implementation Directives)

- Follow `Plan.md` milestones strictly.
- **omr-dln Module implementation**: When creating `src/pipeline/detection/omr_dln.py`, ensure the YOLO model is cached globally within the module so that it is only loaded once per batch processing run. Use `ultralytics.YOLO`.
- **In-Memory Image Passing**: When modifying `src/pdf_to_images.py` and downstream consumers, ensure that images can be passed as a list or dictionary of `np.ndarray` objects. 
    - File I/O should be bypassed unless a debug output path is strictly specified by the config.
    - Check how `src/pipeline/orchestrator.py` constructs `image_paths` and adjust it to handle/store arrays instead if `pdf_to_images` outputting arrays is active.
- **Regression Checks**: If you encounter errors executing `make run-pipeline`, run the underlying python commands directly but **you MUST redirect the output to an artifact file** (e.g. `> artifacts/eval.log 2>&1`) and use tools like `tail` or `grep` to inspect it, preventing context window bloat.
- **Evaluation script logic**: Do not write new evaluation scripts. The evaluation logic must be performed using `tools/evaluate_and_visualize.py`. If path-matching fails due to refactoring the output structures, adjust the internal logic of `evaluate_and_visualize.py` instead of making a new script.
- **Execution Time & Timeout Prevention**: The full evaluation takes several hours. ALWAYS run full evaluations in the background or handle tool timeouts proactively.
- **Milestone Validation**: Only test M1 and M2 using a small subset (e.g., using `--page-limit 3` or a small config). Reserve the full 68-page evaluation exclusively for the Final Verification stage.
- デグレが発生したら、過去のコミットや資料を確認し、`設定が完全に同じかどうか`, `処理が完全に同じかどうか`などを確認してから対処を考える。やみくもな調整を開始しないこと。
