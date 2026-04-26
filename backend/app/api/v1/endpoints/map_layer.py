from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models.user import User
from app.schemas.map_layer import MapLayerCreate, MapLayerRead, MapLayerUpdate
from app.schemas.response import ApiResponse
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
