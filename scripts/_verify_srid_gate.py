# -*- coding: utf-8 -*-
"""坐标系收口（TARGET_SRID）离线验收。

覆盖四层：
  L1 单元：crs.py 白名单 / 带号换算 / crs_to_epsg / describe_mismatch
  L2 静态：后端源码不再有硬编码 4527（白名单内的例外逐个核对）
  L3 落库：upgrade_schema 真跑 —— system_config 固化 + 启动校验（篡改 env 必须拒启）
  L4 数据：geometry_columns 里调查成果/基础空间表的 SRID 与固化值一致

用法：runtime/windows/python/python.exe scripts/_verify_srid_gate.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── 先注入环境变量再 import app（老规矩）──────────────────────────────────
runtime_env = ROOT / "runtime" / ".state" / "runtime.env"
if runtime_env.exists():
    for line in runtime_env.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
os.environ.setdefault("TARGET_SRID", "4527")

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok), detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" | {detail}" if detail else ""))


# ═══ L1 crs.py 单元 ═══════════════════════════════════════════════════
sys.path.insert(0, str(ROOT / "backend"))

from app.core.crs import (  # noqa: E402
    SUPPORTED_TARGET_SRIDS,
    crs_to_epsg,
    describe_mismatch,
    get_target_srid,
    is_supported_srid,
    srid_central_meridian,
    srid_display_name,
    srid_y_zone_prefix,
    srid_zone,
)

check("白名单 = CGCS2000 3°带 4513..4533 共 21 个",
      sorted(SUPPORTED_TARGET_SRIDS) == list(range(4513, 4534)))

check("4527 → 39 带 / 117E / 前缀 39",
      srid_zone(4527) == 39 and srid_central_meridian(4527) == 117.0
      and srid_y_zone_prefix(4527) == "39",
      srid_display_name(4527))

check("4513/4533 边界带号 25/45，4512/4534 不支持",
      srid_zone(4513) == 25 and srid_zone(4533) == 45
      and not is_supported_srid(4512) and not is_supported_srid(4534))

from pyproj import CRS  # noqa: E402

check("crs_to_epsg：pyproj CRS 4528 可解析",
      crs_to_epsg(CRS.from_epsg(4528)) == 4528)
check("crs_to_epsg：WKT dict（fiona 读 GDB 常见形态）可解析",
      crs_to_epsg({"wkt": CRS.from_epsg(4527).to_wkt()}) == 4527)
check("crs_to_epsg：标准 proj4（a/rf 椭球）可解析",
      crs_to_epsg({"proj": "tmerc", "lat_0": 0, "lon_0": 117, "k": 1,
                   "x_0": 39500000, "y_0": 0, "a": 6378137.0,
                   "rf": 298.257222101, "units": "m", "no_defs": True}) == 4527)
check("crs_to_epsg：不规范椭球名（ellps=CGCS2000）→ None（闸门拒收，不猜带）",
      crs_to_epsg({"proj": "tmerc", "lon_0": 117, "x_0": 39500000,
                   "ellps": "CGCS2000", "units": "m"}) is None)
check("crs_to_epsg：None / 垃圾输入 → None（不抛异常）",
      crs_to_epsg(None) is None and crs_to_epsg({"foo": "bar"}) is None)

check("describe_mismatch：错带文案点名双方坐标系并给出处置指引",
      "4528" in describe_mismatch(4528, 4527) and "拒绝导入" in describe_mismatch(4528, 4527)
      and "无法识别" in describe_mismatch(None, 4527))

check("config 默认值 = 4527（env 未设时现网兼容）", get_target_srid() == 4527)

# ═══ L2 静态扫描：后端源码无游离的 4527 ════════════════════════════════
# 允许清单：crs.py 是定义点、config.py 是 env 默认值 —— 它们就是 4527 的合法出处
ALLOWED_FILES = {"crs.py", "config.py"}
backend_src = ROOT / "backend" / "app"
stray: list[str] = []
for py in backend_src.rglob("*.py"):
    if py.name in ALLOWED_FILES:
        continue
    in_doc = False  # 跳过 docstring / 块注释内容
    for lineno, line in enumerate(
        py.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1
    ):
        stripped = line.strip()
        if in_doc:
            if stripped.count('"""') >= 1:
                in_doc = False
            continue
        if stripped.startswith('"""'):
            in_doc = not (stripped.count('"""') >= 2)
            continue
        if "4527" in stripped:
            code_part = line.split("#")[0]
            if "4527" in code_part:
                stray.append(f"{py.relative_to(backend_src)}:{lineno}: {stripped[:90]}")
check("backend/app 代码行无硬编码 4527（定义点与注释除外）", not stray, "; ".join(stray[:4]))

# ═══ L3 落库：固化 + 启动校验 ══════════════════════════════════════════
import app.main  # noqa: E402,F401  —— 完整 import 图（含 progress/boundary/nyt2539）
from app.db.migrations import _upgrade_system_config, upgrade_schema, TARGET_SRID  # noqa: E402
from app.db.session import engine  # noqa: E402

check("migrations.TARGET_SRID 来自 env", TARGET_SRID == int(os.environ.get("TARGET_SRID", "4527")))

upgrade_schema(engine)  # 幂等，真跑一遍（含建 system_config / 固化）

from sqlalchemy import text  # noqa: E402

with engine.begin() as conn:
    locked = conn.exec_driver_sql(
        "SELECT value FROM system_config WHERE key = 'target_srid'"
    ).scalar()
check("system_config.target_srid 已固化且与 env 一致", locked is not None and int(locked) == TARGET_SRID,
      f"locked={locked}")

# 篡改 env 侧（模拟运维改了 .env）→ 必须拒绝启动
import app.db.migrations as mig  # noqa: E402

original = mig.TARGET_SRID
try:
    mig.TARGET_SRID = original + 1
    try:
        _upgrade_system_config(engine)
        check("固化校验：env 改成别的带号必须拒启", False, "未抛 RuntimeError")
    except RuntimeError as exc:
        msg = str(exc)
        check("固化校验：env 改成别的带号必须拒启",
              "拒绝启动" in msg and str(original) in msg and str(original + 1) in msg,
              msg.split("。")[0][:80])
finally:
    mig.TARGET_SRID = original
_upgrade_system_config(engine)  # 复原后再跑应正常
check("固化校验：复原后可正常通过", True)

# ═══ L4 geometry_columns 实测 ═════════════════════════════════════════
with engine.begin() as conn:
    rows = conn.exec_driver_sql(
        "SELECT f_table_name, f_geometry_column, srid, type FROM geometry_columns "
        "WHERE f_table_name IN ('survey_dk_result','czkfbj','dltb','gdbhmb','xzq','xzqjx','yjjbntbhtb','stbhhx') "
        "ORDER BY f_table_name"
    ).fetchall()
srid_map = {(r[0], r[1]): int(r[2]) for r in rows}
for table, col in (("survey_dk_result", "geom"), ("czkfbj", "Shape"), ("dltb", "Shape"),
                   ("gdbhmb", "Shape"), ("xzq", "SHAPE"), ("xzqjx", "SHAPE"), ("yjjbntbhtb", "Shape")):
    got = srid_map.get((table, col))
    check(f"{table}.{col} SRID == {TARGET_SRID}", got == TARGET_SRID, f"got={got}")
stbh = srid_map.get(("stbhhx", "Shape"))
check("stbhhx.Shape 保持 4490（地理坐标系底图例外）", stbh == 4490, f"got={stbh}")

# ── 汇总 ──────────────────────────────────────────────────────────────
failed = [name for name, ok, _ in _results if not ok]
print()
print(f"TOTAL={len(_results)} PASS={len(_results) - len(failed)} FAIL={len(failed)}")
if failed:
    print("FAILED:", " | ".join(failed))
    sys.exit(1)
print("ALL OK")
