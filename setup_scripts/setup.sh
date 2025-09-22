#!/bin/bash
set -euo pipefail

# === User paths (adjust here if needed) ===
PROJECT_DIR="/home/masaki_muramatsu/ws_PDFScoreBar"
SERENA_LOG="$HOME/.serena/mcp.log"
SERENA_PID="$HOME/.serena/mcp.pid"

CODEX_WS="/home/masaki_muramatsu/codex_settings/mcp_codex_bridge_ws"
CODEX_BRIDGE="$CODEX_WS/mcp/codex-bridge/server.js"
GEMINI_CFG_DIR="$HOME/.gemini"               # or: $HOME/.config/gemini
GEMINI_CFG="$GEMINI_CFG_DIR/settings.json"

echo "[1/5] Optional: index project with Serena"
uvx --from git+https://github.com/oraios/serena \
  serena project index "$PROJECT_DIR" || true

echo "[2/5] Start Serena MCP server (SSE, port 9121)"
mkdir -p "$(dirname "$SERENA_LOG")"
nohup uvx --from git+https://github.com/oraios/serena \
  serena start-mcp-server \
  --transport sse --port 9121 \
  --context ide-assistant \
  --project "$PROJECT_DIR" \
  >"$SERENA_LOG" 2>&1 &
echo $! > "$SERENA_PID"
echo "  Serena PID: $(cat "$SERENA_PID")  log: $SERENA_LOG"

echo "[3/5] Prepare Codex MCP bridge (stdio)"
#   - 常駐は不要（Gemini が必要時に起動）なので、存在＆依存チェックのみ。
if [ ! -f "$CODEX_BRIDGE" ]; then
  echo "ERROR: Codex bridge not found at $CODEX_BRIDGE"
  echo "       (did you place mcp_codex_bridge_ws there?)"
  exit 1
fi
# 依存 & 実行権
( cd "$CODEX_WS/mcp/codex-bridge" && npm install && chmod +x server.js )

echo "[4/5] Configure Gemini to use @codex (stdio MCP)"
mkdir -p "$GEMINI_CFG_DIR"
if [ ! -f "$GEMINI_CFG" ]; then
  cat > "$GEMINI_CFG" <<JSON
{
  "model": "gemini-2.5-pro",
  "mcpServers": {
    "codex": {
      "transport": "stdio",
      "command": "$CODEX_BRIDGE",
      "args": []
    }
  }
}
JSON
  echo "  Created $GEMINI_CFG"
else
  # 既存 settings.json に codex エントリをマージ（その他設定は保持）
  tmp="$(mktemp)"
  jq --arg cmd "$CODEX_BRIDGE" '
    .model = (.model // "gemini-2.5-pro") |
    .mcpServers = (.mcpServers // {}) |
    .mcpServers.codex = {
      "transport": "stdio",
      "command": $cmd,
      "args": []
    }
  ' "$GEMINI_CFG" > "$tmp" && mv "$tmp" "$GEMINI_CFG"
  echo "  Updated $GEMINI_CFG (added/updated mcpServers.codex)"
fi

echo "[5/5] Quick checks"
node -v
python3 --version || true
pytest --version || true

cat <<'TIP'

✅ Setup complete.

How to use in Gemini session:
  1) 設計・要約を貼る（docs/session_summary.md 推奨）
  2) 実行が必要になったら：
     @codex.run_cmd   { "cmd":"python", "args":["--version"] }
     @codex.run_tests { "cmd":"pytest", "args":["-q"], "cwd":"'"$PROJECT_DIR"'" }
     @codex.apply_patch { "path":"src/foo.py", "patch":"# 新実装 ..." }

Notes:
  - Serena (SSE 9121) は常駐。Codex ブリッジ（stdio）は Gemini が必要に応じて起動。
  - Gemini Pro の日次上限に達したら settings.json の "model" を "gemini-2.5-flash" に変更。
  - さらに重い実装は Codex 単独モードでもOK（後日 CLI を導入したら切替）。
TIP
