#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取全国 省/市/县 三级行政区划中心点坐标，生成随程序包分发的 centroid 表。

用法（解释器任选，纯标准库）：
  runtime/windows/python/python.exe scripts/fetch_region_centroids.py

数据源：阿里 DataV GeoAtlas（geo.datav.aliyun.com/areas_v3，民政部区划边界）。
每个 adcode 的 FeatureCollection 里 Feature.properties 自带：
  centroid  质心（优先采用）
  center    几何中心（centroid 缺失时兜底）
抓取路径：100000_full（省级）→ {省}_full（市级+省直辖县级）→ {市}_full（县级），
共约 370 个请求；响应缓存在 runtime/.state/region_centroid_cache/，重复跑不重复下载。

输出：backend/app/db/region_centroids.json
  {"320000": [118.75, 32.06], ...} —— 6 位国标码 -> [lng, lat]，约 3200 条（~120KB）。
消费方：backend/app/db/region_full.py::load_centroids -> 部署初始化时按
REGION_SEED_COUNTIES 计算 system_config.map_center（地图默认中心点）。

坐标说明：DataV 数据为常用在线底图坐标系，质心精度为区县级（数百米级），
仅用于地图默认定位；业务数据的精确定位仍走 GeoServer 图层 bbox fit。
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / ".state" / "region_centroid_cache"
DEFAULT_OUT = ROOT / "backend" / "app" / "db" / "region_centroids.json"
FULL_URL = "https://geo.datav.aliyun.com/areas_v3/bound/{}_full.json"


def fetch_full(code: str) -> dict:
    cache = CACHE_DIR / f"{code}.json"
    if cache.exists() and cache.stat().st_size > 200:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    last_exc: Exception | None = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(FULL_URL.format(code), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                # 台湾/港澳等在 DataV 无下级数据：按"无子级"处理，缓存空结果避免重复请求
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache.write_text("{}", encoding="utf-8")
                return {}
            last_exc = exc
            time.sleep(1 + attempt)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1 + attempt)
    raise SystemExit(f"抓取 {code} 失败（重试 4 次）：{last_exc}")


def point_of(props: dict) -> list[float] | None:
    for key in ("centroid", "center"):
        val = props.get(key)
        if isinstance(val, (list, tuple)) and len(val) == 2 and all(isinstance(v, (int, float)) for v in val):
            return [round(float(val[0]), 6), round(float(val[1]), 6)]
    return None


def collect(data: dict, centroids: dict, level: str | None = None) -> list[dict]:
    """把一份 _full 响应里的区划点收进 centroids，返回收到的 feature 列表。"""
    feats = (data or {}).get("features") or []
    kept = []
    for feat in feats:
        props = feat.get("properties") or {}
        code = str(props.get("adcode") or "")
        if len(code) != 6 or not code.isdigit() or code == "-99":
            continue
        if level and props.get("level") != level:
            continue
        point = point_of(props)
        if point:
            centroids[code] = point
            kept.append(props)
    return kept


def main() -> None:
    centroids: dict[str, list[float]] = {}

    # 1) 省级（100000_full 的 children 即省/直辖市/特区）
    provinces = collect(fetch_full("100000"), centroids)
    print(f"provinces: {len(provinces)}")

    # 2) 市级 + 省直辖县级（{省}_full 的 children）
    city_codes: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for props_list in pool.map(lambda p: collect(fetch_full(p["adcode"]), centroids), provinces):
            for props in props_list:
                if props.get("level") == "city" and (props.get("childrenNum") or 0) > 0:
                    city_codes.append(str(props["adcode"]))
    print(f"cities + direct counties recorded; city nodes to expand: {len(city_codes)}")

    # 3) 县级（{市}_full 的 children，level == district）
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        for _ in pool.map(lambda c: collect(fetch_full(c), centroids, level="district"), city_codes):
            done += 1
            if done % 50 == 0:
                print(f"  city files done: {done}/{len(city_codes)}")

    by_prefix = {2: 0, 4: 0, 6: 0}
    for code in centroids:
        if code.endswith("0000"):
            by_prefix[2] += 1
        elif code.endswith("00"):
            by_prefix[4] += 1
        else:
            by_prefix[6] += 1
    print(f"total: {len(centroids)}  provinces={by_prefix[2]} cities={by_prefix[4]} counties={by_prefix[6]}")
    if by_prefix[6] < 2700:
        print("警告：县级条目明显偏少（正常 ~2850），请检查抓取日志", file=sys.stderr)

    DEFAULT_OUT.write_text(json.dumps(centroids, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"written: {DEFAULT_OUT} ({DEFAULT_OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
