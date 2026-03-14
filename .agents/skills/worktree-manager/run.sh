#!/bin/bash
# .agents/skills/worktree-manager/run.sh
# Git Worktree と Docker コンテナの統合管理スクリプト

set -euo pipefail

COMMAND=${1:-""}
BASE_DIR="../worktrees"
IMAGE_NAME="sr_eval_gpu_image" # 将来的に Issue #5/#7 で標準化されるイメージ名

show_help() {
    echo "Usage: $0 {add|remove|list} [args...]"
    echo "  add <branch_name> [container_suffix]: 新しい worktree を作成し、独立コンテナを起動します。"
    echo "  remove <branch_name>: worktree を削除し、対応するコンテナも停止・削除します。"
    echo "  list: 現在の worktree 一覧を表示します。"
}

if [[ -z "$COMMAND" ]]; then
    show_help
    exit 1
fi

# フォルダ名やコンテナ名に使用できる形式に変換
get_clean_name() {
    echo "$1" | sed 's/[^a-zA-Z0-9]/-/g'
}

case "$COMMAND" in
    add)
        BRANCH=$2
        SUFFIX=${3:-$(get_clean_name "$BRANCH")}
        WT_PATH="$BASE_DIR/$SUFFIX"
        CONTAINER_NAME="sr_eval_gpu_$SUFFIX"

        echo "Adding worktree for branch '$BRANCH' at '$WT_PATH'..."
        mkdir -p "$BASE_DIR"
        git worktree add "$WT_PATH" "$BRANCH"

        echo "Starting isolated container '$CONTAINER_NAME'..."
        # 注意: Issue #5/#7 で Makefile 側のコンテナ起動ロジックが整備されたら
        # ここからその Makefile ターゲットを呼び出す形に統合するのが望ましい
        docker run -d --gpus all \
            --name "$CONTAINER_NAME" \
            -v "$(realpath $WT_PATH):/workspace" \
            -v "$(realpath data):/workspace/data:ro" \
            -v "$(realpath datasets):/workspace/datasets:ro" \
            "$IMAGE_NAME" tail -f /dev/null

        echo "Setup complete."
        echo "Worktree Path: $WT_PATH"
        echo "Container Name: $CONTAINER_NAME"
        ;;

    remove)
        BRANCH_OR_SUFFIX=$2
        SUFFIX=$(get_clean_name "$BRANCH_OR_SUFFIX")
        WT_PATH="$BASE_DIR/$SUFFIX"
        CONTAINER_NAME="sr_eval_gpu_$SUFFIX"

        echo "Cleaning up container '$CONTAINER_NAME'..."
        if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            docker stop "$CONTAINER_NAME" || true
            docker rm "$CONTAINER_NAME" || true
            echo "Container removed."
        else
            echo "Container '$CONTAINER_NAME' not found, skipping."
        fi

        echo "Removing worktree at '$WT_PATH'..."
        if [ -d "$WT_PATH" ]; then
            git worktree remove "$WT_PATH"
            echo "Worktree removed."
        else
            echo "Worktree path not found, skipping."
        fi
        ;;

    list)
        git worktree list
        echo "--- Active Containers ---"
        docker ps --filter "name=sr_eval_gpu_" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
        ;;

    *)
        show_help
        exit 1
        ;;
esac
