#!/bin/bash
set -euo pipefail

# === User paths (adjust here if needed) ===
PROJECT_DIR="/home/masaki_muramatsu/ws_PDFScoreBar"
SERENA_LOG="$HOME/.serena/mcp.log"
SERENA_PID="$HOME/.serena/mcp.pid"

echo "[1/3] Optional: index project with Serena"
uvx --from git+https://github.com/oraios/serena \
  serena project index "$PROJECT_DIR" || true

echo "[2/3] Start Serena MCP server (SSE, port 9121)"
mkdir -p "$(dirname "$SERENA_LOG")"
nohup uvx --from git+https://github.com/oraios/serena \
  serena start-mcp-server \
  --transport sse --port 9121 \
  --context ide-assistant \
  --project "$PROJECT_DIR" \
  >"$SERENA_LOG" 2>&1 &
echo $! > "$SERENA_PID"
echo "  Serena PID: $(cat "$SERENA_PID")  log: $SERENA_LOG"

echo "[3/3] Quick checks"
node -v
python3 --version || true
pytest --version || true

cat <<'TIP'

✅ Setup complete.

Notes:
  - Serena MCP サーバー (SSE 9121) は常駐運用を想定。
  - 再起動時は `pkill -F "$SERENA_PID"` などで既存プロセスを停止してから本スクリプトを実行してください。
TIP
