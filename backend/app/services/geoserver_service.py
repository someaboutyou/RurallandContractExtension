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

    def ensure_feature_type(self, layer_name: str) -> bool:
        """确保 featuretype/layer 存在；缺失时按同名 PostGIS 表自动创建。

        GeoServer 会自动从 geometry_columns 读取 SRID、从表数据计算 bbox，
        无需调用方传投影参数。返回 True 表示本次实际执行了创建。
        """
        layer_ref = self._normalize_layer_ref(layer_name)
        native_name = layer_ref.split(":", 1)[-1]
        ft_url = (
            f"{self.base_url}/rest/workspaces/{self.workspace}/datastores/{self.store_name}"
            f"/featuretypes/{native_name}.json"
        )
        try:
            self._request_json_no_body(ft_url, timeout=10)
            return False  # 已存在
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise

        # 发布被跳过过的典型场景：GeoServer 启动时几何表还没有数据/不存在。
        # 用表元数据创建，SRS/bbox 由 GeoServer 自行解析。
        self._request_json(
            f"{self.base_url}/rest/workspaces/{self.workspace}/datastores/{self.store_name}/featuretypes.json",
            "POST",
            {"featureType": {"name": native_name, "nativeName": native_name, "enabled": True}},
            timeout=20,
        )
        # 图层默认样式：与 start-geoserver.ps1 一致，每层用同名工作区样式（样式早已上传）。
        try:
            layer_url = f"{self.base_url}/rest/layers/{urllib.parse.quote(layer_ref, safe='')}.json"
            layer_json = self._request_json_no_body(layer_url, timeout=10)
            layer = layer_json.get("layer") or {}
            layer["defaultStyle"] = {"name": layer_ref}
            self._request_json(layer_url, "PUT", {"layer": layer}, timeout=10)
        except Exception as exc:  # noqa: BLE001 —— 样式设置失败不回滚发布
            logger.warning("GeoServer default style not set: layer=%s error=%s", layer_ref, exc)
        logger.info("GeoServer feature type created: %s", layer_ref)
        return True

    def truncate_tile_cache(self, layer_name: str) -> None:
        """清空该层的 GWC 瓦片缓存（幂等、秒级）。

        导入新数据后，旧范围内已缓存的瓦片不会自动失效（expireCache=0），
        与其重切片不如直接清空 —— GWC 会在请求时按需重绘。
        """
        layer_ref = self._normalize_layer_ref(layer_name)
        url = f"{self.base_url}/gwc/rest/seed/{urllib.parse.quote(layer_ref, safe='')}.json"
        payload = {
            "seedRequest": {
                "name": layer_ref,
                "gridSetId": "EPSG:4326",
                "type": "truncate",
                "format": "image/png",
                # ⛔ GWC 对 truncate 同样要求 zoom 区间，缺了直接 NPE 500
                # （SeedRequest.getZoomStart() is null，2026-10-22 实测）
                "zoomStart": 0,
                "zoomStop": 20,
                "threadCount": 4,
            }
        }
        self._request_json(url, "POST", payload, timeout=20)
        logger.info("GeoServer tile cache truncated: %s", layer_ref)

    def is_running(self) -> bool:
        """探活：只要服务端返回了 HTTP 响应就算在跑（含 302/401）。

        ⛔ 不能用 /web/ 200 判活 —— 它会 302 到登录页，urllib 抛异常会被误判
        成"未启动"（2026-10-22 实测）。连接类错误（拒绝/超时）才算未启动。
        """
        try:
            request = urllib.request.Request(
                f"{self.base_url}/web/", headers={"Authorization": self._auth_header()}
            )
            with urllib.request.urlopen(request, timeout=3):
                return True
        except urllib.error.HTTPError:
            return True  # 服务端有响应（302/401 等），实例在跑
        except Exception:  # noqa: BLE001 —— 连接拒绝/超时 = 未启动
            return False

    def refresh_after_data_change(self) -> dict:
        """数据导入后的图层自愈（幂等，逐层容错）。

        每个默认图层执行四步：
        ① ensure_feature_type —— 发布被跳过的补发布；
        ② recalculate bounds —— bbox 按最新数据重算；
        ③ ensure_tile_layer —— gridSubset 固定为全幅 EPSG:4326，避免退化范围导致 TileOutOfRange；
        ④ truncate 瓦片缓存 —— 旧瓦片作废，WMTS 按需重绘。
        GeoServer 未启动时整体跳过，不抛错（调用方是导入收口，不能阻断导入）。
        """
        result: dict = {"geoserverRunning": False, "layers": {}}
        if not self.is_running():
            logger.info("GeoServer not running; skip layer refresh")
            return result
        result["geoserverRunning"] = True
        for layer_name in self.default_layers:
            info: dict = {}
            try:
                info["created"] = self.ensure_feature_type(layer_name)
                info["boundsRecalculated"] = self.recalculate_feature_type_bounds(layer_name)
                self.ensure_tile_layer(layer_name)
                self.truncate_tile_cache(layer_name)
                info["ok"] = True
            except Exception as exc:  # noqa: BLE001 —— 单层失败不影响其余图层
                info["ok"] = False
                info["error"] = str(exc)
                logger.warning("GeoServer layer refresh failed: layer=%s error=%s", layer_name, exc)
            result["layers"][layer_name] = info
        logger.info("GeoServer layer refresh finished: %s", json.dumps(result, ensure_ascii=False))
        return result


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

    def get_seed_task_status(self, layer_name: str) -> dict:
        """查询图层的切片缓存种子任务运行状态。

        GWC REST：GET /gwc/rest/seed/{layer}.json 返回 long-array-array，
        每行是一个拆分后的子任务：[已完成切片数, 总切片数, 保留位, 任务ID, 线程状态]，
        空数组表示当前没有任务在跑（2026-10-21 实测：一次 seed 请求按 threadCount
        拆成多个子任务，各行的已完成数独立增长，总数相同为整个请求的切片总量）。
        """
        layer_ref = self._normalize_layer_ref(layer_name)
        url = f"{self.base_url}/gwc/rest/seed/{urllib.parse.quote(layer_ref, safe='')}.json"
        empty = {"running": False, "tasks": [], "tilesDone": 0, "tilesTotal": 0, "progress": 0.0, "layerName": layer_ref}
        try:
            data = self._request_json_no_body(url, timeout=10)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return empty
            raise
        rows = data.get("long-array-array") or []
        tasks: list[dict] = []
        tiles_done = 0
        tiles_total = 0
        for row in rows:
            try:
                row_done = max(0, int(row[0])) if len(row) > 0 else 0
                row_total = int(row[1]) if len(row) > 1 else 0
                task_id = int(row[3]) if len(row) > 3 else 0
            except (TypeError, ValueError):
                continue
            if row_total <= 0:
                continue
            tiles_done += row_done
            tiles_total = max(tiles_total, row_total)
            tasks.append({"taskId": task_id, "tilesDone": row_done, "tilesTotal": row_total})
        if not tasks:
            return empty
        progress = round(min(tiles_done * 100.0 / tiles_total, 99.9), 1) if tiles_total > 0 else 0.0
        return {
            "running": True,
            "tasks": tasks,
            "tilesDone": tiles_done,
            "tilesTotal": tiles_total,
            "progress": progress,
            "layerName": layer_ref,
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
            from app.paths import PROJECT_ROOT

            data_dir = str(PROJECT_ROOT / "runtime" / "data" / "geoserver-data")
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
