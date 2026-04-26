from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_LAYER_TYPES = {"GeoJSON", "WMS", "WMTS", "WFS", "XYZ", "OSM"}
ALLOWED_CATEGORIES = {"vector", "basemap"}


class MapLayerServiceConfig(BaseModel):
    serviceType: str = Field(min_length=1, max_length=32)
    serviceUrl: str = Field(min_length=1)
    projection: str | None = Field(default=None, max_length=32)
    minZoom: int = Field(default=0, ge=0, le=24)
    maxZoom: int = Field(default=24, ge=0, le=24)
    enabled: bool = True

    @field_validator("serviceType")
    @classmethod
    def validate_service_type(cls, value: str) -> str:
        if value not in ALLOWED_LAYER_TYPES:
            raise ValueError("invalid layer service type")
        return value

    @field_validator("projection", "serviceUrl")
    @classmethod
    def strip_value(cls, value: str | None):
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_service(self):
        service_url = self.serviceUrl or ""
        if self.maxZoom < self.minZoom:
            raise ValueError("service max zoom must be greater than or equal to min zoom")

        if self.serviceType == "OSM":
            return self

        if self.serviceType == "XYZ":
            if "{z}" not in service_url or "{x}" not in service_url or "{y}" not in service_url:
                raise ValueError("xyz service url must include {z}/{x}/{y}")
            return self

        if self.serviceType in {"WMS", "WMTS", "WFS"}:
            if not service_url.lower().startswith(("http://", "https://", "/")):
                raise ValueError("wms/wmts/wfs service url must be http(s) or relative path")
            return self

        if self.serviceType == "GeoJSON":
            if not (service_url.lower().endswith(".geojson") or service_url.lower().startswith(("http://", "https://", "/"))):
                raise ValueError("geojson service url must be a .geojson file or reachable url")
            return self

        return self


class MapLayerBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    key: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=16)
    groupName: str | None = Field(default=None, max_length=64)
    defaultVisible: bool = False
    isDefault: bool = False
    sortOrder: int = 0
    enabled: bool = True
    serviceConfigs: list[MapLayerServiceConfig] = Field(default_factory=list)

    # Legacy compatibility for existing callers and rows.
    layerType: str | None = Field(default=None, min_length=1, max_length=32)
    serviceUrl: str | None = Field(default=None, min_length=1)
    projection: str | None = Field(default=None, max_length=32)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_")
        if not normalized:
            raise ValueError("layer key cannot be empty")
        if not all(char.isalnum() or char in {"_", "-"} for char in normalized):
            raise ValueError("layer key only supports letters, numbers, underscores and hyphens")
        return normalized

    @field_validator("name", "groupName", "projection", "serviceUrl")
    @classmethod
    def strip_value(cls, value: str | None):
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in ALLOWED_CATEGORIES:
            raise ValueError("invalid layer category")
        return value

    @field_validator("sortOrder")
    @classmethod
    def validate_sort_order(cls, value: int) -> int:
        if value < 0:
            raise ValueError("sort order must be greater than or equal to 0")
        return value

    @model_validator(mode="after")
    def ensure_service_configs(self):
        if not self.serviceConfigs:
            if self.layerType and self.serviceUrl:
                self.serviceConfigs = [
                    MapLayerServiceConfig(
                        serviceType=self.layerType,
                        serviceUrl=self.serviceUrl,
                        projection=self.projection,
                    )
                ]
            else:
                raise ValueError("at least one service config is required")

        if self.category == "basemap" and any(service.serviceType in {"WMS", "WMTS", "WFS", "GeoJSON"} for service in self.serviceConfigs):
            return self
        return self


class MapLayerCreate(MapLayerBase):
    pass


class MapLayerUpdate(MapLayerBase):
    pass


class MapLayerRead(MapLayerBase):
    id: int
    serviceTypesSummary: str
    zoomSummary: str
