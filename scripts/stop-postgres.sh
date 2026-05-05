#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PG_CTL="$PROJECT_ROOT/runtime/linux/postgresql/bin/pg_ctl"
PG_DATA="$PROJECT_ROOT/runtime/data/pgdata"

if [[ ! -x "$PG_CTL" ]]; then
  echo "未找到 pg_ctl：$PG_CTL" >&2
  exit 1
fi

if [[ ! -f "$PG_DATA/PG_VERSION" ]]; then
  echo "PostgreSQL 数据目录尚未初始化。"
  exit 0
fi

if "$PG_CTL" status -D "$PG_DATA" >/dev/null 2>&1; then
  "$PG_CTL" stop -D "$PG_DATA" -m fast
else
  echo "PostgreSQL 未运行。"
fi
