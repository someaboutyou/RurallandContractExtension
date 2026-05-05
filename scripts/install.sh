#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
STATE_DIR="$RUNTIME_ROOT/.state"
INSTALL_MARKER="$STATE_DIR/installed.json"
FORCE=0

if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

require_executable() {
  if [[ ! -x "$1" ]]; then
    echo "$2" >&2
    exit 1
  fi
}

require_any_file() {
  local message="$1"
  shift
  for path in "$@"; do
    if [[ -e "$path" ]]; then
      return 0
    fi
  done
  echo "$message" >&2
  exit 1
}

if [[ -f "$INSTALL_MARKER" && "$FORCE" -ne 1 ]]; then
  echo "Install marker already exists: $INSTALL_MARKER"
  echo "Use --force to re-check runtime dependencies and refresh the marker."
  exit 0
fi

if [[ ! -d "$RUNTIME_ROOT" ]]; then
  echo "Runtime directory not found: $RUNTIME_ROOT" >&2
  exit 1
fi

LINUX_RUNTIME="$RUNTIME_ROOT/linux"
PG_BIN="$LINUX_RUNTIME/postgresql/bin"
JDK_BIN="$LINUX_RUNTIME/jdk/bin"
GEOSERVER_HOME="$LINUX_RUNTIME/geoserver"
PYTHON_EXE="$LINUX_RUNTIME/python/bin/python"

require_executable "$PG_BIN/pg_ctl" "PostgreSQL not found. Expected: runtime/linux/postgresql/bin/pg_ctl"
require_executable "$PG_BIN/initdb" "initdb not found. Expected: runtime/linux/postgresql/bin/initdb"
require_executable "$PG_BIN/psql" "psql not found. Expected: runtime/linux/postgresql/bin/psql"
require_executable "$PG_BIN/createdb" "createdb not found. Expected: runtime/linux/postgresql/bin/createdb"
require_executable "$PG_BIN/pg_isready" "pg_isready not found. Expected: runtime/linux/postgresql/bin/pg_isready"
require_executable "$PG_BIN/pg_dump" "pg_dump not found. Expected: runtime/linux/postgresql/bin/pg_dump"
require_executable "$JDK_BIN/java" "JDK not found. Expected: runtime/linux/jdk/bin/java"
require_executable "$PYTHON_EXE" "Python not found. Expected: runtime/linux/python/bin/python"
require_any_file "GeoServer startup file not found. Expected runtime/linux/geoserver/bin/startup.sh or runtime/linux/geoserver/start.jar" \
  "$GEOSERVER_HOME/bin/startup.sh" \
  "$GEOSERVER_HOME/start.jar"

if ! "$PYTHON_EXE" -c "import fastapi, uvicorn, sqlalchemy, psycopg, pydantic_settings, fiona" >/dev/null 2>&1; then
  echo "Backend Python dependencies are missing in runtime/linux/python. Install backend/requirements.txt into the bundled runtime Python before deployment." >&2
  exit 1
fi

mkdir -p "$STATE_DIR" "$RUNTIME_ROOT/data" "$RUNTIME_ROOT/logs"
cat > "$INSTALL_MARKER" <<EOF
{
  "platform": "linux",
  "installedAt": "$(date -Iseconds)",
  "runtimeRoot": "$RUNTIME_ROOT"
}
EOF

echo "Install check passed."
echo "Marker written: $INSTALL_MARKER"
echo "Next step: bash ./scripts/init.sh"
