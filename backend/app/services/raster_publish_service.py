"""
影像发布服务
功能：验证tif、裁剪tif、发布到GeoServer、创建底图记录
"""

import logging
import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

import fiona
import rasterio
from rasterio.mask import mask as rasterio_mask
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

from app.services.geoserver_service import geoserver_service

logger = logging.getLogger(__name__)

# 任务进度存储（内存中）
_tasks: dict[str, dict[str, Any]] = {}


class RasterPublishService:
    """影像发布服务"""

    def __init__(self):
        self.geoserver_data_dir = os.getenv(
            "GEOSERVER_DATA_DIR",
            str(Path(__file__).resolve().parents[3] / "runtime" / "data" / "geoserver-data")
        )
        self.temp_dir = str(Path(__file__).resolve().parents[3] / "runtime" / "temp" / "raster-publish")
        os.makedirs(self.temp_dir, exist_ok=True)

    def validate_tif(self, tif_path: str) -> dict[str, Any]:
        """验证tif文件是否存在并读取元数据"""
        tif_path = os.path.normpath(tif_path)
        if not os.path.exists(tif_path):
            raise FileNotFoundError(f"文件不存在: {tif_path}")
        if not tif_path.lower().endswith(('.tif', '.tiff')):
            raise ValueError("文件不是TIFF格式")
        try:
            with rasterio.open(tif_path) as src:
                pixel_size_x = abs(src.transform.a)
                pixel_size_y = abs(src.transform.e)
                if src.crs and src.crs.is_geographic:
                    pixel_size_x *= 111320
                    pixel_size_y *= 111320 * math.cos(math.radians(src.bounds.bottom))
                avg_pixel_size = (pixel_size_x + pixel_size_y) / 2
                min_zoom, max_zoom = self._calc_zoom_range(avg_pixel_size)
                return {
                    "exists": True,
                    "path": tif_path,
                    "filename": os.path.basename(tif_path),
                    "size_mb": round(os.path.getsize(tif_path) / (1024 * 1024), 2),
                    "width": src.width,
                    "height": src.height,
                    "bands": src.count,
                    "dtype": str(src.dtypes[0]),
                    "crs": str(src.crs) if src.crs else "未知",
                    "bounds": {
                        "left": src.bounds.left,
                        "bottom": src.bounds.bottom,
                        "right": src.bounds.right,
                        "top": src.bounds.top
                    },
                    "bounds_wgs84": self._transform_bounds_to_wgs84(
                        src.bounds.left, src.bounds.bottom,
                        src.bounds.right, src.bounds.top,
                        src.crs
                    ),
                    "pixel_size": {
                        "x": round(pixel_size_x, 4),
                        "y": round(pixel_size_y, 4)
                    },
                    "suggested_zoom": {"min": min_zoom, "max": max_zoom}
                }
        except rasterio.RasterioIOError as e:
            raise ValueError(f"无法读取TIFF文件: {str(e)}")

    def parse_shp_zip(self, zip_path: str) -> dict[str, Any]:
        """解析上传的shp压缩包，提取范围GeoJSON"""
        import zipfile
        extract_dir = os.path.join(self.temp_dir, f"shp_{uuid.uuid4().hex[:8]}")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            shp_files = list(Path(extract_dir).glob("**/*.shp"))
            if not shp_files:
                raise ValueError("压缩包中未找到.shp文件")
            return self._extract_shp_geometry(str(shp_files[0]))
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    def _extract_shp_geometry(self, shp_path: str) -> dict[str, Any]:
        """从shapefile提取几何信息"""
        try:
            with fiona.open(shp_path, "r") as src:
                if src.crs is None:
                    raise ValueError("SHP文件缺少坐标系信息")
                geometries = [shape(f['geometry']) for f in src]
                if not geometries:
                    raise ValueError("SHP文件中没有几何要素")
                merged = unary_union(geometries)
                geojson = mapping(merged)
                bounds = merged.bounds
                return {
                    "geojson": geojson,
                    "bounds": {"left": bounds[0], "bottom": bounds[1], "right": bounds[2], "top": bounds[3]},
                    "crs": str(src.crs),
                    "feature_count": len(geometries)
                }
        except fiona.DriverError as e:
            raise ValueError(f"无法读取SHP文件: {str(e)}")

    def clip_raster(self, tif_path: str, geojson: dict, output_path: str | None = None) -> str:
        """使用GeoJSON裁剪tif"""
        if output_path is None:
            output_path = os.path.join(self.temp_dir, f"clipped_{uuid.uuid4().hex[:8]}.tif")
        try:
            with rasterio.open(tif_path) as src:
                # 如果tif是投影坐标系，需要将WGS84 GeoJSON转换为tif的坐标系
                geojson_for_clip = geojson
                if src.crs and not src.crs.is_geographic:
                    geojson_for_clip = self._reproject_geojson(geojson, src.crs)
                
                out_image, out_transform = rasterio_mask(
                    src, [geojson_for_clip], crop=True,
                    nodata=src.nodata if src.nodata is not None else 0
                )
                out_meta = src.meta.copy()
                out_meta.update({
                    "driver": "GTiff",
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform,
                    "compress": "lzw"
                })
                with rasterio.open(output_path, "w", **out_meta) as dest:
                    dest.write(out_image)
            logger.info("Raster clipped: %s -> %s", tif_path, output_path)
            return output_path
        except Exception as e:
            logger.error("Raster clip failed: %s", str(e))
            raise ValueError(f"裁剪失败: {str(e)}")

    def publish_raster(self, task_id: str, tif_path: str, clip_geojson: dict | None = None,
                       workspace: str | None = None, store_name: str | None = None) -> dict[str, Any]:
        """发布tif到GeoServer"""
        workspace = workspace or geoserver_service.workspace
        publish_tif_path = tif_path
        try:
            self._update_progress(task_id, 10, "正在验证TIFF文件...")
            tif_info = self.validate_tif(tif_path)

            if clip_geojson:
                self._update_progress(task_id, 20, "正在裁剪影像...")
                publish_tif_path = self.clip_raster(tif_path, clip_geojson)
                self._update_progress(task_id, 40, "裁剪完成")
            else:
                self._update_progress(task_id, 40, "跳过裁剪（未提供裁剪范围）")

            if not store_name:
                store_name = Path(tif_path).stem
                store_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in store_name)

            self._update_progress(task_id, 45, "正在准备GeoServer数据目录...")
            coverage_dir = os.path.join(self.geoserver_data_dir, "workspaces", workspace, store_name)
            os.makedirs(coverage_dir, exist_ok=True)
            dest_tif_path = os.path.join(coverage_dir, f"{store_name}.tif")
            
            # 复制并修复坐标系（如果需要）
            self._copy_and_fix_crs(publish_tif_path, dest_tif_path)
            self._update_progress(task_id, 50, "数据已复制到GeoServer目录")

            self._update_progress(task_id, 55, "正在创建GeoServer CoverageStore...")
            self._create_coveragestore_and_coverage(workspace, store_name, dest_tif_path)
            self._update_progress(task_id, 70, "Coverage发布成功")

            avg_pixel_size = (tif_info['pixel_size']['x'] + tif_info['pixel_size']['y']) / 2
            min_zoom, max_zoom = self._calc_zoom_range(avg_pixel_size)
            layer_name = f"{workspace}:{store_name}"
            grid_set_id = "EPSG:4326"

            self._update_progress(task_id, 75, f"正在创建切片缓存（级别{min_zoom}-{max_zoom}）...")
            geoserver_service.ensure_tile_layer(layer_name, grid_set_id=grid_set_id)
            
            # 设置GWC层的正确extent
            bounds_wgs84 = tif_info.get('bounds_wgs84') or tif_info.get('bounds')
            if bounds_wgs84:
                self._update_gwc_extent(layer_name, bounds_wgs84)
            
            wmts_url = None
            try:
                result = geoserver_service.seed_tile_cache(bounds=bounds_wgs84 and [
                    bounds_wgs84['left'], bounds_wgs84['bottom'],
                    bounds_wgs84['right'], bounds_wgs84['top']
                ] if bounds_wgs84 else None,
                    layer_name=layer_name, grid_set_id=grid_set_id,
                    zoom_start=min_zoom, zoom_stop=max_zoom,
                    seed_type="reseed", thread_count=2
                )
                wmts_url = result.get("wmtsUrl")
            except Exception as e:
                logger.warning("Tile seed failed (non-critical): %s", str(e))
            self._update_progress(task_id, 90, "切片缓存已提交")

            wms_url = f"/geoserver/wms?service=WMS&version=1.1.1&request=GetMap&layers={layer_name}&styles=&format=image/png&transparent=true"
            if not wmts_url:
                wmts_url = geoserver_service.build_wmts_url(layer_name, grid_set_id=grid_set_id)

            self._update_progress(task_id, 100, "发布完成！")
            return {
                "success": True,
                "layer_name": layer_name,
                "store_name": store_name,
                "workspace": workspace,
                "wms_url": wms_url,
                "wmts_url": wmts_url,
                "zoom_range": {"min": min_zoom, "max": max_zoom},
                "tif_info": tif_info,
                "clipped": clip_geojson is not None
            }
        except Exception as e:
            logger.error("Raster publish failed: %s", str(e))
            self._update_progress(task_id, -1, f"发布失败: {str(e)}")
            raise
        finally:
            if clip_geojson and publish_tif_path != tif_path:
                try:
                    os.remove(publish_tif_path)
                except:
                    pass

    def _create_coveragestore_and_coverage(self, workspace: str, store_name: str, tif_path: str):
        """通过GeoServer REST API创建CoverageStore和Coverage"""
        import json
        import urllib.request
        import urllib.error

        base_url = geoserver_service.base_url.rstrip("/")
        auth = geoserver_service._auth_header()

        coveragestore_data = {
            "coverageStore": {
                "name": store_name,
                "workspace": workspace,
                "type": "GeoTIFF",
                "enabled": True,
                "url": f"file:workspaces/{workspace}/{store_name}/{store_name}.tif"
            }
        }
        req = urllib.request.Request(
            f"{base_url}/rest/workspaces/{workspace}/coveragestores.json",
            data=json.dumps(coveragestore_data).encode("utf-8"),
            method="POST",
            headers={"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                logger.info("CoverageStore created: %s:%s", workspace, store_name)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                logger.info("CoverageStore already exists: %s:%s", workspace, store_name)
            else:
                body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
                # 如果是已存在，继续执行
                if "already exists" in body:
                    logger.info("CoverageStore already exists, continuing: %s:%s", workspace, store_name)
                else:
                    raise ValueError(f"创建CoverageStore失败: HTTP {e.code} {body}")

        coverage_data = {
            "coverage": {
                "name": store_name,
                "nativeName": store_name,
                "title": store_name,
                "enabled": True
            }
        }
        req = urllib.request.Request(
            f"{base_url}/rest/workspaces/{workspace}/coveragestores/{store_name}/coverages.json",
            data=json.dumps(coverage_data).encode("utf-8"),
            method="POST",
            headers={"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                logger.info("Coverage created: %s:%s", workspace, store_name)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
            if e.code == 409 or "already exists" in body:
                logger.info("Coverage already exists, continuing: %s:%s", workspace, store_name)
            else:
                raise ValueError(f"创建Coverage失败: HTTP {e.code} {body}")

    def _update_gwc_extent(self, layer_name: str, bounds: dict):
        """更新GWC层的extent配置"""
        import urllib.request
        import urllib.error
        import urllib.parse
        
        try:
            base_url = geoserver_service.base_url.rstrip("/")
            auth = geoserver_service._auth_header()
            
            gwc_xml = (
                '<GeoServerLayer>'
                '<name>' + layer_name + '</name>'
                '<enabled>true</enabled>'
                '<mimeFormats><string>image/png</string></mimeFormats>'
                '<gridSubsets><gridSubset>'
                '<gridSetName>EPSG:4326</gridSetName>'
                '<extent><coords>'
                '<double>' + str(bounds['left']) + '</double>'
                '<double>' + str(bounds['bottom']) + '</double>'
                '<double>' + str(bounds['right']) + '</double>'
                '<double>' + str(bounds['top']) + '</double>'
                '</coords></extent>'
                '</gridSubset></gridSubsets>'
                '<metaWidthHeight><int>4</int><int>4</int></metaWidthHeight>'
                '<expireCache>0</expireCache><expireClients>0</expireClients>'
                '<parameterFilters/><gutter>0</gutter><cacheWarningSkips/>'
                '</GeoServerLayer>'
            )
            
            url = base_url + '/gwc/rest/layers/' + urllib.parse.quote(layer_name, safe=':') + '.xml'
            req = urllib.request.Request(
                url,
                data=gwc_xml.encode('utf-8'),
                method='PUT',
                headers={'Authorization': auth, 'Content-Type': 'text/xml', 'Accept': 'application/xml'}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                logger.info('GWC extent updated for %s', layer_name)
        except Exception as e:
            logger.warning('Failed to update GWC extent: %s', str(e))

    def _copy_and_fix_crs(self, src_path: str, dest_path: str):
        """复制tif并修复坐标系（将LOCAL_CS转换为标准PROJCS）"""
        import shutil
        try:
            with rasterio.open(src_path) as src:
                crs = src.crs
                need_fix = crs and "LOCAL_CS" in str(crs)
                
                if need_fix:
                    logger.info("Detected LOCAL_CS, fixing CRS for %s", src_path)
                    data = src.read()
                    meta = src.meta.copy()
                    
                    # CGCS2000 / 3-degree Gauss-Kruger zone 39 WKT
                    wkt = (
                        'PROJCS["CGCS2000 / 3-degree Gauss-Kruger zone 39",'
                        'GEOGCS["China Geodetic Coordinate System 2000",'
                        'DATUM["China_2000",'
                        'SPHEROID["CGCS2000",6378137,298.257222101]],'
                        'PRIMEM["Greenwich",0],'
                        'UNIT["degree",0.0174532925199433]],'
                        'PROJECTION["Transverse_Mercator"],'
                        'PARAMETER["latitude_of_origin",0],'
                        'PARAMETER["central_meridian",117],'
                        'PARAMETER["scale_factor",1],'
                        'PARAMETER["false_easting",39500000],'
                        'PARAMETER["false_northing",0],'
                        'UNIT["metre",1],'
                        'AXIS["Easting",EAST],'
                        'AXIS["Northing",NORTH]]'
                    )
                    meta["crs"] = CRS.from_wkt(wkt)
                    
                    with rasterio.open(dest_path, "w", **meta) as dest:
                        dest.write(data)
                    
                    logger.info("Fixed CRS to PROJCS for %s", dest_path)
                    return
            
            # 不需要修复，直接复制
            shutil.copy2(src_path, dest_path)
        except Exception as e:
            logger.warning("Failed to fix CRS, copying as-is: %s", str(e))
            shutil.copy2(src_path, dest_path)

    def _guess_epsg_from_bounds(self, bounds) -> int | None:
        """根据坐标范围推断EPSG代码"""
        easting = bounds.left
        
        # 如果Easting > 1000000，可能包含带号
        if easting > 1000000:
            # 去掉带号
            zone = int(easting / 1000000)
            easting = easting - zone * 1000000
        
        # CGCS2000 3度带范围（去掉带号后）
        # 36带: 106.5-109.5度 -> Easting 约 500000
        # 37带: 109.5-112.5度 -> Easting 约 500000
        # 38带: 112.5-115.5度 -> Easting 约 500000
        # 39带: 115.5-118.5度 -> Easting 约 500000
        # 40带: 118.5-121.5度 -> Easting 约 500000
        
        # 根据带号推断EPSG
        if 36 <= zone <= 44:
            return 4508 + zone  # 4544对应36带，4547对应39带
        
        return None
    def _reproject_geojson(self, geojson: dict, target_crs) -> dict:
        """将GeoJSON从WGS84转换为目标CRS"""
        try:
            from pyproj import CRS, Transformer
            
            epsg = target_crs.to_epsg() if target_crs else None
            if not epsg:
                epsg = 4547
            
            target = CRS.from_epsg(epsg)
            transformer = Transformer.from_crs("EPSG:4326", target, always_xy=True)
            
            def transform_coord(x, y):
                new_x, new_y = transformer.transform(x, y)
                # 对于3度带投影，需要添加带号
                # 带号 = round((中央经线) / 3)，中央经线 = 带号 * 3
                # 对于EPSG:4547 (39带)，中央经线是117度
                if epsg and 4539 <= epsg <= 4555:  # CGCS2000 3度带范围
                    zone = epsg - 4508  # 4547对应39带: 4547-4508=39
                    new_x = new_x + zone * 1000000
                return new_x, new_y
            
            coords = geojson.get("coordinates", [])
            if geojson.get("type") == "Polygon":
                new_coords = []
                for ring in coords:
                    new_ring = []
                    for x, y in ring:
                        new_x, new_y = transform_coord(x, y)
                        new_ring.append([new_x, new_y])
                    new_coords.append(new_ring)
                return {"type": "Polygon", "coordinates": new_coords}
            elif geojson.get("type") == "MultiPolygon":
                new_coords = []
                for polygon in coords:
                    new_polygon = []
                    for ring in polygon:
                        new_ring = []
                        for x, y in ring:
                            new_x, new_y = transform_coord(x, y)
                            new_ring.append([new_x, new_y])
                        new_polygon.append(new_ring)
                    new_coords.append(new_polygon)
                return {"type": "MultiPolygon", "coordinates": new_coords}
            else:
                return geojson
        except Exception as e:
            logger.warning("Failed to reproject GeoJSON: %s", str(e))
            return geojson
    def _transform_bounds_to_wgs84(self, left, bottom, right, top, src_crs):
        """Transform bounds from source CRS to WGS84"""
        if src_crs is None:
            return None
        try:
            if src_crs.is_geographic:
                return {"left": left, "bottom": bottom, "right": right, "top": top}
            
            # 尝试从WKT创建CRS（处理LOCAL_CS等情况）
            try:
                src_crs_obj = CRS.from_wkt(src_crs.to_wkt())
            except:
                src_crs_obj = src_crs
            
            # 尝试找对应的EPSG代码
            epsg = src_crs_obj.to_epsg()
            if epsg:
                src_for_transform = CRS.from_epsg(epsg)
            else:
                # 对于 CGCS2000 3度带39带，EPSG是4547
                src_for_transform = CRS.from_epsg(4547)
            
            transformer = Transformer.from_crs(src_for_transform, "EPSG:4326", always_xy=True)
            
            # 处理带号：如果Easting > 1000000，可能包含带号
            # 对于3度带，带号 = (中央经线 - 1.5) / 3
            if left > 1000000:
                # 计算带号（假设是3度带）
                zone = int(left / 1000000)
                left_adj = left - zone * 1000000
                right_adj = right - zone * 1000000
            else:
                left_adj = left
                right_adj = right
            
            lon1, lat1 = transformer.transform(left_adj, bottom)
            lon2, lat2 = transformer.transform(right_adj, top)
            return {
                "left": round(min(lon1, lon2), 6),
                "bottom": round(min(lat1, lat2), 6),
                "right": round(max(lon1, lon2), 6),
                "top": round(max(lat1, lat2), 6)
            }
        except Exception as e:
            logger.warning("Failed to transform bounds to WGS84: %s", str(e))
            return None

    def _calc_zoom_range(self, pixel_size_meters: float) -> tuple[int, int]:
        """根据分辨率计算切片级别范围"""
        if pixel_size_meters <= 0:
            return 0, 18
        max_zoom = max(0, min(18, int(math.log2(156543.03 / pixel_size_meters))))
        min_zoom = max(0, max_zoom - 6)
        return min_zoom, max_zoom

    def _update_progress(self, task_id: str, progress: int, message: str):
        """更新任务进度"""
        if task_id in _tasks:
            _tasks[task_id].update({
                "progress": progress,
                "message": message,
                "status": "failed" if progress < 0 else ("completed" if progress >= 100 else "running")
            })
            logger.info("Task %s: %d%% - %s", task_id, progress, message)

    def create_task(self) -> str:
        """创建新任务"""
        task_id = uuid.uuid4().hex
        _tasks[task_id] = {
            "id": task_id,
            "progress": 0,
            "message": "等待开始...",
            "status": "pending",
            "result": None
        }
        return task_id

    def get_task_progress(self, task_id: str) -> dict[str, Any] | None:
        """获取任务进度"""
        return _tasks.get(task_id)

    def set_task_result(self, task_id: str, result: dict[str, Any]):
        """设置任务结果"""
        if task_id in _tasks:
            _tasks[task_id]["result"] = result


raster_publish_service = RasterPublishService()
















