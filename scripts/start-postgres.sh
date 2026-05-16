#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
STATE_DIR="$RUNTIME_ROOT/.state"
PG_HOME="$RUNTIME_ROOT/linux/postgresql"
PG_BIN="$PG_HOME/bin"
PG_DATA="$RUNTIME_ROOT/data/pgdata"
LOG_DIR="$RUNTIME_ROOT/logs"
PG_LOG="$LOG_DIR/postgres.log"

PORT="${DATABASE_PORT:-15432}"
DB_NAME="${DATABASE_NAME:-erlunyanbao}"
DB_USER="${DATABASE_USER:-RurallandContractExtension}"
DB_PASSWORD="${DATABASE_PASSWORD:-RurallandContractExtension}"

require_file() {
  if [[ ! -e "$1" ]]; then
    echo "$2" >&2
    exit 1
  fi
}

require_file "$PG_BIN/pg_ctl" "PostgreSQL not found: $PG_BIN/pg_ctl. Put Linux PostgreSQL/PostGIS under runtime/linux/postgresql."
require_file "$PG_BIN/initdb" "initdb not found: $PG_BIN/initdb"
require_file "$PG_BIN/psql" "psql not found: $PG_BIN/psql"
require_file "$PG_BIN/createdb" "createdb not found: $PG_BIN/createdb"
require_file "$PG_BIN/pg_isready" "pg_isready not found: $PG_BIN/pg_isready"

mkdir -p "$PG_DATA" "$LOG_DIR" "$STATE_DIR"

if "$PG_BIN/pg_ctl" status -D "$PG_DATA" >/dev/null 2>&1; then
  echo "PostgreSQL is already running."
else
  if [[ ! -f "$PG_DATA/PG_VERSION" ]]; then
    DB_PASSWORD=$(tr -dc 'A-Za-z0-9!#$%&*' < /dev/urandom | head -c24)
    echo "Generated random database password (stored in runtime/.state/runtime.env)"
    echo "$DB_PASSWORD" > "$STATE_DIR/.db-password"

    PW_FILE="$LOG_DIR/.pgpass-init"
    printf '%s\n' "$DB_PASSWORD" > "$PW_FILE"
    "$PG_BIN/initdb" -D "$PG_DATA" -U "$DB_USER" --encoding=UTF8 --locale=C --auth-host=scram-sha-256 --auth-local=trust --pwfile="$PW_FILE"
    rm -f "$PW_FILE"
  fi
  "$PG_BIN/pg_ctl" start -D "$PG_DATA" -l "$PG_LOG" -o "-p $PORT -h 127.0.0.1"
fi

export PGPASSWORD="$DB_PASSWORD"
for _ in $(seq 1 30); do
  if "$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PORT" -U "$DB_USER" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

"$PG_BIN/pg_isready" -h 127.0.0.1 -p "$PORT" -U "$DB_USER"

if [[ "$("$PG_BIN/psql" -h 127.0.0.1 -p "$PORT" -U "$DB_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" != "1" ]]; then
  "$PG_BIN/createdb" -h 127.0.0.1 -p "$PORT" -U "$DB_USER" "$DB_NAME"
fi

"$PG_BIN/psql" -h 127.0.0.1 -p "$PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis;"
"$PG_BIN/psql" -h 127.0.0.1 -p "$PORT" -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis_topology;"

echo "PostgreSQL/PostGIS ready: 127.0.0.1:$PORT/$DB_NAME"
