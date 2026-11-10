"""验收：新建导入批次的区域校验放宽（授权到镇可建县级批次）。

背景：授权到镇（9 位）的用户新建导入批次时，区域下拉只有县级（6 位）可选，
旧逻辑 ensure_region_in_scope 按 startswith 严格校验直接 403，且前端静默吞掉。
修复后 create_batch 走 ensure_import_batch_region_in_scope：批次区域与授权
存在父子关系即放行；范围外数据由导入行逐行校验兜底（resolve_effective_import_region）。

运行：runtime/windows/python/python.exe scripts/_verify_import_batch_scope.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://localhost/verify_stub")
os.environ.setdefault("DATABASE_PORT", "15432")

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException  # noqa: E402

import app.services.data_access_service as das_module  # noqa: E402
from app.services.data_access_service import data_access_service  # noqa: E402

# 授权（license）区域码固定为泗洪县，避免依赖本机 license 文件
das_module.license_validator.get_authorized_region_code = lambda: "321324"


def make_user(*, data_scope="custom", region_codes=("321324201",)):
    return SimpleNamespace(
        tenant_code="321324",
        role=SimpleNamespace(data_scope=data_scope),
        region=SimpleNamespace(code="321324201000"),
        region_permissions=[
            SimpleNamespace(tenant_code="321324", region_code=code, level="town") for code in region_codes
        ],
    )


results: list[tuple[str, bool, str]] = []


def expect_ok(name: str, fn, *args):
    try:
        fn(*args)
        results.append((name, True, "放行"))
    except HTTPException as exc:
        results.append((name, False, f"HTTP {exc.status_code}: {exc.detail}"))


def expect_403(name: str, fn, *args):
    try:
        fn(*args)
        results.append((name, False, "未拦截（应 403）"))
    except HTTPException as exc:
        results.append((name, exc.status_code == 403, f"HTTP {exc.status_code}: {exc.detail}"))


new_check = data_access_service.ensure_import_batch_region_in_scope
old_check = data_access_service.ensure_region_in_scope

user_town = make_user()

# 1. 新校验：授权到镇 → 县级批次放行（本次修复的主场景）
expect_ok("新校验·授权镇321324201·批次县321324", new_check, user_town, "321324")
# 2. 新校验：批次在授权内（正常路径）仍放行
expect_ok("新校验·批次镇321324201001", new_check, user_town, "321324201001")
# 3. 新校验：不相干区域仍 403
expect_403("新校验·批次县321325", new_check, user_town, "321325")
expect_403("新校验·批次邻镇321324202", new_check, user_town, "321324202")
# 4. 新校验：跨租户仍 403
other_tenant = make_user()
other_tenant.tenant_code = "320000"
expect_403("新校验·租户不符320000", new_check, other_tenant, "321324")
# 5. 新校验：data_scope=all 放行（license 系统区域约束优先于 data_scope，与旧校验同口径）
expect_ok("新校验·管理员data_scope=all·license内区域", new_check, make_user(data_scope="all"), "321324")
# 6. 旧校验保持原样：授权到镇 → 县级批次仍 403（其他写操作不受影响）
expect_403("旧校验·授权镇·批次县321324（保持403）", old_check, user_town, "321324")
# 7. 新校验：多授权镇，县级批次放行
multi = make_user(region_codes=("321324201", "321324202"))
expect_ok("新校验·双镇授权·批次县321324", new_check, multi, "321324")

failed = [row for row in results if not row[1]]
for name, ok, note in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ->  {note}")
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
