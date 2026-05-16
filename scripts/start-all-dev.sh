#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
STATE_DIR="$RUNTIME_ROOT/.state"
INSTALL_MARKER="$STATE_DIR/installed.json"
INIT_MARKER="$STATE_DIR/initialized.json"
RUNTIME_ENV_FILE="$STATE_DIR/runtime.env"

if [[ ! -f "$INSTALL_MARKER" ]]; then
  echo "System is not installed yet. Running install..."
  "$SCRIPT_DIR/install.sh"
  if [[ ! -f "$INSTALL_MARKER" ]]; then
    echo "Install did not complete. Marker was not created: $INSTALL_MARKER" >&2
    exit 1
  fi
fi

if [[ ! -f "$INIT_MARKER" ]]; then
  echo "System is installed but not initialized yet. Running init..."
  "$SCRIPT_DIR/init.sh"
  if [[ ! -f "$INIT_MARKER" ]]; then
    echo "Initialization did not complete. Marker was not created: $INIT_MARKER" >&2
    exit 1
  fi
fi

if [[ ! -f "$RUNTIME_ENV_FILE" ]]; then
  echo "Runtime config was not found. Refreshing initialization metadata..."
  "$SCRIPT_DIR/init.sh" --force
  if [[ ! -f "$RUNTIME_ENV_FILE" ]]; then
    echo "Runtime config was not created: $RUNTIME_ENV_FILE" >&2
    exit 1
  fi
fi

set -a
# shellcheck disable=SC1090
source "$RUNTIME_ENV_FILE"
set +a

export DATABASE_HOST="${DATABASE_HOST:-127.0.0.1}"
export DATABASE_PORT="${DATABASE_PORT:-15432}"
export DATABASE_NAME="${DATABASE_NAME:-erlunyanbao}"
export DATABASE_USER="${DATABASE_USER:-RurallandContractExtension}"
export DATABASE_PASSWORD="${DATABASE_PASSWORD:-RurallandContractExtension}"

PG_DATA_DIR="$RUNTIME_ROOT/data/pgdata"
if [[ "$DATABASE_PASSWORD" == "RurallandContractExtension" && -f "$PG_DATA_DIR/PG_VERSION" ]]; then
  echo "Database password is still the default value. Re-initializing with a random password..."
  "$SCRIPT_DIR/init.sh" --force
  if [[ ! -f "$RUNTIME_ENV_FILE" ]]; then
    echo "Re-initialization failed. Runtime config was not created." >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  source "$RUNTIME_ENV_FILE"
  set +a
  export DATABASE_HOST="${DATABASE_HOST:-127.0.0.1}"
  export DATABASE_PORT="${DATABASE_PORT:-15432}"
  export DATABASE_NAME="${DATABASE_NAME:-erlunyanbao}"
  export DATABASE_USER="${DATABASE_USER:-RurallandContractExtension}"
  export DATABASE_PASSWORD="${DATABASE_PASSWORD:-RurallandContractExtension}"
fi

"$SCRIPT_DIR/start-postgres.sh"
"$SCRIPT_DIR/start-geoserver.sh"

cd "$PROJECT_ROOT/backend"
if [[ -x "$PROJECT_ROOT/runtime/linux/python/bin/python" ]]; then
  PYTHON_CMD="$PROJECT_ROOT/runtime/linux/python/bin/python"
else
  echo "Python not found. Put portable Python under runtime/linux/python." >&2
  exit 1
fi

if ! "$PYTHON_CMD" -c "import fastapi, uvicorn, sqlalchemy, psycopg, pydantic_settings, fiona" >/dev/null 2>&1; then
  echo "Backend Python dependencies are missing in runtime/linux/python. Install backend/requirements.txt into the bundled runtime Python before deployment." >&2
  exit 1
fi

"$PYTHON_CMD" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
