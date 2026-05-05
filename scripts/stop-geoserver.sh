#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHUTDOWN="$PROJECT_ROOT/runtime/linux/geoserver/bin/shutdown.sh"

if [[ -x "$SHUTDOWN" ]]; then
  "$SHUTDOWN"
else
  echo "未找到 GeoServer shutdown.sh。若使用 start.jar 方式启动，请手动结束对应 java 进程。"
fi
