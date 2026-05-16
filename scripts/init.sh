#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
STATE_DIR="$RUNTIME_ROOT/.state"
INSTALL_MARKER="$STATE_DIR/installed.json"
INIT_MARKER="$STATE_DIR/initialized.json"
RUNTIME_ENV_FILE="$STATE_DIR/runtime.env"
PG_BIN="$RUNTIME_ROOT/linux/postgresql/bin"
LOG_DIR="$RUNTIME_ROOT/logs"
SQL_INIT_FILE="$SCRIPT_DIR/sql/init-postgis-schema.sql"
FORCE=0
IMPORT_SCHEMA_FROM_SOURCE="${IMPORT_SCHEMA_FROM_SOURCE:-0}"

SCHEMA_SOURCE_HOST="${SCHEMA_SOURCE_HOST:-127.0.0.1}"
SCHEMA_SOURCE_PORT="${SCHEMA_SOURCE_PORT:-5432}"
SCHEMA_SOURCE_DB_NAME="${SCHEMA_SOURCE_DB_NAME:-erlunyanbao}"
SCHEMA_SOURCE_USER="${SCHEMA_SOURCE_USER:-RurallandContractExtension}"
SCHEMA_SOURCE_PASSWORD="${SCHEMA_SOURCE_PASSWORD:-RurallandContractExtension}"
SCHEMA_NAME="${SCHEMA_NAME:-public}"

if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ ! -f "$INSTALL_MARKER" ]]; then
  echo "Install marker was not found. Run: bash ./scripts/install.sh" >&2
  exit 1
fi

if [[ -f "$INIT_MARKER" && "$FORCE" -ne 1 ]]; then
  echo "Init marker already exists: $INIT_MARKER"
  echo "Use --force to re-run initialization and refresh the marker."
  exit 0
fi

if [[ -f "$RUNTIME_ENV_FILE" ]]; then
  while IFS='=' read -r key value; do
    key="${key//[$'\r\n']/}"
    value="${value//[$'\r\n']/}"
    [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
    case "$key" in
      DATABASE_PASSWORD) DATABASE_PASSWORD="$value" ;;
      DATABASE_USER)     DATABASE_USER="$value" ;;
      DATABASE_NAME)     DATABASE_NAME="$value" ;;
      DATABASE_PORT)     DATABASE_PORT="$value" ;;
      DATABASE_HOST)     DATABASE_HOST="$value" ;;
    esac
  done < "$RUNTIME_ENV_FILE"
fi

PG_DATA_DIR="$RUNTIME_ROOT/data/pgdata"
NEEDS_PASSWORD_ROTATION=0
if [[ "${DATABASE_PASSWORD:-RurallandContractExtension}" == "RurallandContractExtension" && -f "$PG_DATA_DIR/PG_VERSION" ]]; then
  NEEDS_PASSWORD_ROTATION=1
fi

"$SCRIPT_DIR/start-postgres.sh"

if [[ -f "$STATE_DIR/.db-password" ]]; then
  DATABASE_PASSWORD=$(cat "$STATE_DIR/.db-password")
  rm -f "$STATE_DIR/.db-password"
fi

TARGET_DB_HOST="${DATABASE_HOST:-127.0.0.1}"
TARGET_DB_PORT="${DATABASE_PORT:-15432}"
TARGET_DB_NAME="${DATABASE_NAME:-erlunyanbao}"
TARGET_DB_USER="${DATABASE_USER:-RurallandContractExtension}"
TARGET_DB_PASSWORD="${DATABASE_PASSWORD:-RurallandContractExtension}"

if [[ "$NEEDS_PASSWORD_ROTATION" -eq 1 && "$TARGET_DB_PASSWORD" == "RurallandContractExtension" ]]; then
  echo "Database password is still the default value. Rotating to a random password (data preserved)..."
  NEW_PASSWORD=$(tr -dc 'A-Za-z0-9!#$%&*' < /dev/urandom | head -c24)
  ESCAPED_PASSWORD="${NEW_PASSWORD//\'/\'\'}"
  PGPASSWORD="$TARGET_DB_PASSWORD" "$PG_BIN/psql" -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" -c "ALTER ROLE \"$TARGET_DB_USER\" PASSWORD '$ESCAPED_PASSWORD'"
  if [[ $? -ne 0 ]]; then
    echo "Failed to rotate database password." >&2
    exit 1
  fi
  TARGET_DB_PASSWORD="$NEW_PASSWORD"
  export DATABASE_PASSWORD="$NEW_PASSWORD"
  echo "Password rotated. New password stored in runtime/.state/runtime.env"
fi

psql_scalar() {
  local host="$1"
  local port="$2"
  local db="$3"
  local user="$4"
  local password="$5"
  local sql="$6"
  PGPASSWORD="$password" "$PG_BIN/psql" -h "$host" -p "$port" -U "$user" -d "$db" -tAc "$sql" 2>/dev/null | tr -d '[:space:]'
}

database_available() {
  [[ "$(psql_scalar "$1" "$2" "$3" "$4" "$5" "SELECT 1")" == "1" ]]
}

user_table_count() {
  local host="$1"
  local port="$2"
  local db="$3"
  local user="$4"
  local password="$5"
  local schema="$6"
  psql_scalar "$host" "$port" "$db" "$user" "$password" "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$schema' AND table_type = 'BASE TABLE' AND table_name NOT IN ('spatial_ref_sys');"
}

if [[ "$IMPORT_SCHEMA_FROM_SOURCE" == "1" ]]; then
  if [[ "$SCHEMA_SOURCE_HOST" == "$TARGET_DB_HOST" && "$SCHEMA_SOURCE_PORT" == "$TARGET_DB_PORT" && "$SCHEMA_SOURCE_DB_NAME" == "$TARGET_DB_NAME" ]]; then
    echo "Schema source and target are the same database. Schema import skipped."
  elif ! database_available "$SCHEMA_SOURCE_HOST" "$SCHEMA_SOURCE_PORT" "$SCHEMA_SOURCE_DB_NAME" "$SCHEMA_SOURCE_USER" "$SCHEMA_SOURCE_PASSWORD"; then
    echo "Schema source database is not available: $SCHEMA_SOURCE_HOST:$SCHEMA_SOURCE_PORT/$SCHEMA_SOURCE_DB_NAME. Schema import skipped."
  else
    TARGET_TABLE_COUNT="$(user_table_count "$TARGET_DB_HOST" "$TARGET_DB_PORT" "$TARGET_DB_NAME" "$TARGET_DB_USER" "$TARGET_DB_PASSWORD" "$SCHEMA_NAME")"
    if [[ "${TARGET_TABLE_COUNT:-0}" -gt 0 ]]; then
      echo "Target schema $SCHEMA_NAME already has $TARGET_TABLE_COUNT user table(s). Schema import skipped."
    else
      mkdir -p "$LOG_DIR"
      DUMP_FILE="$LOG_DIR/schema-$SCHEMA_NAME.sql"
      echo "Importing table structure from $SCHEMA_SOURCE_HOST:$SCHEMA_SOURCE_PORT/$SCHEMA_SOURCE_DB_NAME schema $SCHEMA_NAME..."
      PGPASSWORD="$SCHEMA_SOURCE_PASSWORD" "$PG_BIN/pg_dump" \
        -h "$SCHEMA_SOURCE_HOST" \
        -p "$SCHEMA_SOURCE_PORT" \
        -U "$SCHEMA_SOURCE_USER" \
        -d "$SCHEMA_SOURCE_DB_NAME" \
        --schema-only \
        --schema="$SCHEMA_NAME" \
        --no-owner \
        --no-privileges \
        --file="$DUMP_FILE"
      PGPASSWORD="$TARGET_DB_PASSWORD" "$PG_BIN/psql" \
        -h "$TARGET_DB_HOST" \
        -p "$TARGET_DB_PORT" \
        -U "$TARGET_DB_USER" \
        -d "$TARGET_DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -f "$DUMP_FILE"
      echo "Schema imported into $TARGET_DB_HOST:$TARGET_DB_PORT/$TARGET_DB_NAME."
    fi
  fi
fi

if [[ -f "$SQL_INIT_FILE" ]]; then
  EXISTING_FEATURE_TABLE="$(PGPASSWORD="$TARGET_DB_PASSWORD" "$PG_BIN/psql" \
    -h "$TARGET_DB_HOST" \
    -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" \
    -d "$TARGET_DB_NAME" \
    -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'cbdkxx'" 2>/dev/null | tr -d '[:space:]')"
  if [[ "${EXISTING_FEATURE_TABLE:-0}" != "0" ]]; then
    echo "PostGIS schema initialization skipped; public.cbdkxx already exists."
  else
    echo "Running SQL initialization file: $SQL_INIT_FILE"
    PGPASSWORD="$TARGET_DB_PASSWORD" "$PG_BIN/psql" \
      -h "$TARGET_DB_HOST" \
      -p "$TARGET_DB_PORT" \
      -U "$TARGET_DB_USER" \
      -d "$TARGET_DB_NAME" \
      -v ON_ERROR_STOP=1 \
      -f "$SQL_INIT_FILE"
  fi
fi

if [[ -x "$PROJECT_ROOT/runtime/linux/python/bin/python" ]]; then
  PYTHON_CMD="$PROJECT_ROOT/runtime/linux/python/bin/python"
else
  echo "Python not found. Put portable Python under runtime/linux/python." >&2
  exit 1
fi

if ! "$PYTHON_CMD" -c "import fastapi, sqlalchemy, psycopg, pydantic_settings, fiona" >/dev/null 2>&1; then
  echo "Backend Python dependencies are missing in runtime/linux/python. Install backend/requirements.txt into the bundled runtime Python before deployment." >&2
  exit 1
fi

(
  cd "$PROJECT_ROOT/backend/dist"
  DATABASE_HOST="$TARGET_DB_HOST" \
  DATABASE_PORT="$TARGET_DB_PORT" \
  DATABASE_NAME="$TARGET_DB_NAME" \
  DATABASE_USER="$TARGET_DB_USER" \
  DATABASE_PASSWORD="$TARGET_DB_PASSWORD" \
  "$PYTHON_CMD" -m app.db.bootstrap --schema
)

"$SCRIPT_DIR/start-geoserver.sh"

mkdir -p "$STATE_DIR"
cat > "$RUNTIME_ENV_FILE" <<EOF
DATABASE_HOST=$TARGET_DB_HOST
DATABASE_PORT=$TARGET_DB_PORT
DATABASE_NAME=$TARGET_DB_NAME
DATABASE_USER=$TARGET_DB_USER
DATABASE_PASSWORD=$TARGET_DB_PASSWORD
GEOSERVER_PORT=${GEOSERVER_PORT:-8080}
GEOSERVER_URL=http://127.0.0.1:${GEOSERVER_PORT:-8080}/geoserver
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000
BACKEND_URL=http://127.0.0.1:8000
FRONTEND_HOST=127.0.0.1
FRONTEND_PORT=5173
FRONTEND_URL=http://127.0.0.1:5173
EOF

cat > "$INIT_MARKER" <<EOF
{
  "platform": "linux",
  "initializedAt": "$(date -Iseconds)",
  "database": "$TARGET_DB_NAME",
  "databasePort": "$TARGET_DB_PORT",
  "geoserverUrl": "http://127.0.0.1:${GEOSERVER_PORT:-8080}/geoserver"
}
EOF

echo "Initialization passed."
echo "Marker written: $INIT_MARKER"
echo "Runtime config written: $RUNTIME_ENV_FILE"
echo "Next step: bash ./scripts/start-all.sh"
