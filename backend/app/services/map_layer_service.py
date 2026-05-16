import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.map_layer import MapLayer

LAYER_NAME_FALLBACKS = {
    "image": "\u9065\u611f\u5e95\u56fe",
    "vector": "\u7535\u5b50\u5730\u56fe",
    "terrain": "\u5730\u5f62\u56fe",
    "contract_land": "\u627f\u5305\u5730\u5757",
    "issuer_boundary": "\u53d1\u5305\u65b9\u8303\u56f4",
    "contractor_distribution": "\u627f\u5305\u65b9\u5206\u5e03",
    "workflow_status": "\u6d41\u7a0b\u72b6\u6001",
    "issue_review": "\u95ee\u9898\u6838\u67e5",
    "survey_dk_result": "\u627f\u5305\u5730\u5757",
    "czkfbj": "\u6751\u5e84\u5f00\u53d1\u8fb9\u754c",
    "dltb": "\u5730\u7c7b\u56fe\u6591",
    "gdbhmb": "\u8015\u5730\u4fdd\u62a4\u76ee\u6807",
    "stbhhx": "\u751f\u6001\u4fdd\u62a4\u7ea2\u7ebf",
    "xzq": "\u884c\u653f\u533a",
    "xzqjx": "\u884c\u653f\u533a\u754c\u7ebf",
    "yjjbntbhtb": "\u6c38\u4e45\u57fa\u672c\u519c\u7530",
    "rural_land_layers": "\u8c03\u67e5\u5730\u5757\u56fe\u5c42\u7ec4",
}

LAYER_GROUP_FALLBACKS = {
    "image": "\u57fa\u7840\u5e95\u56fe",
    "vector": "\u57fa\u7840\u5e95\u56fe",
    "terrain": "\u57fa\u7840\u5e95\u56fe",
    "contract_land": "\u4e1a\u52a1\u4e13\u9898",
    "issuer_boundary": "\u4e1a\u52a1\u4e13\u9898",
    "contractor_distribution": "\u4e1a\u52a1\u4e13\u9898",
    "workflow_status": "\u4e1a\u52a1\u4e13\u9898",
    "issue_review": "\u4e1a\u52a1\u4e13\u9898",
    "survey_dk_result": "GeoServer\u56fe\u5c42",
    "czkfbj": "\u56fd\u571f\u7a7a\u95f4\u89c4\u5212",
    "dltb": "\u56fd\u571f\u7a7a\u95f4\u89c4\u5212",
    "gdbhmb": "\u56fd\u571f\u7a7a\u95f4\u89c4\u5212",
    "stbhhx": "\u56fd\u571f\u7a7a\u95f4\u89c4\u5212",
    "xzq": "\u884c\u653f\u533a\u5212",
    "xzqjx": "\u884c\u653f\u533a\u5212",
    "yjjbntbhtb": "\u56fd\u571f\u7a7a\u95f4\u89c4\u5212",
    "rural_land_layers": "GeoServer\u56fe\u5c42",
}


class MapLayerService:
    def list_layers(
        self,
        db: Session,
        *,
        category: str | None = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        stmt = select(MapLayer).order_by(
            MapLayer.category.asc(),
            func.coalesce(MapLayer.group_name, "").asc(),
            MapLayer.sort_order.asc(),
            MapLayer.id.asc(),
        )
        if category:
            stmt = stmt.where(MapLayer.category == category)
        if enabled_only:
            stmt = stmt.where(MapLayer.enabled.is_(True))
        rows = db.scalars(stmt).all()
        return [self._serialize(item) for item in rows]

    def create_layer(self, db: Session, payload: dict) -> dict:
        self._validate_unique_key(db, payload["key"])
        service_configs = self._normalize_service_configs(payload)
        primary_service = self._select_primary_service(service_configs)
        layer = MapLayer(
            name=payload["name"],
            key=payload["key"],
            category=payload["category"],
            group_name=payload.get("groupName"),
            layer_type=primary_service["serviceType"],
            service_config=json.dumps(service_configs, ensure_ascii=False),
            service_url=primary_service["serviceUrl"],
            projection=primary_service.get("projection"),
            default_visible=payload.get("defaultVisible", False),
            is_default=payload.get("isDefault", False),
            sort_order=payload.get("sortOrder", 0),
            enabled=payload.get("enabled", True),
        )
        if layer.is_default:
            self._clear_default_flag(db, layer.category)
        db.add(layer)
        db.commit()
        db.refresh(layer)
        return self._serialize(layer)

    def update_layer(self, db: Session, layer_id: int, payload: dict) -> dict:
        layer = db.get(MapLayer, layer_id)
        if layer is None:
            raise ValueError("layer not found")
        self._validate_unique_key(db, payload["key"], exclude_id=layer_id)
        if payload.get("isDefault", False):
            self._clear_default_flag(db, payload["category"], exclude_id=layer_id)

        service_configs = self._normalize_service_configs(payload)
        primary_service = self._select_primary_service(service_configs)

        layer.name = payload["name"]
        layer.key = payload["key"]
        layer.category = payload["category"]
        layer.group_name = payload.get("groupName")
        layer.layer_type = primary_service["serviceType"]
        layer.service_config = json.dumps(service_configs, ensure_ascii=False)
        layer.service_url = primary_service["serviceUrl"]
        layer.projection = primary_service.get("projection")
        layer.default_visible = payload.get("defaultVisible", False)
        layer.is_default = payload.get("isDefault", False)
        layer.sort_order = payload.get("sortOrder", 0)
        layer.enabled = payload.get("enabled", True)
        db.commit()
        db.refresh(layer)
        return self._serialize(layer)

    def delete_layer(self, db: Session, layer_id: int) -> None:
        layer = db.get(MapLayer, layer_id)
        if layer is None:
            raise ValueError("layer not found")
        db.delete(layer)
        db.commit()

    def _validate_unique_key(self, db: Session, key: str, *, exclude_id: int | None = None) -> None:
        stmt = select(MapLayer).where(MapLayer.key == key)
        row = db.scalars(stmt).first()
        if row is not None and row.id != exclude_id:
            raise ValueError("layer key already exists")

    def _clear_default_flag(self, db: Session, category: str, *, exclude_id: int | None = None) -> None:
        stmt = select(MapLayer).where(MapLayer.category == category, MapLayer.is_default.is_(True))
        for item in db.scalars(stmt).all():
            if exclude_id is not None and item.id == exclude_id:
                continue
            item.is_default = False

    def _normalize_service_configs(self, payload: dict) -> list[dict]:
        raw_configs = payload.get("serviceConfigs") or []
        if not raw_configs and payload.get("layerType") and payload.get("serviceUrl"):
            raw_configs = [
                {
                    "serviceType": payload["layerType"],
                    "serviceUrl": payload["serviceUrl"],
                    "projection": payload.get("projection"),
                    "minZoom": 0,
                    "maxZoom": 24,
                    "enabled": True,
                }
            ]

        normalized = []
        for item in raw_configs:
            service_url = self._normalize_service_url(item.get("serviceUrl"))
            normalized.append(
                {
                    "serviceType": item.get("serviceType"),
                    "serviceUrl": service_url,
                    "projection": item.get("projection"),
                    "minZoom": int(item.get("minZoom", 0)),
                    "maxZoom": int(item.get("maxZoom", 24)),
                    "enabled": bool(item.get("enabled", True)),
                }
            )
        if not normalized:
            raise ValueError("service config is required")
        return normalized

    def _select_primary_service(self, service_configs: list[dict]) -> dict:
        enabled_services = [item for item in service_configs if item.get("enabled", True)]
        return enabled_services[0] if enabled_services else service_configs[0]

    def _deserialize_service_configs(self, item: MapLayer) -> list[dict]:
        if item.service_config:
            try:
                rows = json.loads(item.service_config)
                if isinstance(rows, list) and rows:
                    return [self._normalize_service_config_item(row) for row in rows]
            except json.JSONDecodeError:
                pass
        return [
            self._normalize_service_config_item(
                {
                    "serviceType": item.layer_type,
                    "serviceUrl": item.service_url,
                    "projection": item.projection,
                    "minZoom": 0,
                    "maxZoom": 24,
                    "enabled": True,
                }
            )
        ]

    def _normalize_service_config_item(self, item: dict) -> dict:
        return {
            "serviceType": item.get("serviceType") or item.get("layerType") or "WMS",
            "serviceUrl": self._normalize_service_url(item.get("serviceUrl") or item.get("service_url") or ""),
            "projection": item.get("projection"),
            "minZoom": int(item.get("minZoom", item.get("min_zoom", 0)) or 0),
            "maxZoom": int(item.get("maxZoom", item.get("max_zoom", 24)) or 24),
            "enabled": bool(item.get("enabled", True)),
        }

    def _serialize(self, item: MapLayer) -> dict:
        display_name = self._normalize_display_name(item)
        display_group_name = self._normalize_group_name(item)
        service_configs = self._deserialize_service_configs(item)
        primary_service = self._select_primary_service(service_configs)
        service_types = []
        zoom_labels = []
        for config in service_configs:
            if config["serviceType"] not in service_types:
                service_types.append(config["serviceType"])
            zoom_labels.append(f'{config["serviceType"]}: {config["minZoom"]}-{config["maxZoom"]}')

        return {
            "id": item.id,
            "name": display_name,
            "key": item.key,
            "category": item.category,
            "groupName": display_group_name,
            "groupSortKey": f"{display_group_name or ''}:{item.sort_order:04d}",
            "layerType": primary_service["serviceType"],
            "serviceUrl": primary_service["serviceUrl"],
            "projection": primary_service.get("projection"),
            "defaultVisible": item.default_visible,
            "isDefault": item.is_default,
            "sortOrder": item.sort_order,
            "enabled": item.enabled,
            "serviceConfigs": service_configs,
            "serviceTypesSummary": " + ".join(service_types),
            "zoomSummary": " | ".join(zoom_labels),
        }

    def _normalize_service_url(self, service_url: str | None) -> str:
        value = (service_url or "").strip()
        if value.startswith(("http://localhost:8080/geoserver", "http://127.0.0.1:8080/geoserver")):
            prefix, _, suffix = value.partition("/geoserver")
            if prefix:
                return f"/geoserver{suffix}"
        return value

    def _normalize_display_name(self, item: MapLayer) -> str:
        value = (item.name or "").strip()
        if value and "?" not in value and "\u9378\ufe43\u6fa6" not in value:
            return value
        return LAYER_NAME_FALLBACKS.get(item.key, value or item.key)

    def _normalize_group_name(self, item: MapLayer) -> str | None:
        value = (item.group_name or "").strip()
        if value and "?" not in value and "\u9378\u30e6\u5133" not in value:
            return value
        return LAYER_GROUP_FALLBACKS.get(item.key, value or None)


map_layer_service = MapLayerService()
