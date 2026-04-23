class GISService:
    def get_status(self) -> dict:
        return {
            "enabled": False,
            "provider": None,
            "message": "预留给 OpenLayers / PostGIS / GeoServer 集成",
        }


gis_service = GISService()
