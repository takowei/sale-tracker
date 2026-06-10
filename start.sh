#!/usr/bin/env bash
# 啟動 sale-tracker 本地 HTTP server
set -euo pipefail
PORT=${PORT:-8080}
DIR="$(cd "$(dirname "$0")" && pwd)"
printf '特價追蹤器：http://localhost:%s\n' "$PORT"
python3 -m http.server "$PORT" --directory "$DIR"
