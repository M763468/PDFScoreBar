# doc-consistency-manager

## Purpose
Ensure that the repository's documentation and asset inventories accurately reflect the state of the codebase. This skill wraps the `make check-consistency` command and provides actionable instructions on how to resolve common discrepancies (Orphans, Broken Links, Stale Docs).

## Context
As the repository evolves, files are moved, tools are deprecated, and reports become outdated. The consistency check script (`tools/check_repo_consistency.py`) verifies that:
1. All core assets defined in `docs/MANIFEST.md` exist.
2. All documents in `docs/` are classified in `docs/DOCUMENT_INVENTORY.md` and are fresh (updated within 30 days).
3. Tools and experiments have corresponding registry entries in `docs/inventory/`.

## Input
- None (The skill runs standard repository checks).

## Output (Respond in Japanese)
- Summary of the consistency check (`[PASSED]` or `[FAILED]`).
- Action plan for any critical errors (`[BROKEN]`, `[CRITICAL]`).
- Recommendations for warnings (`[UNTRACKED]`, `[STALE!!]`).

## Steps
1) Run `./run.sh` to execute the consistency check.
2) Analyze the output located in `artifacts/consistency_check.log` (or standard output).
3) Interpret the results based on these rules:
    - **`[BROKEN]` (Exit Code 2 / CI Failure)**: A file is listed in an inventory but missing from disk.
        - *Action*: Use the `replace` tool to remove the entry from the relevant markdown inventory (e.g., `DOCUMENT_INVENTORY.md`). *Note: Empty directories tracked in inventories MUST contain a `.gitkeep`.*
    - **`[CRITICAL]` (CI Failure)**: A core asset in `MANIFEST.md` is missing.
        - *Action*: Determine if the deletion was intentional. If yes, remove it from `MANIFEST.md`. If no, restore the file.
    - **`[UNTRACKED] / [MISSING]` (Info)**: A file exists in a core directory (`src/`, `tools/`, `configs/`) but isn't documented.
        - *Action*: If the file is a permanent, important addition, document it in `docs/MANIFEST.md` or the appropriate `docs/inventory/` file. If it's temporary or experimental, it can be safely ignored.
    - **`[STALE!!]` (Warning)**: A `Current` document is over 30 days old.
        - *Action*: Read the document. If the information is still accurate and applicable to the current mainline (e.g., `main.py`, `sr_eval_gpu`), update the document's timestamp by adding a note at the top (e.g., `> [!NOTE] Status (YYYY-MM): This remains active and valid.`) using the `replace` tool. If the content is obsolete, consider moving it to `[Legacy]` / `docs/archive/`.
4) Propose fixes for `[BROKEN]` and `[CRITICAL]` issues first, as they break CI.
5) Run `make check-consistency` again to verify your fixes.
6) Commit the fixes.

## Required commands/permissions
- `make check-consistency`
- File editing tools (`replace`, `write_file`)

## Example output
```markdown
### 整合性チェック結果
ログを確認したところ、`docs/long-horizon-tasks/` が `[BROKEN]` と判定されています（ディレクトリが空のためGitに認識されていない状態）。

### 解決策
- 空のディレクトリを追跡するため `docs/long-horizon-tasks/.gitkeep` を作成します。
- `docs/ENVIRONMENTS.md` が `[STALE!!]` となっています。内容を確認し、現状有効であればタイムスタンプ更新（Status note追記）を行います。
```
