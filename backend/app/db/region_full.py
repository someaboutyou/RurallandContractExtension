"""全国行政区划数据包（region_full.zip）读取与子树抽取。

数据包由 scripts/fetch_region_seed.py --full 在构建机上生成、随程序包分发
（setup_cython.py COPY_FILES 拷进 dist）。目标机**不联网**也能初始化区域：
部署人在 .env 配 REGION_SEED_COUNTIES（6 位码，支持县级/市级/省级，见
build_county_items docstring），bootstrap 时从中抽子树，
由 init_db.ensure_default_regions「缺则补」插入。

编码转换规则（与 fetch_region_seed.py 的 build() 保持一致，改动必须两处同步）：
  - 省 2 位码补 0000（32 -> 320000）
  - 市 4 位码补 00（3213 -> 321300，是县码的真前缀；省码不是市/县码前缀）
  - 直辖市（京/津/沪/渝）省下直挂县，不落「市辖区」节点
  - 村级按 12 位码前 9 位（镇码）归组
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path

REGION_FULL_FILE = Path(__file__).with_name("region_full.zip")
REGION_CENTROIDS_FILE = Path(__file__).with_name("region_centroids.json")

MUNICIPALITIES = {"11", "12", "31", "50"}  # 京/津/沪/渝 的 2 位省码


def load_centroids() -> dict[str, list[float]]:
    """全国省/市/县三级行政区划中心点表（region_centroids.json，随包分发）。

    返回 {code: [lng, lat]}；文件缺失/损坏返回空 dict（调用方自行降级）。
    数据由 scripts/fetch_region_centroids.py 从阿里 DataV GeoAtlas 抓取生成。
    """
    if not REGION_CENTROIDS_FILE.exists():
        return {}
    try:
        data = json.loads(REGION_CENTROIDS_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[seed] 警告：区划中心点文件读取失败：{REGION_CENTROIDS_FILE} ({exc})")
        return {}
    return data if isinstance(data, dict) else {}


def parse_county_codes(raw: str | list[str] | None) -> list[str]:
    """把 .env 里的 REGION_SEED_COUNTIES（'150502, 150521' 之类）解析成 6 位码列表。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace("，", ",").replace("、", ",").replace(";", ",").replace("；", ",").split(",")
    else:
        parts = list(raw)
    codes: list[str] = []
    for part in parts:
        code = (part or "").strip()
        if len(code) == 6 and code.isdigit() and code not in codes:
            codes.append(code)
    return codes


def build_county_items(county_codes: list[str]) -> list[dict] | None:
    """从 region_full.zip 抽出配置码覆盖的完整子树。

    配置码支持三种粒度（与 install.ps1 提示一致）：
      - 县级码（6 位，如 150502）→ 该县子树
      - 市级码（6 位末两位 00，如 150500）→ 全市所有县子树
      - 省级码（6 位前两位+0000，如 150000）→ 全省（慎用，量大）
    返回与 region_seed.json 的 regions 同构的 list[dict]（name/code/level/full_name/parent_code）；
    数据包缺失返回 None；配置码在数据里找不到时跳过并打印告警。
    """
    if not county_codes:
        return None
    if not REGION_FULL_FILE.exists():
        return None

    wanted = set(county_codes)
    unmatched = set(wanted)
    items: list[dict] = []
    seen: set[str] = set()

    def push(name: str, code: str, level: str, full_name: str, parent_code: str | None) -> None:
        if code in seen:
            return
        seen.add(code)
        items.append(
            {
                "name": name,
                "code": code,
                "level": level,
                "full_name": full_name,
                "parent_code": parent_code,
            }
        )

    with zipfile.ZipFile(REGION_FULL_FILE) as zf:
        divisions = json.loads(zf.read("divisions.json").decode("utf-8"))

        # 第一遍：把市/省码展开成县级码集合
        counties: set[str] = set()
        for province in divisions:
            p_code2 = province["code"]
            p_code = f"{p_code2}0000"
            province_hit = p_code in wanted
            for city in province.get("children") or []:
                c_code = f"{city['code']}00"
                city_hit = province_hit or c_code in wanted
                for area in city.get("children") or []:
                    a_code = area["code"]
                    if a_code in wanted or city_hit:
                        counties.add(a_code)
                        unmatched.discard(a_code)
                        unmatched.discard(c_code)
                        unmatched.discard(p_code)
        if unmatched:
            print(f"[seed] 警告：REGION_SEED_COUNTIES 里这些码不在数据包中，已跳过：{sorted(unmatched)}")
        if not counties:
            return None

        # 村级（12 位）按前 9 位镇码归组；先按县前缀过滤，避免整表入内存
        county_prefixes = {c[:6] for c in counties}
        villages_by_town: dict[str, list[dict]] = {}
        reader = csv.DictReader(io.TextIOWrapper(zf.open("villages.csv"), encoding="utf-8"))
        for row in reader:
            code = (row.get("code") or "").strip()
            name = (row.get("name") or "").strip()
            street = (row.get("streetCode") or "").strip()
            if not code or not name or not street or street[:6] not in county_prefixes:
                continue
            villages_by_town.setdefault(street, []).append({"code": code, "name": name})

        # 第二遍：按展开后的县级码建条目
        for province in divisions:
            p_code2 = province["code"]
            p_code = f"{p_code2}0000"
            p_name = province["name"]
            is_municipality = p_code2 in MUNICIPALITIES
            for city in province.get("children") or []:
                city_name = city["name"]
                for area in city.get("children") or []:
                    a_code = area["code"]
                    if a_code not in counties:
                        continue

                    push(p_name, p_code, "province", p_name, None)
                    if is_municipality:
                        county_full = f"{p_name} / {area['name']}"
                        county_parent = p_code
                    else:
                        c_code = f"{city['code']}00"
                        push(city_name, c_code, "city", f"{p_name} / {city_name}", p_code)
                        county_full = f"{p_name} / {city_name} / {area['name']}"
                        county_parent = c_code
                    push(area["name"], a_code, "county", county_full, county_parent)

                    for street in area.get("children") or []:
                        s_code = street["code"]
                        s_full = f"{county_full} / {street['name']}"
                        push(street["name"], s_code, "town", s_full, a_code)
                        for v in villages_by_town.get(s_code, []):
                            push(v["name"], v["code"], "village", f"{s_full} / {v['name']}", s_code)

    return items or None
