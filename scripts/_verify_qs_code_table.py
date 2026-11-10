# -*- coding: utf-8 -*-
"""验收：权属单位代码表（xls）↔ 区域管理 双向同步。

1. 码级判定：14 位补零码按尾零分级（县/镇/村/组）+ 裸码按长度定级；
2. 读表：真实样例 datas/321324泗洪县/权属数据/3213242017权属单位代码表.xls；
3. 写表：xlwt 写出 → xlrd 读回，逐行勾稽；
4. 定位：find_qs_code_table 在模拟包目录（权属数据/ 子目录）中命中；
5. 区域同步：sync_regions_from_qs_table 事务内跑真实库（结束回滚，不留痕），
   断言缺则补 + 名称以代码表为准覆盖 + full_name 链重算；
6. 导出：build_qs_rows_from_regions 按前缀取子树，补零码逐行可回溯。

用法：runtime/windows/python/python.exe scripts/_verify_qs_code_table.py
"""

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

import app.main  # noqa: F401,E402 — 注册全部 mapper
from sqlalchemy import select  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.region import Region  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.services.data_import.qs_code_table import (  # noqa: E402
    build_qs_rows_from_regions,
    classify_qs_code,
    find_qs_code_table,
    pad_region_code,
    read_qs_code_table,
    sync_regions_from_qs_table,
    write_qs_code_table,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


SAMPLE_XLS = ROOT / "datas" / "321324泗洪县" / "权属数据" / "3213242017权属单位代码表.xls"


def main() -> None:
    print("== 1. 码级判定 ==")
    cases = [
        ("32132400000000", ("county", "321324")),
        ("32132410000000", ("town", "321324100")),
        ("32132410002200", ("village", "321324100022")),
        ("32132410002201", ("group", "32132410002201")),
        ("32132410002210", ("group", "32132410002210")),
        ("321324", ("county", "321324")),
        ("321324100", ("town", "321324100")),
        ("321324100022", ("village", "321324100022")),
        ("abc", None),
        ("12345", None),
    ]
    for raw, expected in cases:
        got = classify_qs_code(raw)
        check(f"classify {raw!r}", got == expected, f"got={got}")

    check("pad_region_code 6位", pad_region_code("321324") == "32132400000000")
    check("pad_region_code 9位", pad_region_code("321324100") == "32132410000000")
    check("pad_region_code 14位", pad_region_code("32132410002201") == "32132410002201")

    print("== 2. 读真实样例 ==")
    assert SAMPLE_XLS.exists(), f"样例不存在：{SAMPLE_XLS}"
    rows = read_qs_code_table(SAMPLE_XLS)
    check("样例行数 = 13", len(rows) == 13, f"got={len(rows)}")
    check("首行 = 县 泗洪县", rows[0] == {"code": "321324", "name": "泗洪县"}, f"got={rows[0]}")
    check("组行名称", any(r["code"] == "32132410002201" and r["name"] == "泗洪县青阳镇宏伟居一组" for r in rows))

    print("== 3. 写表回读勾稽 ==")
    out_path = ROOT / "runtime" / ".state" / "_verify_qs_roundtrip.xls"
    try:
        written = write_qs_code_table(out_path, rows and [(r["code"], r["name"]) for r in rows])
        check("写出行数 = 13", written == 13)
        back = read_qs_code_table(out_path)
        check("回读行数 = 13", len(back) == 13, f"got={len(back)}")
        check("回读逐行一致", back == [{"code": c, "name": n} for c, n in ((r["code"], r["name"]) for r in rows)])
    finally:
        out_path.unlink(missing_ok=True)

    print("== 4. 包内定位 ==")
    fake_pkg = ROOT / "runtime" / ".state" / "_verify_qs_pkg"
    try:
        (fake_pkg / "权属数据").mkdir(parents=True, exist_ok=True)
        shutil.copy(SAMPLE_XLS, fake_pkg / "权属数据" / "3213242017权属单位代码表.xls")
        (fake_pkg / "权属数据" / "干扰.xls").write_bytes(b"not an xls")
        found = find_qs_code_table(fake_pkg)
        check("定位到代码表", found is not None and found.name == "3213242017权属单位代码表.xls", f"got={found}")
    finally:
        shutil.rmtree(fake_pkg, ignore_errors=True)
    check("无代码表返回 None", find_qs_code_table(ROOT / "scripts") is None)

    print("== 5. 区域同步（事务内，收尾回滚）==")
    db = SessionLocal()
    try:
        scope = "321324"
        before = {
            r.code: (r.name, r.level)
            for r in db.scalars(select(Region).where(Region.code.startswith(scope)))
        }
        stats = sync_regions_from_qs_table(db, rows, scope)
        check("applied = 13", stats["applied"] == 13, f"got={stats['applied']}")
        check("skipped = 0", stats["skipped"] == 0)

        county = db.query(Region).filter(Region.code == "321324").one_or_none()
        check("县级存在且名称=泗洪县", county is not None and county.name == "泗洪县")
        tenant = db.get(Tenant, "321324")
        check("县级租户缺则建", tenant is not None and tenant.name == "泗洪县", f"got={tenant}")
        town = db.query(Region).filter(Region.code == "321324100").one_or_none()
        check("镇级名称以代码表为准", town is not None and town.name == "泗洪县青阳镇")
        village = db.query(Region).filter(Region.code == "321324100022").one_or_none()
        check("村级名称以代码表为准", village is not None and village.name == "泗洪县青阳镇宏伟居")
        group = db.query(Region).filter(Region.code == "32132410002201").one_or_none()
        check("组级存在", group is not None, f"got={group}")
        if group:
            check("组级父链挂村级", group.parent_id == village.id)
            check("组级 full_name 含村链", village.name in group.full_name, f"full_name={group.full_name}")
        if village and town:
            check("村级 full_name 含镇链", town.name in village.full_name, f"full_name={village.full_name}")

        # 幂等：再跑一遍，不再新建
        stats2 = sync_regions_from_qs_table(db, rows, scope)
        check("幂等重跑 created = 0", stats2["created"] == 0, f"got={stats2['created']}")
        check("幂等重跑 renamed = 0", stats2["renamed"] == 0, f"got={stats2['renamed']}")

        # 导出（区域表 → 代码表）：与上面同步同一事务，回滚前跑
        print("== 6. 导出（区域表 → 代码表，同一事务）==")
        export_rows = build_qs_rows_from_regions(db, "321324100022")
        check("村级导出含自身 + 10 个组", len(export_rows) == 11, f"got={len(export_rows)}")
        check("村级导出首行为自身补零码", export_rows[0] == ("32132410002200", "泗洪县青阳镇宏伟居"), f"got={export_rows[0]}")
        check("组行补零码 = 原码", all(code == group_code for (code, _), group_code in zip(export_rows[1:], [f"321324100022{n:02d}" for n in range(1, 11)])), f"got={[c for c, _ in export_rows[1:]]}")
        county_rows = build_qs_rows_from_regions(db, "321324")
        check("县级导出 ≥ 村级导出", len(county_rows) >= len(export_rows), f"county={len(county_rows)} village={len(export_rows)}")
        codes = [c for c, _ in county_rows]
        check("补零码升序（县→镇→村→组）", codes == sorted(codes))
        check("县级首行补零码", codes[0] == "32132400000000", f"got={codes[0]}")
        names_by_code = dict(county_rows)
        check("县级导出含镇行", names_by_code.get("32132410000000") == "泗洪县青阳镇", f"got={names_by_code.get('32132410000000')}")
        empty = build_qs_rows_from_regions(db, "")
        check("空区域码返回空", empty == [])
    finally:
        db.rollback()  # 验收不留痕
        db.close()

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n共 {len(RESULTS)} 项，失败 {len(failed)} 项")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
