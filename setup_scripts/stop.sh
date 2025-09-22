#!/usr/bin/env bash
set -euo pipefail
SERENA_PID="$HOME/.serena/mcp.pid"
if [ -f "$SERENA_PID" ]; then
  kill "$(cat "$SERENA_PID")" || true
  rm -f "$SERENA_PID"
  echo "Serena stopped."
else
  echo "Serena not running."
fi
