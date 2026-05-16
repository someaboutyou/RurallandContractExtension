from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.models.map_layer import MapLayer
from app.schemas.map_layer import MapLayerCreate, MapLayerRead, MapLayerUpdate
from app.schemas.response import ApiResponse
from app.services.geoserver_service import geoserver_service
from app.services.map_layer_service import map_layer_service

router = APIRouter()


@router.get("", response_model=ApiResponse[list[MapLayerRead]])
def list_map_layers(
    category: str | None = Query(default=None),
    enabled_only: bool = Query(default=False, alias="enabledOnly"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.view")),
):
    return {"data": map_layer_service.list_layers(db, category=category, enabled_only=enabled_only)}


@router.get("/validate", response_model=ApiResponse[dict])
def validate_map_layer_service(
    service_url: str = Query(alias="serviceUrl", min_length=1),
    layer_type: str = Query(alias="layerType", min_length=1),
    _: User = Depends(require_permission("layers.manage")),
):
    url = service_url.strip()
    layer_kind = layer_type.strip().upper()

    if url.startswith("/"):
        return {"data": {"ok": True, "message": "本地相对地址可直接作为系统内资源使用。"}}

    if layer_kind == "OSM":
        return {"data": {"ok": True, "message": "OSM 底图类型已通过规则校验。"}}

    if layer_kind == "XYZ" and not all(token in url for token in ("{z}", "{x}", "{y}")):
        return {"data": {"ok": False, "message": "XYZ 服务地址缺少 {z}/{x}/{y} 占位符。"}}

    if not url.lower().startswith(("http://", "https://")):
        return {"data": {"ok": False, "message": "服务地址必须以 http:// 或 https:// 开头。"}}

    if layer_kind in {"WMS", "WMTS", "WFS"}:
        parts = urlsplit(url)
        params = {"service": layer_kind, "request": "GetCapabilities"}
        if layer_kind == "WMS":
            params["version"] = "1.1.1"
        if layer_kind == "WMTS":
            params["version"] = "1.0.0"
        capability_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
        try:
            request = Request(capability_url, headers={"User-Agent": "RuralLandPlatform/1.0"})
            with urlopen(request, timeout=8) as response:
                content = response.read(300).decode("utf-8", errors="ignore")
                if "Capabilities" in content:
                    return {"data": {"ok": True, "message": f"{layer_kind} GetCapabilities 校验通过。"}}
                return {"data": {"ok": True, "message": f"{layer_kind} 地址可访问，但返回内容不是标准能力文档。"}}
        except HTTPError as exc:
            return {"data": {"ok": False, "message": f"{layer_kind} 能力文档访问失败，状态码 {exc.code}。"}}
        except URLError as exc:
            return {"data": {"ok": False, "message": f"{layer_kind} 能力文档不可访问：{exc.reason}"}}

    try:
        request = Request(url, method="HEAD", headers={"User-Agent": "RuralLandPlatform/1.0"})
        with urlopen(request, timeout=6) as response:
            return {"data": {"ok": True, "message": f"地址可访问，状态码 {response.status}。"}}
    except HTTPError as exc:
        return {"data": {"ok": False, "message": f"地址返回异常状态码 {exc.code}。"}}
    except URLError as exc:
        return {"data": {"ok": False, "message": f"地址不可访问：{exc.reason}"}}


@router.get("/geoserver-layers", response_model=ApiResponse[list[dict]])
def list_geoserver_layers(
    geoserver_url: str = Query(default="/geoserver", alias="geoserverUrl"),
    service_type: str = Query(default="WMS", alias="serviceType"),
    workspace: str | None = Query(default=None),
    _: User = Depends(require_permission("layers.view")),
):
    """从 GeoServer 获取可用的图层列表（WMS / WMTS）。

    调用 GeoServer 的 GetCapabilities 接口，解析返回的 XML，
    提取图层名称、标题、坐标参考系等信息返回给前端用于图层选择。
    """
    base_url = geoserver_url.strip().rstrip("/")
    if base_url.startswith("/"):
        base_url = f"http://localhost:8080{base_url}"

    layer_kind = service_type.strip().upper()
    if layer_kind not in {"WMS", "WMTS"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的服务类型：{layer_kind}，仅支持 WMS 和 WMTS。",
        )

    # 构建 GetCapabilities 请求 URL
    parts = urlsplit(base_url)
    if layer_kind == "WMS":
        params = {"service": "WMS", "version": "1.1.1", "request": "GetCapabilities"}
        capability_path = f"{parts.path.rstrip('/')}/wms"
    else:
        params = {"service": "WMTS", "version": "1.0.0", "request": "GetCapabilities"}
        capability_path = f"{parts.path.rstrip('/')}/gwc/service/wmts"

    capability_url = urlunsplit((parts.scheme, parts.netloc, capability_path, urlencode(params), ""))
    if workspace:
        capability_url = urlunsplit(
            (parts.scheme, parts.netloc, f"{parts.path.rstrip('/')}/{workspace}/wms", urlencode(params), ""),
        )

    try:
        request = Request(capability_url, headers={"User-Agent": "RuralLandPlatform/1.0"})
        with urlopen(request, timeout=15) as response:
            raw_xml = response.read().decode("utf-8", errors="ignore")
    except HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GeoServer 返回错误状态码 {exc.code}。",
        ) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"无法连接 GeoServer：{exc.reason}",
        ) from exc

    layers = _parse_get_capabilities_layers(raw_xml, layer_kind, workspace)
    return {"data": layers}


@router.post("/geoserver/recalculate-bbox", response_model=ApiResponse[dict])
def recalculate_all_geoserver_bbox(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.manage")),
):
    rows = db.scalars(select(MapLayer).where(MapLayer.category == "vector", MapLayer.enabled.is_(True))).all()
    updated = []
    skipped = []
    for row in rows:
        layer_name = _resolve_geoserver_layer_name(row)
        if not layer_name:
            skipped.append(row.key)
            continue
        if geoserver_service.recalculate_feature_type_bounds(layer_name):
            updated.append(layer_name)
        else:
            skipped.append(layer_name)
    return {"data": {"updated": updated, "skipped": skipped, "updatedCount": len(updated), "skippedCount": len(skipped)}}


@router.post("/geoserver/seed-cache", response_model=ApiResponse[dict])
def seed_geoserver_tile_cache_by_url(
    payload: dict = Body(default_factory=dict),
    _: User = Depends(require_permission("layers.manage")),
):
    service_url = str(payload.get("serviceUrl") or "")
    layer_name = _resolve_geoserver_layer_name_from_url(service_url)
    if not layer_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无法从服务地址识别 GeoServer 图层名")

    try:
        result = geoserver_service.seed_tile_cache(
            layer_name,
            grid_set_id=str(payload.get("gridSetId") or "EPSG:4326"),
            zoom_start=int(payload.get("zoomStart", 0)),
            zoom_stop=int(payload.get("zoomStop", 15)),
            mime_format=str(payload.get("format") or "image/png"),
            seed_type=str(payload.get("type") or "reseed"),
            thread_count=int(payload.get("threadCount", 2)),
            bounds=_normalize_bounds(payload.get("bounds")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except HTTPError as exc:
        detail = _read_http_error_detail(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GeoServer 缓存任务创建失败，状态码 {exc.code}。{detail}") from exc
    except URLError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"无法连接 GeoServer：{exc.reason}") from exc

    return {"data": result}


@router.post("/{layer_id}/geoserver/recalculate-bbox", response_model=ApiResponse[dict])
def recalculate_geoserver_bbox(
    layer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.manage")),
):
    layer = db.get(MapLayer, layer_id)
    if layer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图层不存在")
    layer_name = _resolve_geoserver_layer_name(layer)
    if not layer_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无法从图层服务地址识别 GeoServer 图层名")
    if not geoserver_service.recalculate_feature_type_bounds(layer_name):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GeoServer bbox 重新计算失败")
    return {"data": {"layerName": geoserver_service._normalize_layer_ref(layer_name), "message": "bbox 已重新计算"}}


@router.post("/{layer_id}/geoserver/seed-cache", response_model=ApiResponse[dict])
def seed_geoserver_tile_cache(
    layer_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.manage")),
):
    layer = db.get(MapLayer, layer_id)
    if layer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图层不存在")
    layer_name = _resolve_geoserver_layer_name(layer)
    if not layer_name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无法从图层服务地址识别 GeoServer 图层名")

    try:
        result = geoserver_service.seed_tile_cache(
            layer_name,
            grid_set_id=str(payload.get("gridSetId") or "EPSG:4326"),
            zoom_start=int(payload.get("zoomStart", 0)),
            zoom_stop=int(payload.get("zoomStop", 15)),
            mime_format=str(payload.get("format") or "image/png"),
            seed_type=str(payload.get("type") or "reseed"),
            thread_count=int(payload.get("threadCount", 2)),
            bounds=_normalize_bounds(payload.get("bounds")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except HTTPError as exc:
        detail = _read_http_error_detail(exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"GeoServer 缓存任务创建失败，状态码 {exc.code}。{detail}") from exc
    except URLError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"无法连接 GeoServer：{exc.reason}") from exc

    return {"data": result}


def _resolve_geoserver_layer_name(layer: MapLayer) -> str | None:
    for config in map_layer_service._deserialize_service_configs(layer):
        service_url = config.get("serviceUrl") or ""
        service_type = (config.get("serviceType") or "").upper()
        if service_type not in {"WMS", "WMTS"} and "/geoserver/" not in service_url:
            continue
        layer_name = _resolve_geoserver_layer_name_from_url(service_url)
        if layer_name:
            return layer_name
    if layer.group_name and "GeoServer" in layer.group_name:
        return layer.key
    if layer.key in geoserver_service.default_layers:
        return layer.key
    return None


def _resolve_geoserver_layer_name_from_url(service_url: str) -> str | None:
    parsed = urlsplit(service_url)
    params = parse_qs(parsed.query)
    candidates = params.get("layers") or params.get("LAYERS") or params.get("layer") or params.get("LAYER")
    if candidates and candidates[0]:
        return candidates[0]
    return None


def _read_http_error_detail(exc: HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="ignore")[:500].strip()
    except Exception:
        return ""


def _normalize_bounds(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = [value.get("minx"), value.get("miny"), value.get("maxx"), value.get("maxy")]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("invalid bounds")
    numbers = [float(item) for item in value]
    if numbers[0] >= numbers[2] or numbers[1] >= numbers[3]:
        raise ValueError("invalid bounds")
    return numbers


def _parse_get_capabilities_layers(xml_text: str, layer_kind: str, workspace: str | None) -> list[dict]:
    """解析 GetCapabilities XML 响应，提取图层信息。

    支持多种 GeoServer 返回格式：
    - WMS 1.1.1（无命名空间）
    - WMS 1.3.0（默认命名空间 http://www.opengis.net/wms）
    - WMTS（命名空间 http://www.opengis.net/wmts/1.0 + ows 命名空间）

    策略：忽略 XML 命名空间，递归查找所有 <Layer> 元素，
    从中提取 <Name>（或 <Identifier>）和 <Title>。
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []

    if layer_kind == "WMS":
        return _parse_wms_layers(root, workspace)
    return _parse_wmts_layers(root, workspace)


def _strip_ns(tag: str) -> str:
    """去掉命名空间 URI 前缀，只返回本地标签名。"""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _find_all_layers(element):
    """递归查找所有 <Layer> 元素，忽略命名空间。"""
    result = []
    if _strip_ns(element.tag) == "Layer":
        result.append(element)
    for child in element:
        result.extend(_find_all_layers(child))
    return result


def _first_text(el, *tag_names):
    """从元素中查找第一个匹配标签的文本内容，忽略命名空间。"""
    for child in el:
        if _strip_ns(child.tag) in tag_names:
            return (child.text or "").strip()
    return ""


def _parse_wms_layers(root, workspace):
    """解析 WMS GetCapabilities 响应中的图层。

    策略：不依赖特定的 XML 路径结构，直接递归查找所有 <Layer> 元素，
    然后从每个 <Layer> 中提取 <Name> 和 <Title>。
    """
    # 查找所有 Layer 元素
    all_layers = _find_all_layers(root)
    if not all_layers:
        return []

    layers = []
    for layer_el in all_layers:
        name = _first_text(layer_el, "Name")
        if not name:
            continue
        title = _first_text(layer_el, "Title")
        if workspace and not name.startswith(f"{workspace}:"):
            continue
        layers.append({
            "name": name,
            "title": title,
            "workspace": name.split(":")[0] if ":" in name else "",
        })

    return layers


def _parse_wmts_layers(root, workspace):
    """解析 WMTS GetCapabilities 响应中的图层。"""
    # 递归查找所有 Layer 元素
    all_layers = _find_all_layers(root)
    if not all_layers:
        return []

    layers = []
    for layer_el in all_layers:
        ident = _first_text(layer_el, "Identifier")
        if not ident:
            continue
        title = _first_text(layer_el, "Title")
        if workspace and not ident.startswith(f"{workspace}:"):
            continue
        layers.append({
            "name": ident,
            "title": title,
            "workspace": ident.split(":")[0] if ":" in ident else "",
        })

    return layers


@router.post("", response_model=ApiResponse[MapLayerRead], status_code=status.HTTP_201_CREATED)
def create_map_layer(
    payload: MapLayerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.manage")),
):
    try:
        return {"data": map_layer_service.create_layer(db, payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.put("/{layer_id}", response_model=ApiResponse[MapLayerRead])
def update_map_layer(
    layer_id: int,
    payload: MapLayerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.manage")),
):
    try:
        return {"data": map_layer_service.update_layer(db, layer_id, payload.model_dump())}
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "layer not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete("/{layer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_map_layer(
    layer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("layers.manage")),
):
    try:
        map_layer_service.delete_layer(db, layer_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
