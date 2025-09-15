#bin/bash

# This script sets up the environment for the project
# 1) （任意）初回だけプロジェクトを索引化
uvx --from git+https://github.com/oraios/serena \
  serena project index /home/masaki_muramatsu/ws_PDFScoreBar

# 2) SSE サーバ起動（ポート 9121）
nohup uvx --from git+https://github.com/oraios/serena \
  serena start-mcp-server \
  --transport sse --port 9121 \
  --context ide-assistant \
  --project /home/masaki_muramatsu/ws_PDFScoreBar \
  >~/.serena/mcp.log 2>&1 &
echo $! > ~/.serena/mcp.pid