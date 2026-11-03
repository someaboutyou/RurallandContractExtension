"""从公开行政区划数据生成区域初始化种子文件（region_seed.json）。

数据源（内容同源：国家统计局「统计用区划代码」，modood/china-division 整理）：
  1. GitHub 直连 raw.githubusercontent.com/modood/Administrative-divisions-of-China（小文件可用，大文件易断）；
  2. 兜底：npmmirror 拉 china-division npm 包 tarball 解包（国内 CDN，快且稳）。

产出：backend/app/db/region_seed.json —— **全国 省 -> 市 -> 县(区/旗) 三级**，随程序包分发。
启动时 ensure_default_regions 按 .env 的 REGION_SEED_COUNTIES 从全国种子里抽取
配置码对应的省/市/县链路「缺则补」插入 regions 表（不覆盖、不删除）。

⚠️ 种子只到县级。镇/村/组三级不在种子里（公开数据也没有组级），由业务数据
导入完成后 sync_regions_from_business_codes 从发包方编码反推补齐（缺则补）。

用法（解释器任选，纯标准库）：
  runtime/windows/python/python.exe scripts/fetch_region_seed.py            # 生成全国三级种子
  runtime/windows/python/python.exe scripts/fetch_region_seed.py --full     # （遗留）生成 region_full.zip
  runtime/windows/python/python.exe scripts/fetch_region_seed.py --out path # 指定输出路径

说明：
  - 市码 = 4 位市码 + "00"（如 3213 -> 321300）。⚠️ 国标 6 位码是「省2+市2+县2」
    结构，县码**不是**市码的前缀扩展（"321324" 不以 "321300" 开头），真前缀链
    只从县开始；
  - 直辖市（京/津/沪/渝）省下直挂县，不落「市辖区」节点。
  - 原始数据缓存到 runtime/.state/region_fetch/，重复跑不重复下载。
"""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "runtime" / ".state" / "region_fetch"
DEFAULT_OUT = ROOT / "backend" / "app" / "db" / "region_seed.json"
FULL_OUT = ROOT / "backend" / "app" / "db" / "region_full.zip"

MUNICIPALITIES = {"11", "12", "31", "50"}  # 京/津/沪/渝 的 2 位省码

RAW_URL = "https://raw.githubusercontent.com/modood/Administrative-divisions-of-China/master/dist/{file}"
NPM_META = "https://registry.npmmirror.com/china-division/latest"

PCAS_FILE = "pcas-code.json"  # 省(2位)->市(4位)->县(6位)->镇(9位)


def _download(url: str, dest: Path) -> None:
    print(f"[get ] {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as fh:
        fh.write(resp.read())


def fetch(file: str) -> Path:
    """取回数据文件到缓存目录：GitHub 直连优先，失败则从 npm tarball 解包。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / file
    if target.exists() and target.stat().st_size > 0:
        print(f"[cache] {file} -> {target} ({target.stat().st_size} bytes)")
        return target

    errors: list[str] = []
    try:
        _download(RAW_URL.format(file=file), target)
        print(f"[ok  ] {target.stat().st_size} bytes (github)")
        return target
    except Exception as exc:  # noqa: BLE001
        errors.append(f"github 直连 {file}: {exc}")
        target.unlink(missing_ok=True)

    # 兜底：npmmirror tarball（稳定，但 24MB，解包后留缓存）
    try:
        meta = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(NPM_META, headers={"User-Agent": "Mozilla/5.0"}),
                timeout=60,
            ).read()
        )
        tarball_url = meta["dist"]["tarball"]
        tgz = CACHE_DIR / "china-division.tgz"
        if not (tgz.exists() and tgz.stat().st_size > 0):
            _download(tarball_url, tgz)
        with tarfile.open(tgz, "r:gz") as tf:
            member = tf.getmember(f"package/dist/{file}")
            data = tf.extractfile(member).read()
        target.write_bytes(data)
        print(f"[ok  ] {target.stat().st_size} bytes (npmmirror tarball)")
        return target
    except Exception as exc:  # noqa: BLE001
        errors.append(f"npmmirror tarball {file}: {exc}")
        target.unlink(missing_ok=True)

    raise SystemExit("下载失败：\n  " + "\n  ".join(errors))


def load(file: str):
    return json.loads(fetch(file).read_text(encoding="utf-8"))


def build_national() -> dict:
    """全国 省 -> 市 -> 县 三级区域种子（镇/村由业务导入反推，不入种子）。"""
    pcas = load(PCAS_FILE)

    regions: list[dict] = []
    seen: set[str] = set()

    def push(name: str, code: str, level: str, full_name: str, parent_code: str | None) -> None:
        if code in seen:
            return
        seen.add(code)
        regions.append(
            {
                "name": name,
                "code": code,
                "level": level,
                "full_name": full_name,
                "parent_code": parent_code,
            }
        )

    for province in pcas:
        p_code2 = province["code"]
        p_code = f"{p_code2}0000"
        p_name = province["name"]
        is_municipality = p_code2 in MUNICIPALITIES
        push(p_name, p_code, "province", p_name, None)

        for city in province.get("children") or []:
            city_name = city["name"]
            areas = city.get("children") or []
            if is_municipality:
                # 直辖市：省下直挂县，不落「市辖区」节点
                for area in areas:
                    push(
                        area["name"],
                        area["code"],
                        "county",
                        f"{p_name} / {area['name']}",
                        p_code,
                    )
                continue

            c_code = f"{city['code']}00"
            push(city_name, c_code, "city", f"{p_name} / {city_name}", p_code)
            for area in areas:
                push(
                    area["name"],
                    area["code"],
                    "county",
                    f"{p_name} / {city_name} / {area['name']}",
                    c_code,
                )

    if not regions:
        raise SystemExit("没有生成任何区域")

    return {
        "source": "modood/Administrative-divisions-of-China（国家统计局统计用区划代码 2023 版镜像）",
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "regions": regions,
    }


def build_full_zip(out: Path = FULL_OUT) -> Path:
    """（遗留）把全国 省->市->县->镇 树（divisions.json）+ 村级 CSV（villages.csv）
    打成一个 zip。新版初始化不再读取该包（种子只到县，镇村由业务导入反推），
    仅为旧版后端保留生成能力。
    """
    import zipfile

    pcas_path = fetch(PCAS_FILE)
    villages_path = fetch(VILLAGES_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(pcas_path, "divisions.json")
        zf.write(villages_path, "villages.csv")
    print(f"[done] {out} ({out.stat().st_size} bytes)")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full",
        action="store_true",
        help="（遗留）生成全国行政区划数据包 region_full.zip",
    )
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 JSON 路径")
    args = parser.parse_args()

    if args.full:
        build_full_zip()
        return

    payload = build_national()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    levels: dict[str, int] = {}
    for item in payload["regions"]:
        levels[item["level"]] = levels.get(item["level"], 0) + 1
    print(f"[done] {out}")
    print(f"[done] 共 {len(payload['regions'])} 条：{levels}")


if __name__ == "__main__":
    sys.exit(main())
