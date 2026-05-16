import base64
import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape


logger = logging.getLogger(__name__)


class GeoServerService:
    default_layers = (
        "survey_dk_result",
        "czkfbj",
        "dltb",
        "gdbhmb",
        "stbhhx",
        "xzq",
        "xzqjx",
        "yjjbntbhtb",
    )

    def __init__(self) -> None:
        self.base_url = os.getenv("GEOSERVER_URL", "http://127.0.0.1:8080/geoserver").rstrip("/")
        self.workspace = os.getenv("GEOSERVER_WORKSPACE", "erlunyanbao")
        self.store_name = os.getenv("GEOSERVER_STORE_NAME", "postgis")
        self.admin_user = os.getenv("GEOSERVER_ADMIN_USER", "admin")
        self.admin_password = os.getenv("GEOSERVER_ADMIN_PASSWORD", "geoserver")

    def recalculate_feature_type_bounds(self, layer_name: str) -> bool:
        layer_ref = self._normalize_layer_ref(layer_name)
        native_name = layer_ref.split(":", 1)[-1]
        url = (
            f"{self.base_url}/rest/workspaces/{self.workspace}/datastores/{self.store_name}"
            f"/featuretypes/{native_name}.json?recalculate=nativebbox,latlonbbox"
        )
        try:
            self._request_json(url, "PUT", {"featureType": {"name": native_name}}, timeout=10)
            logger.info("GeoServer bbox recalculated: %s", layer_ref)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                logger.warning("GeoServer bbox recalculation failed: layer=%s status=%s", layer_ref, exc.code)
            return False
        except Exception as exc:
            logger.warning("GeoServer bbox recalculation skipped: layer=%s error=%s", layer_ref, exc)
            return False

    def recalculate_default_bounds(self) -> None:
        updated = 0
        for layer_name in self.default_layers:
            if self.recalculate_feature_type_bounds(layer_name):
                updated += 1
        logger.info("GeoServer bbox recalculation finished: updated=%s", updated)

    def seed_tile_cache(
        self,
        layer_name: str,
        *,
        grid_set_id: str = "EPSG:4326",
        zoom_start: int = 0,
        zoom_stop: int = 15,
        mime_format: str = "image/png",
        seed_type: str = "reseed",
        thread_count: int = 2,
        bounds: list[float] | None = None,
    ) -> dict:
        layer_ref = self._normalize_layer_ref(layer_name)
        seed_type = seed_type.lower()
        if seed_type not in {"seed", "reseed", "truncate"}:
            raise ValueError("invalid seed type")
        if zoom_stop < zoom_start:
            raise ValueError("invalid zoom range")

        self.ensure_tile_layer(layer_ref, grid_set_id=grid_set_id, mime_format=mime_format)
        self.repair_local_tile_layer_meta(layer_ref)
        resolved_bounds = bounds or self.get_layer_bounds(layer_ref, grid_set_id=grid_set_id)
        seed_url = f"{self.base_url}/gwc/rest/seed/{urllib.parse.quote(layer_ref, safe='')}.json"
        seed_request = {
            "name": layer_ref,
            "gridSetId": grid_set_id,
            "zoomStart": int(zoom_start),
            "zoomStop": int(zoom_stop),
            "format": mime_format,
            "type": seed_type,
            "threadCount": int(thread_count),
        }
        if resolved_bounds:
            seed_request["bounds"] = {"coords": {"double": [float(value) for value in resolved_bounds]}}
        payload = {
            "seedRequest": seed_request
        }
        self._request_json(seed_url, "POST", payload, timeout=20)
        logger.info("GeoServer tile cache seed submitted: layer=%s zoom=%s-%s", layer_ref, zoom_start, zoom_stop)
        return {
            "layerName": layer_ref,
            "gridSetId": grid_set_id,
            "zoomStart": zoom_start,
            "zoomStop": zoom_stop,
            "format": mime_format,
            "type": seed_type,
            "bounds": resolved_bounds,
            "wmtsUrl": self.build_wmts_url(layer_ref, grid_set_id=grid_set_id, mime_format=mime_format),
        }

    def get_layer_bounds(self, layer_name: str, *, grid_set_id: str = "EPSG:4326") -> list[float] | None:
        layer_ref = self._normalize_layer_ref(layer_name)
        native_name = layer_ref.split(":", 1)[-1]
        url = (
            f"{self.base_url}/rest/workspaces/{self.workspace}/datastores/{self.store_name}"
            f"/featuretypes/{native_name}.json"
        )
        data = self._request_json_no_body(url, timeout=10)
        feature_type = data.get("featureType") or {}
        bbox_key = "latLonBoundingBox" if grid_set_id in {"EPSG:4326", "EPSG:900913"} else "nativeBoundingBox"
        bbox = feature_type.get(bbox_key) or feature_type.get("latLonBoundingBox") or feature_type.get("nativeBoundingBox")
        if not bbox:
            return None
        minx = bbox.get("minx")
        miny = bbox.get("miny")
        maxx = bbox.get("maxx")
        maxy = bbox.get("maxy")
        values = [minx, miny, maxx, maxy]
        if any(value is None for value in values):
            return None
        try:
            numbers = [float(value) for value in values]
        except (TypeError, ValueError):
            return None
        if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
            return None
        return numbers

    def ensure_tile_layer(self, layer_name: str, *, grid_set_id: str = "EPSG:4326", mime_format: str = "image/png") -> None:
        layer_ref = self._normalize_layer_ref(layer_name)
        url = f"{self.base_url}/gwc/rest/layers/{urllib.parse.quote(layer_ref, safe='')}.xml"
        payload = f"""<GeoServerLayer>
  <name>{escape(layer_ref)}</name>
  <enabled>true</enabled>
  <mimeFormats>
    <string>{escape(mime_format)}</string>
  </mimeFormats>
  <gridSubsets>
    <gridSubset>
      <gridSetName>{escape(grid_set_id)}</gridSetName>
    </gridSubset>
  </gridSubsets>
  <metaWidthHeight>
    <int>4</int>
    <int>4</int>
  </metaWidthHeight>
  <expireCache>0</expireCache>
  <expireClients>0</expireClients>
  <parameterFilters/>
  <gutter>0</gutter>
  <cacheWarningSkips/>
</GeoServerLayer>""".encode("utf-8")
        self._request_bytes(url, "PUT", payload, "text/xml; charset=utf-8", timeout=15)
        logger.info("GeoServer tile layer ensured: %s", layer_ref)

    def repair_local_tile_layer_meta(self, layer_name: str) -> None:
        data_dir = os.getenv("GEOSERVER_DATA_DIR")
        if not data_dir:
            project_root = Path(__file__).resolve().parents[3]
            data_dir = str(project_root / "runtime" / "data" / "geoserver-data")
        gwc_dir = Path(data_dir) / "gwc-layers"
        if not gwc_dir.exists():
            return
        layer_ref = self._normalize_layer_ref(layer_name)
        for path in gwc_dir.glob("*.xml"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                text = path.read_text(encoding="utf-8-sig")
            if f"<name>{layer_ref}</name>" not in text:
                continue
            repaired = text.replace(
                "<metaWidthHeight>\n    <int>0</int>\n    <int>0</int>\n  </metaWidthHeight>",
                "<metaWidthHeight>\n    <int>4</int>\n    <int>4</int>\n  </metaWidthHeight>",
            )
            if repaired != text:
                path.write_text(repaired, encoding="utf-8")
                logger.info("GeoServer local tile meta repaired: %s", path)

    def build_wmts_url(self, layer_name: str, *, grid_set_id: str = "EPSG:4326", mime_format: str = "image/png") -> str:
        layer_ref = self._normalize_layer_ref(layer_name)
        return (
            f"/geoserver/gwc/service/wmts?layer={urllib.parse.quote(layer_ref, safe=':')}"
            f"&style=&tilematrixset={urllib.parse.quote(grid_set_id)}"
            f"&Service=WMTS&Request=GetTile&Version=1.0.0&Format={urllib.parse.quote(mime_format)}"
        )

    def _request_json(self, url: str, method: str, payload: dict, *, timeout: int):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        raw = self._request_bytes(url, method, body, "application/json; charset=utf-8", timeout=timeout)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8", errors="ignore"))

    def _request_json_no_body(self, url: str, *, timeout: int):
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": self._auth_header(),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8", errors="ignore"))

    def _request_bytes(self, url: str, method: str, body: bytes, content_type: str, *, timeout: int) -> bytes:
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
            headers={
                "Authorization": self._auth_header(),
                "Content-Type": content_type,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()

    def _normalize_layer_ref(self, layer_name: str) -> str:
        value = layer_name.strip()
        return value if ":" in value else f"{self.workspace}:{value}"

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.admin_user}:{self.admin_password}".encode("ascii")).decode("ascii")
        return f"Basic {token}"


geoserver_service = GeoServerService()
