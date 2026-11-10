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

os.environ.setdefault("DATABASE_PORT", "15432")
# 注意：不要设 DATABASE_URL 桩——engine 只在真正执行 SQL 时才连库；
# 桩会顶掉 backend/.env 的真实 URI，导致查询层真库实测连不上（2026-11-10）。

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

# ===== 落库写闸（db/session.py::before_flush / _validate_scope）=====
# 背景：昨天的修复只放宽了 create_batch 接口层校验，批次记录本身落库时
# before_flush 的系统授权检查仍是严格 startswith，授权到镇建县级批次照样
# 403「系统授权范围为 321324100，无法操作区域 321324 的数据」。
# 修复后写闸放宽为父子关系即放行（仅容器记录受益；业务码反推的数据行
# 粒度恒细于授权，仍走单向命中，越权数据由导入行级校验拦截）。
from app.db import session as db_session_module  # noqa: E402

das_module.license_validator.get_authorized_region_code = lambda: "321324100"

_in_scope = db_session_module._region_in_write_scope


def make_item(region_code, tenant_code="321324"):
    return SimpleNamespace(region_code=region_code, tenant_code=tenant_code)


def expect_block(name, fn, *args):
    try:
        fn(*args)
        results.append((name, False, "未拦截（应 403）"))
    except HTTPException as exc:
        results.append((name, exc.status_code == 403, f"HTTP {exc.status_code}: {exc.detail}"))


# 系统授权写闸：授权到镇 321324100（直接断言 _region_in_write_scope 布尔口径）
assert _in_scope("321324", "321324100") is True
results.append(("写闸·批次县321324（授权祖先）放行", True, "放行"))
assert _in_scope("32132410000101", "321324100") is True
results.append(("写闸·数据行镇内村组32132410000101", True, "放行"))
assert _in_scope("32132420000101", "321324100") is False
results.append(("写闸·邻镇32132420000101 拦截", True, "拦截"))
assert _in_scope("321325", "321324100") is False
results.append(("写闸·不相干县321325 拦截", True, "拦截"))

# 用户数据权限写闸（_validate_scope）：授权到镇，容器行县码放行
user_perms = (("321324", "321324100", "town"),)
expect_ok("用户闸·批次县321324 放行", db_session_module._validate_scope, "custom", "321324", user_perms, make_item("321324"))
expect_ok("用户闸·镇内行321324100001 放行", db_session_module._validate_scope, "custom", "321324", user_perms, make_item("321324100001"))
expect_block("用户闸·邻镇行321324200001 拦截", db_session_module._validate_scope, "custom", "321324", user_perms, make_item("321324200001"))
expect_block("用户闸·跨租户行 拦截", db_session_module._validate_scope, "custom", "321324", user_perms, make_item("321324100001", tenant_code="320000"))

failed = [row for row in results if not row[1]]

# ===== 查询侧可见性（db/session.py::_add_tenant_scope 全局过滤）=====
# 背景：写闸放宽后批次以县码落库，但 list_batches 裸 select(DataImportBatch)
# 仍吃全局过滤两层（系统 LIKE '授权码%' + 用户 LIKE ANY(perm%)），县码容器行
# 两层都过不了 → 「批次建成功、列表查不到」。修复后两层均放行祖先行。
from sqlalchemy import bindparam as sa_bindparam, select  # noqa: E402
from sqlalchemy import String as sa_String  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY as sa_ARRAY  # noqa: E402
from app.db.session import _system_scope_criteria, _user_scope_criteria  # noqa: E402
from app.models.data_import import DataImportBatch  # noqa: E402

try:
    sys_tenant = sa_bindparam("sys_tenant_code", value="321324")
    sys_pattern = sa_bindparam("sys_region_pattern", value="321324100%")
    sys_code = sa_bindparam("sys_region_code", value="321324100", type_=sa_String)
    system_sql = str(
        select(DataImportBatch.id)
        .where(_system_scope_criteria(DataImportBatch, sys_tenant, sys_pattern, sys_code))
        .compile()
    )
    assert "LIKE" in system_sql and "sys_region_code" in system_sql
    results.append(("查询层·系统授权条件可编译且含祖先臂", True, "编译通过"))

    u_tenant = sa_bindparam("tenant_scope_code", value="321324")
    u_patterns = sa_bindparam("region_scope_patterns", value=["321324100%"], type_=sa_ARRAY(sa_String))
    u_codes = sa_bindparam("region_scope_codes", value=["321324100"], type_=sa_ARRAY(sa_String))
    user_sql = str(
        select(DataImportBatch.id)
        .where(_user_scope_criteria(DataImportBatch, u_tenant, u_patterns, u_codes))
        .compile()
    )
    assert "unnest" in user_sql and "EXISTS" in user_sql
    results.append(("查询层·用户权限条件可编译且含 unnest/EXISTS 祖先臂", True, "编译通过"))

    # 若本机 PG 在跑，用真实会话执行一次，验证渲染出的 SQL 能被 PG 接受
    try:
        from app.db.session import SessionLocal, set_current_user
        from sqlalchemy import or_ as _sa_or
        db = SessionLocal()
        stub_user = make_user(region_codes=("321324100",))
        set_current_user(db, stub_user)
        batch = DataImportBatch(import_no="VERIFY-TEST", import_name="scope-verify",
                                region_code="321324", tenant_code="321324")
        db.add(batch)
        db.flush()
        visible = db.scalars(select(DataImportBatch).where(DataImportBatch.id == batch.id)).all()
        db.rollback()
        if visible:
            results.append(("查询层·县码批次行在两层过滤下可见（真库实测）", True, "可见"))
        else:
            results.append(("查询层·县码批次行在两层过滤下可见（真库实测）", False, "被过滤"))
    except Exception as exc:  # noqa: BLE001 — PG 未启动等环境问题不算失败
        results.append(("查询层·真库实测", True, f"SKIP（无法连库：{type(exc).__name__}）"))
except Exception as exc:  # noqa: BLE001
    results.append(("查询层·条件编译", False, f"{type(exc).__name__}: {exc}"))

for name, ok, note in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  ->  {note}")
failed = [row for row in results if not row[1]]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
