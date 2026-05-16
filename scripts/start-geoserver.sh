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
DEFAULT_LAYER="${GEOSERVER_DEFAULT_LAYER:-survey_dk_result}"
TABLE_NAME="${GEOSERVER_TABLE_NAME:-survey_dk_result}"
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

  STYLES_DIR="$PROJECT_ROOT/datas/geoserver-styles"

  # ── Helper: check if a PostGIS table has a geometry column ──
  check_feature_table() {
    local table="$1"
    local count
    count="$(PGPASSWORD="$DB_PASSWORD" "$RUNTIME_ROOT/linux/postgresql/bin/psql" -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
      "SELECT count(*) FROM information_schema.tables t JOIN geometry_columns g ON g.f_table_schema = t.table_schema AND g.f_table_name = t.table_name WHERE t.table_schema = '$DB_SCHEMA' AND t.table_name = '$table' AND t.table_type IN ('BASE TABLE', 'VIEW');" 2>/dev/null | tr -d '[:space:]')"
    if [[ "${count:-0}" != "0" ]]; then
      echo "$table"
    else
      echo ""
    fi
  }

  # ── Upload SLD styles ──
  upload_style() {
    local style_name="$1" sld_file="$2"
    local style_url="$REST_URL/workspaces/$WORKSPACE/styles?name=$style_name"
    local check_url="$REST_URL/workspaces/$WORKSPACE/styles/$style_name.json"
    if [[ ! -f "$sld_file" ]]; then
      echo "  SLD file not found: $sld_file — style '$style_name' skipped"
      return
    fi
    if curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$check_url" >/dev/null 2>&1; then
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X PUT -H "Content-Type: application/vnd.ogc.sld+xml" --data-binary "@$sld_file" "$style_url" >/dev/null 2>&1 && echo "  Style updated: $style_name" || echo "  Style update failed: $style_name"
    else
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X POST -H "Content-Type: application/vnd.ogc.sld+xml" --data-binary "@$sld_file" "$style_url" >/dev/null 2>&1 && echo "  Style created: $style_name" || echo "  Style creation failed: $style_name"
    fi
  }

  # ── Publish a single feature type ──
  publish_feature() {
    local layer="$1" table="$2" title="$3" srs="$4" style="$5"
    local ft_url="$REST_URL/workspaces/$WORKSPACE/datastores/$STORE_NAME/featuretypes/$layer.json"
    local layer_url="$REST_URL/layers/$WORKSPACE:$layer.json"

    local publish_table
    publish_table="$(check_feature_table "$table")"
    if [[ -z "$publish_table" ]]; then
      echo "  PostGIS table skipped (no geometry): $DB_SCHEMA.$table"
      return 1
    fi

    if curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$ft_url" >/dev/null 2>&1; then
      echo "  Feature type exists: $WORKSPACE:$layer"
      local projection_policy="FORCE_DECLARED"
      if [[ "$srs" != "EPSG:4527" ]]; then
        projection_policy="REPROJECT_TO_DECLARED"
      fi
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X PUT \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "{\"featureType\":{\"nativeName\":\"$publish_table\",\"title\":\"$title\",\"srs\":\"$srs\",\"projectionPolicy\":\"$projection_policy\",\"enabled\":true}}" \
        "$ft_url" >/dev/null 2>&1 && \
        echo "  Feature type updated: $title -> $publish_table" || \
        echo "  Feature type update failed: $WORKSPACE:$layer"
    else
      local projection_policy="FORCE_DECLARED"
      if [[ "$srs" != "EPSG:4527" ]]; then
        projection_policy="REPROJECT_TO_DECLARED"
      fi
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "{\"featureType\":{\"name\":\"$layer\",\"nativeName\":\"$publish_table\",\"title\":\"$title\",\"srs\":\"$srs\",\"projectionPolicy\":\"$projection_policy\",\"enabled\":true}}" \
        "$REST_URL/workspaces/$WORKSPACE/datastores/$STORE_NAME/featuretypes" >/dev/null && \
        echo "  Feature type published: $WORKSPACE:$layer" || \
        echo "  Feature type publish failed: $WORKSPACE:$layer"
    fi

    curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X PUT \
      -H "Content-Type: application/json; charset=utf-8" \
      -d "{\"featureType\":{\"name\":\"$layer\"}}" \
      "$ft_url?recalculate=nativebbox,latlonbbox" >/dev/null 2>&1 && \
      echo "  Feature type bounds recalculated: $WORKSPACE:$layer" || \
      echo "  Feature type bounds recalculation failed: $WORKSPACE:$layer"

    if curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$layer_url" >/dev/null 2>&1; then
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X PUT \
        -H "Content-Type: application/json; charset=utf-8" \
        -d "{\"layer\":{\"defaultStyle\":{\"name\":\"$style\"}}}" \
        "$layer_url" >/dev/null 2>&1 && \
        echo "  Default style set: $style" || \
        echo "  Style assignment failed: $WORKSPACE:$layer"
    fi
    return 0
  }

  # ── Create / update layer group ──
  publish_layer_group() {
    local group_name="$1" group_title="$2"
    shift 2
    local published_json=""
    for layer in "$@"; do
      published_json="${published_json}{\"@type\":\"layer\",\"name\":\"$WORKSPACE:$layer\"},"
    done
    published_json="[${published_json%,}]"
    local group_url="$REST_URL/workspaces/$WORKSPACE/layergroups/$group_name.json"
    local body="{\"layerGroup\":{\"name\":\"$group_name\",\"mode\":\"SINGLE\",\"title\":\"$group_title\",\"publishables\":{\"published\":$published_json}}}"
    if curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" "$group_url" >/dev/null 2>&1; then
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X PUT -H "Content-Type: application/json; charset=utf-8" -d "$body" "$group_url" >/dev/null 2>&1 && \
        echo "Layer group updated: $group_name ($# layers)" || \
        echo "Layer group update failed: $group_name"
    else
      curl -fsS -u "$ADMIN_USER:$ADMIN_PASSWORD" -X POST -H "Content-Type: application/json; charset=utf-8" -d "$body" "$REST_URL/workspaces/$WORKSPACE/layergroups" >/dev/null 2>&1 && \
        echo "Layer group created: $group_name ($# layers, SINGLE mode)" || \
        echo "Layer group creation failed: $group_name"
    fi
  }

  # ── Upload all styles ──
  echo "Uploading SLD styles..."
  upload_style "survey_dk_result" "$STYLES_DIR/survey_dk_result.sld"
  upload_style "czkfbj"           "$STYLES_DIR/czkfbj.sld"
  upload_style "dltb"             "$STYLES_DIR/dltb.sld"
  upload_style "gdbhmb"           "$STYLES_DIR/gdbhmb.sld"
  upload_style "stbhhx"           "$STYLES_DIR/stbhhx.sld"
  upload_style "xzq"              "$STYLES_DIR/xzq.sld"
  upload_style "xzqjx"            "$STYLES_DIR/xzqjx.sld"
  upload_style "yjjbntbhtb"       "$STYLES_DIR/yjjbntbhtb.sld"

  # ── Publish all feature types ──
  echo "Publishing GeoServer layers..."
  PUBLISHED=()
  publish_feature "survey_dk_result" "survey_dk_result" "承包地块"             "EPSG:4527" "survey_dk_result" && PUBLISHED+=("survey_dk_result")
  publish_feature "czkfbj"          "czkfbj"          "村庄开发边界"             "EPSG:4527" "czkfbj"          && PUBLISHED+=("czkfbj")
  publish_feature "dltb"            "dltb"            "地类图斑"                 "EPSG:4527" "dltb"            && PUBLISHED+=("dltb")
  publish_feature "gdbhmb"          "gdbhmb"          "耕地保护目标"             "EPSG:4527" "gdbhmb"          && PUBLISHED+=("gdbhmb")
  publish_feature "stbhhx"          "stbhhx"          "生态保护红线"             "EPSG:4490" "stbhhx"          && PUBLISHED+=("stbhhx")
  publish_feature "xzq"             "xzq"             "行政区"                   "EPSG:4527" "xzq"             && PUBLISHED+=("xzq")
  publish_feature "xzqjx"           "xzqjx"           "行政区界线"               "EPSG:4527" "xzqjx"           && PUBLISHED+=("xzqjx")
  publish_feature "yjjbntbhtb"      "yjjbntbhtb"      "永久基本农田保护图斑"     "EPSG:4527" "yjjbntbhtb"      && PUBLISHED+=("yjjbntbhtb")

  if [[ ${#PUBLISHED[@]} -eq 0 ]]; then
    echo "No spatial layers were found in the database."
    if [[ "$REQUIRE_DEFAULT_LAYER" == "1" ]]; then
      exit 1
    fi
    echo "GeoServer ready: $BASE_URL"
    exit 0
  fi

  # ── Create layer group ──
  echo "Creating layer group..."
  publish_layer_group "rural_land_layers" "农村承包经营权调查图层组" "${PUBLISHED[@]}"

  # ── Summary ──
  echo ""
  echo "GeoServer layer summary:"
  for layer in "${PUBLISHED[@]}"; do
    echo "  ✓ $WORKSPACE:$layer"
  done
  echo "  Layer group: $WORKSPACE:rural_land_layers (SINGLE mode)"
  echo "GeoServer ready: $BASE_URL"
fi
