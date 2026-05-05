#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
JDK_HOME="$RUNTIME_ROOT/linux/jdk"
GEOSERVER_HOME="$RUNTIME_ROOT/linux/geoserver"
GEOSERVER_DATA_DIR="$RUNTIME_ROOT/data/geoserver-data"
LOG_DIR="$RUNTIME_ROOT/logs"
PORT="${GEOSERVER_PORT:-8080}"
BASE_URL="http://127.0.0.1:$PORT/geoserver"
REST_URL="$BASE_URL/rest"
WORKSPACE="${GEOSERVER_WORKSPACE:-erlunyanbao}"
NAMESPACE_URI="${GEOSERVER_NAMESPACE_URI:-http://erlunyanbao}"
STORE_NAME="${GEOSERVER_STORE_NAME:-postgis}"
DEFAULT_LAYER="${GEOSERVER_DEFAULT_LAYER:-DK3213242017}"
TABLE_NAME="${GEOSERVER_TABLE_NAME:-DK3213242017}"
REQUIRE_DEFAULT_LAYER="${GEOSERVER_REQUIRE_DEFAULT_LAYER:-0}"
DB_HOST="${DATABASE_HOST:-127.0.0.1}"
DB_PORT="${DATABASE_PORT:-15432}"
DB_NAME="${DATABASE_NAME:-erlunyanbao}"
DB_USER="${DATABASE_USER:-RurallandContractExtension}"
DB_PASSWORD="${DATABASE_PASSWORD:-RurallandContractExtension}"
DB_SCHEMA="${DATABASE_SCHEMA:-public}"
LAYER_SRS="${GEOSERVER_LAYER_SRS:-EPSG:4527}"
ADMIN_USER="${GEOSERVER_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${GEOSERVER_ADMIN_PASSWORD:-geoserver}"

if [[ ! -x "$JDK_HOME/bin/java" ]]; then
  echo "JDK not found: $JDK_HOME/bin/java. Put Linux JDK under runtime/linux/jdk." >&2
  exit 1
fi

mkdir -p "$GEOSERVER_DATA_DIR" "$LOG_DIR"
if [[ -z "$(find "$GEOSERVER_DATA_DIR" -mindepth 1 -maxdepth 1 2>/dev/null)" && -d "$GEOSERVER_HOME/data_dir" ]]; then
  cp -R "$GEOSERVER_HOME/data_dir/." "$GEOSERVER_DATA_DIR/"
fi

export JAVA_HOME="$JDK_HOME"
export PATH="$JDK_HOME/bin:$PATH"
export GEOSERVER_HOME
export GEOSERVER_DATA_DIR
export GEOSERVER_OPTS="-DGEOSERVER_DATA_DIR=$GEOSERVER_DATA_DIR -Djetty.port=$PORT"

if command -v curl >/dev/null 2>&1 && curl -fsS "$BASE_URL/web/" >/dev/null 2>&1; then
  echo "GeoServer is already running: $BASE_URL"
else
  if [[ -x "$GEOSERVER_HOME/bin/startup.sh" ]]; then
    nohup "$GEOSERVER_HOME/bin/startup.sh" > "$LOG_DIR/geoserver.log" 2>&1 &
  elif [[ -f "$GEOSERVER_HOME/start.jar" ]]; then
    nohup "$JDK_HOME/bin/java" -DGEOSERVER_DATA_DIR="$GEOSERVER_DATA_DIR" -Djetty.port="$PORT" -jar "$GEOSERVER_HOME/start.jar" > "$LOG_DIR/geoserver.log" 2>&1 &
  else
    echo "GeoServer startup file not found. Put GeoServer under runtime/linux/geoserver." >&2
    exit 1
  fi

  echo "GeoServer starting: $BASE_URL"
fi

if command -v curl >/dev/null 2>&1; then
  for _ in $(seq 1 60); do
    if curl -fsS "$BASE_URL/web/" >/dev/null 2>&1; then
      echo "GeoServer ready: $BASE_URL"
      break
    fi
    sleep 2
  done
  if ! curl -fsS "$BASE_URL/web/" >/dev/null 2>&1; then
    echo "GeoServer startup timed out. Check $LOG_DIR/geoserver.log" >&2
    exit 1
  fi

  if ! curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$REST_URL/workspaces/$WORKSPACE.json" >/dev/null 2>&1; then
    echo "GeoServer workspace not found: $WORKSPACE"
    curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" \
      -H "Content-Type: application/json" \
      -d "{\"workspace\":{\"name\":\"$WORKSPACE\"}}" \
      "$REST_URL/workspaces" >/dev/null
    echo "GeoServer workspace created: $WORKSPACE"
  fi

  if ! curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$REST_URL/workspaces/$WORKSPACE/datastores/$STORE_NAME.json" >/dev/null 2>&1; then
    echo "GeoServer PostGIS store not found: $WORKSPACE/$STORE_NAME"
    curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" \
      -H "Content-Type: application/json" \
      -d "{\"dataStore\":{\"name\":\"$STORE_NAME\",\"enabled\":true,\"type\":\"PostGIS\",\"connectionParameters\":{\"entry\":[{\"@key\":\"dbtype\",\"\$\":\"postgis\"},{\"@key\":\"host\",\"\$\":\"$DB_HOST\"},{\"@key\":\"port\",\"\$\":\"$DB_PORT\"},{\"@key\":\"database\",\"\$\":\"$DB_NAME\"},{\"@key\":\"schema\",\"\$\":\"$DB_SCHEMA\"},{\"@key\":\"namespace\",\"\$\":\"$NAMESPACE_URI\"},{\"@key\":\"user\",\"\$\":\"$DB_USER\"},{\"@key\":\"passwd\",\"\$\":\"$DB_PASSWORD\"},{\"@key\":\"Expose primary keys\",\"\$\":\"true\"},{\"@key\":\"validate connections\",\"\$\":\"true\"}]}}}" \
      "$REST_URL/workspaces/$WORKSPACE/datastores" >/dev/null
    echo "GeoServer PostGIS store created: $WORKSPACE/$STORE_NAME -> $DB_HOST:$DB_PORT/$DB_NAME"
  else
    curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" \
      -X PUT \
      -H "Content-Type: application/json" \
      -d "{\"dataStore\":{\"name\":\"$STORE_NAME\",\"enabled\":true,\"type\":\"PostGIS\",\"connectionParameters\":{\"entry\":[{\"@key\":\"dbtype\",\"\$\":\"postgis\"},{\"@key\":\"host\",\"\$\":\"$DB_HOST\"},{\"@key\":\"port\",\"\$\":\"$DB_PORT\"},{\"@key\":\"database\",\"\$\":\"$DB_NAME\"},{\"@key\":\"schema\",\"\$\":\"$DB_SCHEMA\"},{\"@key\":\"namespace\",\"\$\":\"$NAMESPACE_URI\"},{\"@key\":\"user\",\"\$\":\"$DB_USER\"},{\"@key\":\"passwd\",\"\$\":\"$DB_PASSWORD\"},{\"@key\":\"Expose primary keys\",\"\$\":\"true\"},{\"@key\":\"validate connections\",\"\$\":\"true\"}]}}}" \
      "$REST_URL/workspaces/$WORKSPACE/datastores/$STORE_NAME" >/dev/null
    echo "GeoServer PostGIS store updated: $WORKSPACE/$STORE_NAME -> $DB_HOST:$DB_PORT/$DB_NAME"
  fi

  if ! curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$REST_URL/workspaces/$WORKSPACE/datastores/$STORE_NAME/featuretypes/$DEFAULT_LAYER.json" >/dev/null 2>&1; then
    FEATURE_TABLE_COUNT="$(PGPASSWORD="$DB_PASSWORD" "$RUNTIME_ROOT/linux/postgresql/bin/psql" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc "SELECT count(*) FROM information_schema.tables t JOIN geometry_columns g ON g.f_table_schema = t.table_schema AND g.f_table_name = t.table_name WHERE t.table_schema = '$DB_SCHEMA' AND t.table_name = '$TABLE_NAME' AND t.table_type = 'BASE TABLE';" 2>/dev/null | tr -d '[:space:]')"
    if [[ "${FEATURE_TABLE_COUNT:-0}" == "0" ]]; then
      echo "PostGIS feature table was not found or has no geometry column: $DB_SCHEMA.$TABLE_NAME. Add its DDL to scripts/sql/init-postgis-schema.sql, rerun init, then publish $WORKSPACE:$DEFAULT_LAYER."
      if [[ "$REQUIRE_DEFAULT_LAYER" == "1" ]]; then
        exit 1
      fi
      echo "GeoServer layer publishing skipped; backend startup will continue."
      exit 0
    fi

    echo "GeoServer feature type not found: $WORKSPACE/$STORE_NAME/$DEFAULT_LAYER"
    curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" \
      -H "Content-Type: application/json" \
      -d "{\"featureType\":{\"name\":\"$DEFAULT_LAYER\",\"nativeName\":\"$TABLE_NAME\",\"title\":\"$DEFAULT_LAYER\",\"srs\":\"$LAYER_SRS\",\"projectionPolicy\":\"FORCE_DECLARED\",\"enabled\":true}}" \
      "$REST_URL/workspaces/$WORKSPACE/datastores/$STORE_NAME/featuretypes" >/dev/null || {
        echo "Failed to publish GeoServer layer $WORKSPACE:$DEFAULT_LAYER from table $DB_SCHEMA.$TABLE_NAME. Ensure the PostGIS table exists and has a geometry column." >&2
        exit 1
      }
    echo "GeoServer feature type published: $WORKSPACE:$DEFAULT_LAYER from table $DB_SCHEMA.$TABLE_NAME"
  fi

  if curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$REST_URL/layers/$WORKSPACE:$DEFAULT_LAYER.json" >/dev/null 2>&1; then
    echo "GeoServer default layer exists: $WORKSPACE:$DEFAULT_LAYER"
  else
    echo "GeoServer feature type was created, but layer endpoint is still unavailable: $WORKSPACE:$DEFAULT_LAYER" >&2
    exit 1
  fi
fi
