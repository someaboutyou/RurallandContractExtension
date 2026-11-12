"""验证：权属单位代码表导入的区域「相对名」改造 + 导出回环 + 伪组清理。

背景（2026-11-11 扎鲁特旗巨日合数据）：
  1. 导入侧区域名称曾存代码表全名（「内蒙古省通辽市扎鲁特旗巨日合镇」），
     区域树层层重复 → 改为存相对名（「巨日合镇」「双山子村村民委员会」），
     原始全名存 regions.qs_full_name，导出时按它还原（回环一致）。
  2. 村级发包方（fbfbm 14 位以 00 结尾）曾被误建为 level=group 区域行，
     导出权属单位代码表时与村行补零撞码 → 每个村民委员会两行且名称不同。
     写入侧已跳过 + 迁移清理存量 + 导出侧排除兜底。
  3. 导出文件名对齐源包「<县码><年份>权属单位代码表.xls」。

验证项：
  A. compute_relative_names 纯函数：县/镇/村相对名与全名保留；
  B. sync_regions_from_qs_table（事务内、回滚）：相对名落库、qs_full_name、
     full_name 链、rename 计数；
  C. build_qs_rows_from_regions：无补零撞码、无伪组、名称为全名、镇级范围
     自动补县行；
  D. 迁移 _cleanup_pseudo_group_regions + qs_full_name 回填（真实执行，幂等）。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_qs_region_names.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "runtime" / ".state" / "runtime.env"
# 原始导入包里的代码表（县码 + 年份命名）
SOURCE_XLS = ROOT / "datas" / "巨日合(1)" / "权属数据" / "1505262019权属单位代码表.xls"
COUNTY_CODE = "150526"
TOWN_CODE = "150526103"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" | {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def load_env() -> None:
    if not ENV_PATH.exists():
        sys.exit(f"缺少运行时环境文件：{ENV_PATH}")
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
    os.environ.setdefault("DATABASE_PORT", "15432")


def main() -> int:
    load_env()
    sys.path.insert(0, str(ROOT / "backend"))
    import app.main  # noqa: F401 注册全部模型
    from app.db.session import SessionLocal, engine
    from sqlalchemy import select

    from app.db.migrations import _cleanup_pseudo_group_regions, upgrade_schema
    from app.models.region import Region
    from app.services.data_import.qs_code_table import (
        build_qs_rows_from_regions,
        compute_relative_names,
        read_qs_code_table,
        sync_regions_from_qs_table,
    )

    rows = read_qs_code_table(SOURCE_XLS)
    check("A0 读取原表行数=29（县+镇+27村）", len(rows) == 29, f"实际 {len(rows)}")

    # 加列/回填/伪组清理与后端启动同路径（幂等），先补齐新列再查库
    upgrade_schema(engine)

    # ---- A. 纯函数：相对名计算 ----
    computed = compute_relative_names(rows, scope_prefix=COUNTY_CODE)
    check("A1 县相对名=扎鲁特旗", computed[COUNTY_CODE]["relative"] == "扎鲁特旗",
          computed[COUNTY_CODE]["relative"])
    check("A2 县全名保留", computed[COUNTY_CODE]["full"] == "内蒙古省通辽市扎鲁特旗",
          computed[COUNTY_CODE]["full"])
    check("A3 镇相对名=巨日合镇", computed[TOWN_CODE]["relative"] == "巨日合镇",
          computed[TOWN_CODE]["relative"])
    village_code = "150526103201"
    check("A4 村相对名=双山子村村民委员会",
          computed[village_code]["relative"] == "双山子村村民委员会",
          computed[village_code]["relative"])
    check("A5 村全名保留",
          computed[village_code]["full"] == "内蒙古省通辽市扎鲁特旗巨日合镇双山子村村民委员会",
          computed[village_code]["full"])

    # ---- B/C. 事务内同步 + 导出（结束回滚，不落库）----
    db = SessionLocal()
    try:
        stats = sync_regions_from_qs_table(db, rows, COUNTY_CODE)
        check("B1 applied=29", stats["applied"] == 29, str(stats))

        county = db.scalar(select(Region).where(Region.code == COUNTY_CODE))
        town = db.scalar(select(Region).where(Region.code == TOWN_CODE))
        village = db.scalar(select(Region).where(Region.code == village_code))
        check("B2 县 name=扎鲁特旗", county is not None and county.name == "扎鲁特旗",
              county.name if county else "缺失")
        check("B3 县 qs_full_name=内蒙古省通辽市扎鲁特旗",
              county is not None and county.qs_full_name == "内蒙古省通辽市扎鲁特旗",
              str(county.qs_full_name if county else None))
        check("B4 镇 name=巨日合镇", town is not None and town.name == "巨日合镇",
              town.name if town else "缺失")
        check("B5 镇 full_name 链含相对名",
              town is not None and town.full_name.endswith("/ 巨日合镇"),
              town.full_name if town else "缺失")
        check("B6 村 name=双山子村村民委员会",
              village is not None and village.name == "双山子村村民委员会",
              village.name if village else "缺失")
        check("B7 村 full_name 链",
              village is not None
              and village.full_name.endswith("/ 巨日合镇 / 双山子村村民委员会"),
              village.full_name if village else "缺失")

        # 县级范围导出：29 行、无撞码、名称=全名
        county_rows = build_qs_rows_from_regions(db, COUNTY_CODE)
        padded = [c for c, _ in county_rows]
        check("C1 县级导出行数=29", len(county_rows) == 29, str(len(county_rows)))
        check("C2 无补零撞码", len(padded) == len(set(padded)))
        check("C3 首行=县全名", county_rows[0] == ("15052600000000", "内蒙古省通辽市扎鲁特旗"),
              str(county_rows[0]))
        target = ("15052610320100", "内蒙古省通辽市扎鲁特旗巨日合镇双山子村村民委员会")
        check("C4 村行导出全名且唯一", target in county_rows and padded.count(target[0]) == 1)

        # 镇级范围导出：自动补县行 → 29 行
        town_rows = build_qs_rows_from_regions(db, TOWN_CODE)
        check("C5 镇级导出补县行=29 行", len(town_rows) == 29, str(len(town_rows)))
        check("C6 镇级导出含县行", town_rows[0] == ("15052600000000", "内蒙古省通辽市扎鲁特旗"),
              str(town_rows[0]))
    finally:
        db.rollback()
        db.close()
    print("（B/C 已在事务内验证并回滚，开发库数据未变）")

    # ---- D. 迁移：qs_full_name 回填 + 伪组清理（真实执行，幂等）----
    from app.db.session import engine
    from sqlalchemy import func

    _cleanup_pseudo_group_regions(engine)
    db2 = SessionLocal()
    try:
        pseudo = db2.scalar(
            select(func.count())
            .select_from(Region)
            .where(Region.level == "group", Region.code.like("_" * 12 + "00"))
        )
        check("D1 伪组行已清零", (pseudo or 0) == 0, f"剩余 {pseudo}")
        county2 = db.scalar(select(Region).where(Region.code == COUNTY_CODE))
        check("D2 存量县行 qs_full_name 已回填",
              county2 is not None and county2.qs_full_name == "内蒙古省通辽市扎鲁特旗",
              str(county2.qs_full_name if county2 else None))
        # 清理后导出（不依赖事务回滚的内存态）
        real_rows = build_qs_rows_from_regions(db2, TOWN_CODE)
        check("D3 清理后镇级导出=29 行无重复", len(real_rows) == 29, str(len(real_rows)))
    finally:
        db2.close()

    print()
    if FAILURES:
        print(f"共 {len(FAILURES)} 项失败：")
        for item in FAILURES:
            print(" -", item)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
