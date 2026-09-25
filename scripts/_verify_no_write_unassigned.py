"""验收：未分配 / 非归属人 **不能录入**，只能查看详细信息。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_no_write_unassigned.py

要证明的四件事：
1. 规则表（服务层，零写入）：管理员 / 归属人 → 放行；**批次创建人不再豁免**
   （2026-09-24 起创建人也按任务归属判）⇒ 对未分配户 403「尚未分配」、
   对别人的户 403「已分配给 X」；未分配 → 403，只能查看。
2. HTTP 层的写接口确实拦得住（`PUT /results/{uid}`、`POST .../skip`、`add-parcel`）——
   越权请求走的是 403，而不是「界面藏了按钮但接口能打」。
3. 列表里的 `canWrite` 与规则表同口径（前端据此把「调查录入」降级成「查看详情」）。
4. 静态核查：`_ensure_editable_batch_and_result` 的调用点全部传了 `current_user`
   （它是附件 / 委托书 / 权属调整 / 标签等子资源写接口的总闸，漏传等于放行）。

**不写任何真实数据**：所有 403 断言都发生在写操作之前；唯一的临时改动是
「把 batch 41 的一户临时分给某人」，结束时原样改回并断言已复原。
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
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_no_write_unassigned.txt"
BATCH_ID = 41


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
TEMP_ASSIGNEE_RESTORE: list[tuple[str, None]] = []


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


def show(title: str, resp, limit: int = 400) -> None:
    log(f"--- {title} -> {resp.status_code}")
    if resp.headers.get("content-type", "").startswith("application/json"):
        log("   ", json.dumps(resp.json(), ensure_ascii=False, default=str)[:limit])
    else:
        log("   ", str(resp.text)[:limit])


def rows(sql: str, **params):
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params).all()]


def scalar(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


class _FakeBatch:
    """只为验证「批次创建人」豁免这条纯规则，不触发任何查询。"""

    def __init__(self, created_by):
        self.id = -1
        self.created_by = created_by


# 不进入 with，所以不触发 lifespan（不会重跑 bootstrap / seed）。
client = TestClient(app)

try:
    log("========== 0. 静态核查：写权限总闸的调用点都传了 current_user ==========")
    offenders: list[str] = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        if path.name == "migrations.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            if "_ensure_editable_batch_and_result(" in line and "def " not in line and "current_user" not in line:
                offenders.append(f"{path.relative_to(ROOT)}:{lineno} {line.strip()}")
    log("   漏传 current_user 的调用点 =", offenders or "（无）")
    check("_ensure_editable_batch_and_result 无漏传（附件/委托书/权属调整/标签的总闸）", not offenders, offenders)

    log("")
    log("========== 1. 规则表（服务层，零写入） ==========")
    db = SessionLocal()
    admin = db.get(User, 1)
    set_current_user(db, admin)

    batch = survey_service._ensure_batch(db, BATCH_ID)
    log(f"   批次 #{batch.id} {batch.batch_name} created_by={batch.created_by} status={batch.status} region={batch.region_code}")
    task_rows = rows(
        """
        SELECT contractor_uid, cbfbm, cbfmc, task_status, assigned_to, assigned_to_name
        FROM survey_cbf_base WHERE batch_id = :bid ORDER BY cbfbm
        """,
        bid=BATCH_ID,
    )
    log(f"   本批任务行 = {len(task_rows)} 条，已分配 = {sum(1 for r in task_rows if r[4] is not None)} 条")

    # 挑一个「当前未分配」的户做后续 403 断言。
    target = next((row for row in task_rows if row[4] is None), None)
    check("batch 41 里存在未分配的户（本轮口径的适用对象）", target is not None, task_rows[:3])
    if target is None:
        raise RuntimeError("batch 41 没有未分配的户，无法验收")

    target_uid, target_cbfbm, target_task_status = target[0], target[1], target[3]
    log(f"   选中的户 = {target_cbfbm} ({target[2]}), uid={target_uid}")

    # 找几个「有 contractors.manage 权限」的用户当演员。
    actors = []
    for user in db.scalars(
        select(User).where(User.status == "active").order_by(User.id)
    ).all():
        codes = {p.code for p in (user.role.permissions if user.role else [])}
        actors.append(
            {
                "id": user.id,
                "name": user.real_name,
                "scope": user.role.data_scope if user.role else None,
                "can_manage": "contractors.manage" in codes,
            }
        )
    log("   可用演员 =")
    for item in actors:
        log(f"     #{item['id']} {item['name']} scope={item['scope']} contractors.manage={item['can_manage']}")

    writer = next(
        (item for item in actors if item["can_manage"] and item["scope"] != "all" and item["id"] != batch.created_by),
        None,
    )
    check("存在一个「非管理员 + 有 contractors.manage」的演员（否则 403 会来自权限层，验不出归属）", writer is not None, actors)

    creator_user = db.get(User, batch.created_by) if batch.created_by else None
    log(f"   批次创建人 = #{batch.created_by} {creator_user.real_name if creator_user else None}")

    # ---- 未分配：只有管理员放行（创建人 2026-09-24 起不再豁免录入写权） ----
    log("")
    log("   [未分配] 判定：")
    check(
        "管理员（data_scope=all）→ 可写",
        survey_service.can_write_task(db, batch, target_uid, admin) is True,
    )
    if creator_user is not None:
        set_current_user(db, creator_user)
        creator_can = survey_service.can_write_task(db, batch, target_uid, creator_user)
        try:
            survey_service.ensure_task_write_permission(
                db, batch, survey_service._get_result(db, BATCH_ID, target_uid), creator_user
            )
            creator_raised = None
        except HTTPException as exc:  # noqa: BLE001
            creator_raised = exc
        check(
            f"批次创建人 #{creator_user.id} {creator_user.real_name} 对未分配户 → canWrite=False 且 403「尚未分配」"
            "（创建人不再豁免录入写权）",
            creator_can is False
            and creator_raised is not None
            and creator_raised.status_code == 403
            and "尚未分配" in str(creator_raised.detail),
            f"canWrite={creator_can} raised={creator_raised.status_code if creator_raised else None} "
            f"detail={creator_raised.detail if creator_raised else None}",
        )

    set_current_user(db, admin)
    for actor in actors:
        if actor["scope"] == "all" or not actor["can_manage"] or actor["id"] == batch.created_by:
            # 创建人已在上方单独断言过（结论相同，不重复报）
            continue
        user = db.get(User, actor["id"])
        set_current_user(db, user)
        can = survey_service.can_write_task(db, batch, target_uid, user)
        try:
            survey_service.ensure_task_write_permission(db, batch, survey_service._get_result(db, BATCH_ID, target_uid), user)
            raised = None
        except HTTPException as exc:  # noqa: BLE001
            raised = exc
        check(
            f"#{actor['id']} {actor['name']}（未分配到这一户）→ canWrite=False 且 403「尚未分配」",
            can is False and raised is not None and raised.status_code == 403 and "尚未分配" in str(raised.detail),
            f"canWrite={can} raised={raised.status_code if raised else None} detail={raised.detail if raised else None}",
        )
        set_current_user(db, admin)

    # 纯规则（duck-typed，不查库）：两个豁免口分工不同，别混用。
    if writer is not None:
        check(
            "is_batch_privileged（**分配**权）：created_by=我 → True",
            survey_service.is_batch_privileged(_FakeBatch(created_by=writer["id"]), db.get(User, writer["id"])) is True,
        )
        check(
            "is_batch_privileged（**分配**权）：既非管理员也非创建人 → False",
            survey_service.is_batch_privileged(_FakeBatch(created_by=999999), db.get(User, writer["id"])) is False,
        )
        check(
            "is_task_write_privileged（**录入**写权）：非管理员（哪怕他是批次创建人）→ False",
            survey_service.is_task_write_privileged(db.get(User, writer["id"])) is False,
        )
    check(
        "is_task_write_privileged（**录入**写权）：管理员 → True",
        survey_service.is_task_write_privileged(admin) is True,
    )
    if creator_user is not None:
        check(
            f"is_task_write_privileged：批次创建人 #{creator_user.id}（非管理员）→ False",
            survey_service.is_task_write_privileged(creator_user) is False,
        )

    # ---- 已分配给他人：只有归属人 / 管理员放行（创建人不再豁免） ----
    log("")
    log("   [已分配给他人] 判定（临时把这一户分给 writer，结束会改回）：")
    if writer is not None:
        owner = db.get(User, writer["id"])
        before_assigned = scalar("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_to IS NOT NULL", bid=BATCH_ID)
        result = survey_service.assign_tasks(
            db, BATCH_ID, {"contractorUids": [target_uid], "assigneeId": owner.id}, admin
        )
        after = rows(
            "SELECT assigned_to, assigned_to_name FROM survey_cbf_base WHERE batch_id = :bid AND contractor_uid = :uid",
            bid=BATCH_ID,
            uid=target_uid,
        )
        log(f"   临时分配结果 = {after}（assign_tasks updated={result.get('updated')}）")
        check("临时分配生效", after and after[0][0] == owner.id, after)
        TEMP_ASSIGNEE_RESTORE.append((target_uid, None))

        owner_ok = survey_service.can_write_task(db, batch, target_uid, owner)
        check(f"归属人 #{owner.id} {owner.real_name} → 可写", owner_ok is True)
        check("管理员 → 可写", survey_service.can_write_task(db, batch, target_uid, admin) is True)
        if creator_user is not None:
            set_current_user(db, creator_user)
            creator_can2 = survey_service.can_write_task(db, batch, target_uid, creator_user)
            try:
                survey_service.ensure_task_write_permission(
                    db, batch, survey_service._get_result(db, BATCH_ID, target_uid), creator_user
                )
                creator_raised2 = None
            except HTTPException as exc:  # noqa: BLE001
                creator_raised2 = exc
            set_current_user(db, admin)
            check(
                f"批次创建人 #{creator_user.id} {creator_user.real_name} 对「已分给他人」的户 "
                "→ canWrite=False 且 403「已分配给」（创建人不再豁免）",
                creator_can2 is False
                and creator_raised2 is not None
                and creator_raised2.status_code == 403
                and "已分配给" in str(creator_raised2.detail),
                f"canWrite={creator_can2} raised={creator_raised2.status_code if creator_raised2 else None} "
                f"detail={creator_raised2.detail if creator_raised2 else None}",
            )

        # 换一个「不是归属人」的演员来打越权请求
        intruder = next(
            (
                item
                for item in actors
                if item["can_manage"]
                and item["scope"] != "all"
                and item["id"] not in {owner.id, batch.created_by}
            ),
            None,
        )
        if intruder is None:
            log("   （没有第三方演员可做越权请求，跳过 HTTP 越权断言）")
        else:
            set_current_user(db, admin)
            log(f"   越权演员 = #{intruder['id']} {intruder['name']}")
            intro_user = db.get(User, intruder["id"])
            set_current_user(db, intro_user)
            intruder_can = survey_service.can_write_task(db, batch, target_uid, intro_user)
            check(f"#{intruder['id']} 对别人的户 canWrite=False", intruder_can is False)

            # ---- HTTP 越权：写接口必须 403，且不能有任何写入 ----
            log("")
            log("   [HTTP] 越权写请求（全部必须 403，且不得落库）：")
            payload = {
                "code": target_cbfbm,
                "typeCode": "1",
                "name": "越权验收",
                "idType": "1",
                "idNo": "320000199001019999",
                "address": "越权验收地址",
                "postcode": "223900",
            }
            resp = client.put(f"{BASE}/surveys/batches/{BATCH_ID}/results/{target_uid}", json=payload, headers=token(intruder["id"]))
            show("PUT /surveys/batches/41/results/<uid>（越权）", resp)
            check(
                "PUT 保存调查结果 → 403「已分配给」",
                resp.status_code == 403 and "已分配给" in json.dumps(resp.json(), ensure_ascii=False),
                resp.text[:300],
            )

            resp = client.post(
                f"{BASE}/surveys/batches/{BATCH_ID}/tasks/{target_uid}/skip",
                json={"skipReason": "越权验收"},
                headers=token(intruder["id"]),
            )
            show("POST .../skip（越权）", resp)
            check(
                "POST 跳过 → 403「已分配给」",
                resp.status_code == 403 and "已分配给" in json.dumps(resp.json(), ensure_ascii=False),
                resp.text[:300],
            )

            # 注意：请求体必须先合法，否则 Pydantic 会在进服务层前就 422，
            # 那验的是「参数校验」而不是「归属闸」——本轮要验的是后者。
            resp = client.post(
                f"{BASE}/surveys/batches/{BATCH_ID}/results/{target_uid}/add-parcel",
                json={
                    "dkbm": target_cbfbm[:19],
                    "dkmc": "越权验收地块",
                    "scmj": 1.0,
                    "dklb": "1",
                    "tdyt": "1",
                    "sfjbnt": "2",
                    "dldj": "1",
                },
                headers=token(intruder["id"]),
            )
            show("POST .../add-parcel（越权、合法 payload）", resp)
            detail = json.dumps(resp.json(), ensure_ascii=False) if resp.content else ""
            check(
                "POST 新增地块 → 403「已分配给」/「尚未分配」（拦在归属层，不是 400/422）",
                resp.status_code == 403 and ("已分配给" in detail or "尚未分配" in detail),
                resp.text[:300],
            )

            resp = client.post(
                f"{BASE}/surveys/batches/{BATCH_ID}/results/{target_uid}/tags",
                json={"tagCode": "whole_family_urbanized", "tagName": "越权验收标签"},
                headers=token(intruder["id"]),
            )
            show("POST .../tags（越权）", resp)
            detail = json.dumps(resp.json(), ensure_ascii=False) if resp.content else ""
            check(
                "POST 打标签 → 403（走 _ensure_editable_batch_and_result 总闸）",
                resp.status_code == 403 and ("已分配给" in detail or "尚未分配" in detail),
                resp.text[:300],
            )

            # 写接口被拒后，库内不该有任何变化。
            # 注意 survey_status 在 survey_cbf_result 上，survey_cbf_base 只有 task_status，
            # 这里只查 base 表的列，避免 UndefinedColumn。
            untouched = rows(
                """
                SELECT cbfmc, task_status, assigned_to, assigned_to_name
                FROM survey_cbf_base WHERE batch_id = :bid AND contractor_uid = :uid
                """,
                bid=BATCH_ID,
                uid=target_uid,
            )
            log(f"   越权后库内该户 = {untouched}")
            check(
                "越权请求全部被拒、库内该户未被写坏（cbfmc 仍是原名、任务状态未变）",
                untouched
                and untouched[0][0] != "越权验收"
                and untouched[0][1] == target_task_status
                and untouched[0][2] == owner.id,
                f"{untouched} (原 task_status={target_task_status})",
            )
            check(
                "临时分配前后的已分配户数一致（没被越权请求改掉）",
                scalar("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_to IS NOT NULL", bid=BATCH_ID) == before_assigned + 1,
            )

            # ---- canWrite 字段：前端「调查录入 / 查看详情」的唯一依据 ----
            log("")
            log("   [HTTP] 列表里的 canWrite：")
            for viewer_id, expect in ((owner.id, True), (intruder["id"], False), (1, True)):
                resp = client.get(
                    f"{BASE}/surveys/batches/{BATCH_ID}/tasks",
                    params={"page": 1, "page_size": 200},
                    headers=token(viewer_id),
                )
                items = resp.json()["data"]["items"] if resp.status_code == 200 else []
                row = next((item for item in items if item["contractorUid"] == target_uid), None)
                log(
                    f"     viewer #{viewer_id}: status={resp.status_code} "
                    f"canWrite={row.get('canWrite') if row else None} assignedTo={row.get('assignedTo') if row else None}"
                )
                check(
                    f"viewer #{viewer_id} 看到 canWrite={expect}",
                    row is not None and row.get("canWrite") is expect,
                    row,
                )

    # ---- 未分配的 HTTP 403（把临时分配收回后） ----
    log("")
    log("   [HTTP] 未分配户的写请求（收回分配后）：")
    set_current_user(db, admin)
    survey_service.assign_tasks(db, BATCH_ID, {"contractorUids": [target_uid], "assigneeId": None}, admin)
    TEMP_ASSIGNEE_RESTORE.clear()
    restored = rows(
        "SELECT assigned_to, assigned_to_name, assigned_at FROM survey_cbf_base WHERE batch_id = :bid AND contractor_uid = :uid",
        bid=BATCH_ID,
        uid=target_uid,
    )
    log(f"   收回分配后 = {restored}")
    check("临时分配已原样收回（assigned_* 全为 NULL）", restored and restored[0][0] is None and restored[0][1] is None and restored[0][2] is None, restored)

    if writer is not None:
        resp = client.put(
            f"{BASE}/surveys/batches/{BATCH_ID}/results/{target_uid}",
            json={
                "code": target_cbfbm, "typeCode": "1", "name": "越权验收", "idType": "1",
                "idNo": "320000199001019999", "address": "越权验收地址", "postcode": "223900",
            },
            headers=token(writer["id"]),
        )
        show(f"PUT 保存（#{writer['id']} 对未分配户）", resp)
        check(
            "未分配户：非管理员保存 → 403「尚未分配，只能查看详细信息」",
            resp.status_code == 403 and "尚未分配" in json.dumps(resp.json(), ensure_ascii=False),
            resp.text[:300],
        )

        resp = client.get(
            f"{BASE}/surveys/batches/{BATCH_ID}/tasks",
            params={"page": 1, "page_size": 200},
            headers=token(writer["id"]),
        )
        row = next(
            (item for item in (resp.json()["data"]["items"] if resp.status_code == 200 else []) if item["contractorUid"] == target_uid),
            None,
        )
        check(f"未分配户对 #{writer['id']} 的 canWrite=False（前端显示「查看详情」）", row is not None and row.get("canWrite") is False, row)

    db.close()

except Exception as exc:  # noqa: BLE001
    import traceback

    CHECKS["fail"] += 1
    FAILED.append(f"脚本异常：{exc!r}")
    OUT.append("")
    OUT.append("!!! 脚本异常，堆栈如下 !!!")
    OUT.append(traceback.format_exc())
finally:
    # 兜底：把可能残留的临时分配收回（只动这一户，且只在它确实被临时改过时才动）
    try:
        if TEMP_ASSIGNEE_RESTORE:
            db2 = SessionLocal()
            set_current_user(db2, db2.get(User, 1))
            for uid, _ in TEMP_ASSIGNEE_RESTORE:
                survey_service.assign_tasks(db2, BATCH_ID, {"contractorUids": [uid], "assigneeId": None}, db2.get(User, 1))
            db2.close()
            OUT.append("cleanup: 已收回临时分配")
        OUT.append(
            "残留检查：batch 41 已分配户数 = "
            + str(scalar("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_to IS NOT NULL", bid=BATCH_ID))
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
