"""验收：新建调查批次的「指派调查员」按角色分流（2026-09-23 用户要求）。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_batch_create_role.py

用户原话：*"管理员新建批次的时候要有指派调查员选择，其他人不需要。其他人新建批次的时候，
直接指派给自己。后端需要验证这个逻辑，防止越权。"*

要证明的四件事：

1. **纯规则（零写入）**—— `resolve_batch_create_assignees`：
   | 角色 | 入参 | 期望 |
   | --- | --- | --- |
   | 管理员 | 不传 / 空数组 | **400**「请先指派调查员」（必填） |
   | 管理员 | `[a]` / `[a,b,a]` | `[a]` / `[a,b]`（去重保序） |
   | 其他人 | 不传 / 空 / `[自己]` | 归一成 `[自己]` |
   | 其他人 | 含他人 | **403**（不静默改回自己） |
   | 任何人 | 非法值（如 `["abc"]`） | 400 |
2. **HTTP 层真的拦得住**：`POST /surveys/batches`（in-process ASGI，不碰正在跑的 8000）
   - 管理员不带名单 → 400，且**不落库**
   - 非管理员带他人 id → 403，且**不落库**
   - 非管理员不带名单 → 200，且该批次**每一户** `assigned_to` = 本人、`assigned_at` 非空
   - 管理员带名单 → 200，户落到名单上
3. `is_global_admin` 是「按人筛选下拉」的管理员判据（前端 `dataScope === "all"` 同源）。
4. 静态核查：前端不再用 `contractors.manage` 当这个下拉的判据。

会真实创建**临时批次**（选空闲区域里体量最小的一块，控制耗时），每验完立刻删干净，
结束时断言残留为 0，可重复运行。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_batch_create_role.txt"
BATCH_NAME = "__角色指派验收批次__"
DROP_TABLES = (
    "survey_cbf_jtcy_base",
    "survey_cbdkxx_base",
    "survey_dk_base",
    "survey_fbf_base",
    "survey_change_diffs",
    "survey_change_records",
    "survey_cbf_base",
)


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    # 配置文件带 BOM，必须用 utf-8-sig
    for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


for _key, _value in load_env().items():
    os.environ.setdefault(_key, _value)
os.environ.setdefault("SECRET_KEY", "verify-only")

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import SessionLocal, engine, set_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402

BASE = "/api/v1"
OUT: list[str] = []
CHECKS = {"ok": 0, "fail": 0}
FAILED: list[str] = []
TEMP_BATCH_IDS: list[int] = []


def log(*parts) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        CHECKS["ok"] += 1
        log(f"  [OK]   {label}")
    else:
        CHECKS["fail"] += 1
        FAILED.append(label)
        log(f"  [FAIL] {label} | {detail}")


def token(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def rows(sql: str, **params):
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params).all()]


def scalar(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def show(title: str, resp, limit: int = 300) -> None:
    log(f"--- {title} -> {resp.status_code}")
    if resp.headers.get("content-type", "").startswith("application/json"):
        log("   ", json.dumps(resp.json(), ensure_ascii=False, default=str)[:limit])
    else:
        log("   ", str(resp.text)[:limit])


def body_text(resp) -> str:
    return json.dumps(resp.json(), ensure_ascii=False) if resp.content else ""


def drop_batch(batch_id: int) -> None:
    """把临时批次连壳带芯删干净（与现有验收脚本同一张表清单）。"""
    with engine.begin() as conn:
        for table in DROP_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE batch_id = :bid"), {"bid": batch_id})
        conn.execute(text("DELETE FROM survey_batches WHERE id = :bid"), {"bid": batch_id})


def expect_error(label: str, fn, *, code: int | None = None, keyword: str | None = None) -> None:
    try:
        result = fn()
    except HTTPException as exc:
        ok = True
        if code is not None and exc.status_code != code:
            ok = False
        if keyword and keyword not in str(exc.detail):
            ok = False
        check(label, ok, f"{exc.status_code}: {exc.detail}")
        return
    check(label, False, f"没有报错，返回 {result!r}")


def batch_residue() -> int:
    return scalar("SELECT count(*) FROM survey_batches WHERE batch_name = :n", n=BATCH_NAME)


# 不进入 with，所以不触发 lifespan（不会重跑 bootstrap / seed）。
client = TestClient(app)

try:
    db = SessionLocal()
    admin = db.get(User, 1)
    set_current_user(db, admin)
    log(f"   管理员 = #{admin.id} {admin.real_name} scope={admin.role.data_scope if admin.role else None}")

    log("")
    log("========== 0. 挑操作人：必须「非管理员 + 有 contractors.manage 权限」 ==========")
    # ⛔ 只挑"非管理员"不够：入口还挂 require_permission("contractors.manage")，
    # 没有该权限的用户（如县级审核员 #2）会在权限层就被 403 拦掉，
    # 那样验到的是权限而不是归属/角色分流规则。
    manage_users = [
        db.get(User, row[0])
        for row in rows(
            """
            SELECT DISTINCT u.id
            FROM users u JOIN roles ro ON ro.id = u.role_id
            WHERE u.status = 'active' AND ro.data_scope <> 'all'
              AND EXISTS (
                SELECT 1 FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                WHERE rp.role_id = u.role_id AND p.code = 'contractors.manage'
              )
            ORDER BY u.id
            """
        )
    ]
    log("   有 contractors.manage 权限的非管理员 =", [(u.id, u.real_name) for u in manage_users])
    check(
        "存在「非管理员 + 有 contractors.manage」的用户（否则 403 全来自权限层，验不出角色分流）",
        bool(manage_users),
        manage_users,
    )

    code = name = None
    creator = None
    for user in manage_users:
        authorized = [
            row[0]
            for row in rows(
                "SELECT region_code FROM user_region_permissions WHERE user_id = :u ORDER BY region_code",
                u=user.id,
            )
        ]
        if not authorized:
            continue
        for auth_code in authorized:
            hit = rows(
                """
                SELECT r.group_region_code, r.group_region_name, count(*) AS n
                FROM survey_cbf_result r
                WHERE r.group_region_code IS NOT NULL
                  AND r.group_region_code LIKE :prefix
                  AND NOT EXISTS (
                    SELECT 1 FROM survey_batches b
                    WHERE b.status = 'active' AND b.region_code LIKE r.group_region_code || '%'
                  )
                GROUP BY r.group_region_code, r.group_region_name
                HAVING count(*) BETWEEN 10 AND 500
                ORDER BY n
                LIMIT 1
                """,
                prefix=f"{auth_code}%",
            )
            if hit and survey_service._user_covers_region(user, hit[0][0]):
                code, name = hit[0][0], hit[0][1]
                creator = user
                log(
                    f"   选中区域 = {code} {name}（{hit[0][2]} 户），"
                    f"操作人 = #{user.id} {user.real_name}（授权 {auth_code}）"
                )
                break
        if creator is not None:
            break
    if creator is None:
        raise RuntimeError("找不到「空闲 + 有数据 + 有 manage 权限的非管理员覆盖」的区域，无法验收")
    set_current_user(db, creator)
    log(f"   非管理员操作人 = #{creator.id} {creator.real_name} scope={creator.role.data_scope if creator.role else None}")

    # 再找一个跟上面两位都不同的用户，用来验「指派他人」的越权分支。
    others = [
        user
        for user in db.scalars(select(User).where(User.status == "active").order_by(User.id)).all()
        if user.id not in {admin.id, creator.id}
    ]
    check("存在第三个用户可做「他人」样本", bool(others), others)
    other_a = others[0]
    other_b = others[1] if len(others) > 1 else others[0]
    log(f"   他人样本 = #{other_a.id} {other_a.real_name} / #{other_b.id} {other_b.real_name}")

    set_current_user(db, admin)

    log("")
    log("========== 1. 纯规则：按角色分流（零写入） ==========")
    check("is_global_admin(管理员) == True", survey_service.is_global_admin(admin) is True)
    check("is_global_admin(非管理员) == False", survey_service.is_global_admin(creator) is False)
    check("is_global_admin(None) == False", survey_service.is_global_admin(None) is False)

    log("   [管理员] 必须指派：")
    expect_error(
        "管理员 不传 assigneeIds → 400「请先指派调查员」",
        lambda: survey_service.resolve_batch_create_assignees(None, admin),
        code=400,
        keyword="请先指派调查员",
    )
    expect_error(
        "管理员 assigneeIds=[] → 400「请先指派调查员」",
        lambda: survey_service.resolve_batch_create_assignees([], admin),
        code=400,
        keyword="请先指派调查员",
    )
    check(
        f"管理员 [{other_a.id}] → [{other_a.id}]",
        survey_service.resolve_batch_create_assignees([other_a.id], admin) == [other_a.id],
    )
    check(
        f"管理员 [{other_a.id},{other_b.id},{other_a.id}] → 去重保序",
        survey_service.resolve_batch_create_assignees([other_a.id, other_b.id, other_a.id], admin)
        == list(dict.fromkeys([other_a.id, other_b.id])),
    )

    log("   [非管理员] 只能派给自己：")
    check(
        "非管理员 不传 → [自己]",
        survey_service.resolve_batch_create_assignees(None, creator) == [creator.id],
    )
    check(
        "非管理员 assigneeIds=[] → [自己]",
        survey_service.resolve_batch_create_assignees([], creator) == [creator.id],
    )
    check(
        "非管理员 [自己] → [自己]",
        survey_service.resolve_batch_create_assignees([creator.id], creator) == [creator.id],
    )
    expect_error(
        f"非管理员 [{other_a.id}]（他人）→ 403",
        lambda: survey_service.resolve_batch_create_assignees([other_a.id], creator),
        code=403,
        keyword="只有管理员可以指派其他调查员",
    )
    expect_error(
        f"非管理员 [自己,{other_a.id}] → 403（混入他人也不行）",
        lambda: survey_service.resolve_batch_create_assignees([creator.id, other_a.id], creator),
        code=403,
        keyword="只有管理员可以指派其他调查员",
    )
    expect_error(
        '非法值 ["abc"] → 400「格式不正确」',
        lambda: survey_service.resolve_batch_create_assignees(["abc"], admin),
        code=400,
        keyword="格式不正确",
    )

    log("")
    log("========== 2. HTTP：真实路由（in-process ASGI，不碰 8000） ==========")
    baseline = batch_residue()
    log(f"   运行前同名残留批次 = {baseline}（上次异常退出的遗留，结束时一并清掉）")
    payload_base = {"batchName": BATCH_NAME, "regionCode": code, "regionName": name}

    log("   [2.1] 管理员不指派 → 400，且不落库")
    resp = client.post(f"{BASE}/surveys/batches", json=dict(payload_base), headers=token(admin.id))
    show("POST 新建批次（管理员 #%s，不指派）" % admin.id, resp)
    check(
        "管理员不指派 → 400「请先指派调查员」",
        resp.status_code == 400 and "请先指派调查员" in body_text(resp),
        resp.text[:300],
    )
    check("被拒后没有落库", batch_residue() == baseline, f"residue={batch_residue()}")

    log("   [2.2] 非管理员指派他人 → 403，且不落库")
    resp = client.post(
        f"{BASE}/surveys/batches",
        json={**payload_base, "assigneeIds": [other_a.id]},
        headers=token(creator.id),
    )
    show("POST 新建批次（非管理员 #%s，指派他人 #%s）" % (creator.id, other_a.id), resp)
    check(
        "非管理员指派他人 → 403「只有管理员可以指派其他调查员」",
        resp.status_code == 403 and "只有管理员可以指派其他调查员" in body_text(resp),
        resp.text[:300],
    )
    check("越权被拒后没有落库", batch_residue() == baseline, f"residue={batch_residue()}")

    log("   [2.3] 非管理员不指派 → 200，且每户都归自己")
    resp = client.post(f"{BASE}/surveys/batches", json=dict(payload_base), headers=token(creator.id))
    show("POST 新建批次（非管理员 #%s，不指派）" % creator.id, resp, limit=800)
    batch_id = resp.json()["data"]["id"] if resp.status_code == 200 and "data" in resp.json() else None
    check("非管理员不指派也能创建（后端自动派给自己）", resp.status_code == 200 and batch_id is not None, resp.text[:300])
    if batch_id:
        TEMP_BATCH_IDS.append(batch_id)
        dist = rows(
            """
            SELECT assigned_to, assigned_to_name, count(*) AS n
            FROM survey_cbf_base WHERE batch_id = :b GROUP BY assigned_to, assigned_to_name ORDER BY assigned_to
            """,
            b=batch_id,
        )
        log(f"   批次 #{batch_id} 户归属分布 = {dist}")
        unassigned = scalar("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :b AND assigned_to IS NULL", b=batch_id)
        check("该批次没有未分配户", unassigned == 0, f"unassigned={unassigned}")
        check(
            f"全部户都归到操作人 #{creator.id}（{creator.real_name}）",
            bool(dist) and all(row[0] == creator.id for row in dist),
            dist,
        )
        no_time = scalar("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :b AND assigned_at IS NULL", b=batch_id)
        check("assigned_at 全部非空", no_time == 0, f"null={no_time}")
        drop_batch(batch_id)
        TEMP_BATCH_IDS.remove(batch_id)
        check("临时批次已清理", scalar("SELECT count(*) FROM survey_batches WHERE id = :b", b=batch_id) == 0)

    log("   [2.4] 非管理员显式传 [自己] → 200（兼容旧前端）")
    resp = client.post(
        f"{BASE}/surveys/batches",
        json={**payload_base, "assigneeIds": [creator.id]},
        headers=token(creator.id),
    )
    show("POST 新建批次（非管理员 #%s，assigneeIds=[自己]）" % creator.id, resp, limit=400)
    batch_id = resp.json()["data"]["id"] if resp.status_code == 200 and "data" in resp.json() else None
    check("显式传 [自己] 也放行", resp.status_code == 200 and batch_id is not None, resp.text[:300])
    if batch_id:
        TEMP_BATCH_IDS.append(batch_id)
        unassigned = scalar("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :b AND assigned_to IS NULL", b=batch_id)
        check("该批次无未分配户", unassigned == 0, f"unassigned={unassigned}")
        drop_batch(batch_id)
        TEMP_BATCH_IDS.remove(batch_id)

    log("   [2.5] 管理员指派他人 → 200，户落到名单上")
    resp = client.post(
        f"{BASE}/surveys/batches",
        json={**payload_base, "assigneeIds": [creator.id]},
        headers=token(admin.id),
    )
    show("POST 新建批次（管理员 #%s，指派 #%s）" % (admin.id, creator.id), resp, limit=800)
    batch_id = resp.json()["data"]["id"] if resp.status_code == 200 and "data" in resp.json() else None
    check("管理员可以指派他人建批次", resp.status_code == 200 and batch_id is not None, resp.text[:300])
    if batch_id:
        TEMP_BATCH_IDS.append(batch_id)
        dist = rows(
            "SELECT assigned_to, assigned_to_name, count(*) FROM survey_cbf_base WHERE batch_id = :b "
            "GROUP BY assigned_to, assigned_to_name ORDER BY assigned_to",
            b=batch_id,
        )
        log(f"   批次 #{batch_id} 户归属分布 = {dist}")
        check(
            f"全部户都归到被指派人 #{creator.id}",
            bool(dist) and all(row[0] == creator.id for row in dist),
            dist,
        )
        drop_batch(batch_id)
        TEMP_BATCH_IDS.remove(batch_id)

    log("")
    log("========== 3. 前端静态核查：下拉判据必须是「管理员」而不是 contractors.manage ==========")
    survey_view = (ROOT / "frontend" / "src" / "views" / "SurveyView.vue").read_text(encoding="utf-8-sig", errors="replace")
    dialog = (ROOT / "frontend" / "src" / "components" / "survey" / "view" / "BatchCreateDialog.vue").read_text(
        encoding="utf-8-sig", errors="replace"
    )
    check(
        "批次面板「按调查员筛选」下拉用 showAssigneeFilter（由 isAdmin = dataScope==='all' 派生）判定",
        'v-if="showAssigneeFilter"' in survey_view
        and 'const isAdmin = computed(() => authStore.user?.dataScope === "all")' in survey_view
        and "const showAssigneeFilter = computed(() => isAdmin.value)" in survey_view,
    )
    check(
        "该下拉不再用 canManage（contractors.manage）当判据",
        'v-if="canManage"\n        v-model="batchAssigneeId"' not in survey_view,
    )
    check(
        "新建批次对话框的「指派调查员」选择器只在管理员时渲染",
        'v-if="isAdmin" label="指派调查员" required' in dialog
        and 'const isAdmin = computed(() => authStore.user?.dataScope === "all")' in dialog,
    )
    check(
        "非管理员提交时不带 assigneeIds（交给后端归一成派给自己）",
        "assigneeIds: isAdmin.value ? batchForm.assigneeIds : undefined" in dialog,
    )
    # —— 2026-09-23 追加：同类判据错配的另两处（同一个坑换控件再犯）——
    # 「结束批次」后端是 `_ensure_batch_manager`（管理员 / createdByMe），前端一度只用 canManage；
    # 「分配任务」后端曾同名收口 ⇒ 弹窗报"没有可分配的调查员"（其实是 403）。
    check(
        "「结束批次」按钮用 canFinishBatch（管理员 / 本批次创建人），不用 canManage",
        'v-if="canFinishBatch"' in survey_view
        and "canManage.value && (isAdmin.value || activeBatch.value?.createdByMe === true)" in survey_view,
    )
    assign_dialog = (
        ROOT / "frontend" / "src" / "components" / "survey" / "view" / "TaskAssignDialog.vue"
    ).read_text(encoding="utf-8-sig", errors="replace")
    check(
        "分配弹窗把「接口被拒」与「真的没有候选人」区分开（403 不再被说成没人可分配）",
        assign_dialog.count("usersError") >= 4 and "usersError ||" in assign_dialog,
        f"usersError 出现 {assign_dialog.count('usersError')} 次",
    )

    db.close()

except Exception as exc:  # noqa: BLE001
    import traceback

    CHECKS["fail"] += 1
    FAILED.append(f"脚本异常：{exc!r}")
    OUT.append("")
    OUT.append("!!! 脚本异常，堆栈如下 !!!")
    OUT.append(traceback.format_exc())
finally:
    try:
        with engine.connect() as conn:
            for row in conn.execute(text("SELECT id FROM survey_batches WHERE batch_name = :n"), {"n": BATCH_NAME}).all():
                if row[0] not in TEMP_BATCH_IDS:
                    TEMP_BATCH_IDS.append(row[0])
        for _bid in TEMP_BATCH_IDS:
            drop_batch(_bid)
        OUT.append("")
        OUT.append("=== cleanup ===")
        OUT.append("removed batches = " + str(TEMP_BATCH_IDS))
        OUT.append("残留验收批次 = " + str(batch_residue()))
        OUT.append(
            "全库「未分配」户数（应只含既有历史批次 40 之类） = "
            + str(scalar("SELECT count(*) FROM survey_cbf_base WHERE assigned_to IS NULL"))
        )
    except Exception as exc:  # noqa: BLE001
        OUT.append(f"CLEANUP FAILED: {exc}")

OUT.append("")
OUT.append(f"=== 通过 {CHECKS['ok']} 项，失败 {CHECKS['fail']} 项 ===")
if FAILED:
    OUT.append("失败项：")
    OUT.extend(f"  - {item}" for item in FAILED)

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
sys.exit(1 if CHECKS["fail"] else 0)
