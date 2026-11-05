#!/usr/bin/env bash
# Start A2A server for OpenCode agents
# Usage: bash .ai/a2a/start.sh [port]
set -euo pipefail
PORT="${1:-4096}"
REPO="C:/Users/Admin/UGAFStudio"
cd "$REPO"
echo "Starting A2A server on port $PORT..."
echo "Discover: http://127.0.0.1:$PORT/a2a_discover"
echo "Health:  http://127.0.0.1:$PORT/a2a_health"
exec python .ai/a2a/a2a_server.py "$PORT"
