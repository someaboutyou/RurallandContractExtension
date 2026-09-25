"""验收：调查任务「分配权」放宽 + 「结束批次」不放宽（2026-09-23）。

背景：原口径 `_ensure_batch_manager`（只放行 data_scope=all 或 batch.created_by）
同时管「分配任务」和「结束批次」。用户反馈：镇级业务员登录后，「分配调查任务」
弹窗里调查员下拉为空 —— 实为接口 403，被前端误显示成"当前区县没有可分配的调查员"。

改法：拆出 `_ensure_batch_assigner`（分配权 = 管理员 / 创建人 / **数据权限覆盖本批次区域**），
`finish_batch` 仍用 `_ensure_batch_manager`。

四层验收（见 skill backend-permission-verify）：
  层0 静态核查 —— 谁调 `_ensure_batch_manager`、谁调 `_ensure_batch_assigner`，路由权限码是否都在
  层1 服务层规则表 —— 5 种情形判定 + 403 文案，零写入
  层2 HTTP —— 真实打接口；临时分配后**原样收回并断言残留 = 0**
  层3 列表口径 —— `createdByMe` 是前端「结束」按钮判据的来源

可重复跑：`runtime/windows/python/python.exe -X utf8 scripts/_verify_batch_assign_scope.py`
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
OUT: list[str] = []
CHECKS = {"ok": 0, "fail": 0}
FAILED: list[str] = []
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_batch_assign_scope.txt"

BASE = "/api/v1"


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        CHECKS["ok"] += 1
        OUT.append(f"  [OK]   {label}")
    else:
        CHECKS["fail"] += 1
        FAILED.append(label)
        OUT.append(f"  [FAIL] {label} | {detail}")


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


for _k, _v in load_env().items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("SECRET_KEY", "verify-only")

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.session import SessionLocal, engine, set_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models.survey import SurveyBatch  # noqa: E402
from app.models.user import User  # noqa: E402

# ⛔ 不进 with：进 with 会触发 lifespan → 重跑 bootstrap/seed，污染库
client = TestClient(app)

USER_ADMIN = 1
USER_MULTI = 6          # 多区域测试员：授权 321324100(镇) + 321324101203(村)，有 contractors.manage
USER_GROUP2 = 22        # 组级测试员2：授权 32132410000104/105/106，**不覆盖**城东居二组


def token(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def rows(sql: str, **params):
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text(sql), params).all()]


def scalar(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


TEMP_CLEARED = False
BATCH_ID = None
CBF_UIDS: list[str] = []

try:
    OUT.append("=" * 78)
    OUT.append("层0 静态核查：闸门调用点与路由权限码")
    OUT.append("=" * 78)

    assignment_src = (ROOT / "backend/app/services/survey/assignment.py").read_text(encoding="utf-8-sig")
    batch_src = (ROOT / "backend/app/services/survey/batch.py").read_text(encoding="utf-8-sig")
    endpoint_src = (ROOT / "backend/app/api/v1/endpoints/survey.py").read_text(encoding="utf-8-sig")

    def callers_of(src: str, name: str) -> list[str]:
        return [
            line.strip()
            for line in src.splitlines()
            if re.search(rf"(?<!def )self\.{name}\(", line) and not line.strip().startswith("#")
        ]

    manager_calls = [
        (f, callers_of(src, "_ensure_batch_manager"))
        for f, src in (("assignment.py", assignment_src), ("batch.py", batch_src))
    ]
    assigner_calls = [
        (f, callers_of(src, "_ensure_batch_assigner"))
        for f, src in (("assignment.py", assignment_src), ("batch.py", batch_src))
    ]
    OUT.append(f"  调用点 _ensure_batch_manager = {manager_calls}")
    OUT.append(f"  调用点 _ensure_batch_assigner  = {assigner_calls}")

    check(
        "分配链路（assign_tasks / list_assignable_users）已改用 _ensure_batch_assigner",
        len(assigner_calls[0][1]) == 2 and not assigner_calls[1][1],
        assigner_calls,
    )
    check(
        "assignment.py 里已无 _ensure_batch_manager 调用（分配不再走创建人闸门）",
        not manager_calls[0][1],
        manager_calls[0],
    )
    check(
        "finish_batch 仍走 _ensure_batch_manager（结束批次没被顺手放宽）",
        any("_ensure_batch_manager" in line for line in manager_calls[1][1]) and len(manager_calls[1][1]) == 1,
        manager_calls[1],
    )

    for ep, needle in (
        ("assign_survey_tasks", 'require_permission("contractors.manage")'),
        ("list_survey_assignable_users", 'require_permission("contractors.manage")'),
        ("finish_survey_batch", 'require_permission("contractors.manage")'),
    ):
        seg = endpoint_src.split(f"def {ep}(")[1][:600] if f"def {ep}(" in endpoint_src else ""
        check(f"路由 {ep} 仍挂 contractors.manage", needle in seg, seg[:120])

    OUT.append("")
    OUT.append("=" * 78)
    OUT.append("选演员：确认批次与「覆盖 / 不覆盖」两种非创建人")
    OUT.append("=" * 78)

    BATCH_ID = scalar(
        "SELECT id FROM survey_batches WHERE region_code LIKE '321324100001%' AND status = 'active' ORDER BY id DESC LIMIT 1"
    )
    check("找到可作为样本的 active 批次", BATCH_ID is not None, BATCH_ID)
    batch_region = scalar("SELECT region_code FROM survey_batches WHERE id = :b", b=BATCH_ID)
    creator = scalar("SELECT created_by FROM survey_batches WHERE id = :b", b=BATCH_ID)
    CBF_UIDS = [
        r[0]
        for r in rows(
            # ⛔ 只挑「**当前未分配**」的户，别改成 ORDER BY ... LIMIT 2：
            # 真实使用会把户分掉，挑到已分配的户就会让下面「分配前均为未分配」
            # 的前置条件不成立（2026-09-24 踩过：批次 41 前两户被分给了组级测试员）。
            # 夹具自洽点：挑的是未分配户 + 结束收回为 NULL ⇒ 天然复原原状。
            "SELECT contractor_uid FROM survey_cbf_base"
            " WHERE batch_id = :b AND assigned_to IS NULL"
            " ORDER BY contractor_uid LIMIT 2",
            b=BATCH_ID,
        )
    ]
    OUT.append(f"  批次 #{BATCH_ID} region={batch_region} created_by={creator} 取户={CBF_UIDS}")
    check("批次创建人不是测试用非创建人（否则测不出东西）",
          creator != USER_MULTI and creator is not None, creator)
    check("批次下有 ≥2 户**当前未分配**的承包方可供临时分配", len(CBF_UIDS) >= 2, CBF_UIDS)

    db = SessionLocal()
    set_current_user(db, db.get(User, USER_ADMIN))
    admin = db.get(User, USER_ADMIN)
    multi = db.get(User, USER_MULTI)
    group2 = db.get(User, USER_GROUP2)
    batch = db.get(SurveyBatch, BATCH_ID)

    from app.services.survey_service import survey_service  # noqa: E402

    OUT.append("")
    OUT.append("=" * 78)
    OUT.append("层1 服务层规则表（零写入）")
    OUT.append("=" * 78)

    class _VacantBatch:
        """没有区域码的批次，用于验"无法证明覆盖就不放行"。"""

        id = -1
        created_by = 999999
        region_code = None
        status = "active"

    cases = [
        ("管理员(data_scope=all)", batch, admin, True, ""),
        ("非创建人 + 授权覆盖本批次区域", batch, multi, True, ""),
        ("不覆盖本批次区域(组104/105/106)", batch, group2, False, "不包含本调查批次"),
        ("批次无区域码 + 非创建人", _VacantBatch(), multi, False, "缺少区域信息"),
    ]
    for label, b, user, expect_pass, expect_kw in cases:
        try:
            survey_service._ensure_batch_assigner(b, user)
            passed, msg = True, ""
        except Exception as exc:  # noqa: BLE001
            passed, msg = False, str(getattr(exc, "detail", exc))
        check(
            f"分配权：{label} → {'放行' if expect_pass else '403'}",
            passed is expect_pass and (expect_pass or expect_kw in msg),
            f"passed={passed} msg={msg}",
        )

    # 创建人豁免：授权不覆盖也应放行（与列表「与我相关」口径一致）
    class _ForeignBatch:
        id = -2
        created_by = USER_GROUP2
        region_code = "32132410000102"   # 组22 的授权不覆盖这里
        status = "active"

    try:
        survey_service._ensure_batch_assigner(_ForeignBatch(), group2)
        creator_ok = True
    except Exception:  # noqa: BLE001
        creator_ok = False
    check("分配权：创建人即便授权不覆盖也放行（避免「列表看得见、点开 403」）", creator_ok)

    # 结束批次：仍不放行非创建人
    try:
        survey_service._ensure_batch_manager(batch, multi)
        finish_blocked = False
    except Exception as exc:  # noqa: BLE001
        finish_blocked = getattr(exc, "status_code", None) == 403 and "结束批次" in str(getattr(exc, "detail", ""))
    check("结束批次：非创建人仍 403 且文案只提结束批次", finish_blocked)

    OUT.append("")
    OUT.append("=" * 78)
    OUT.append("层2 HTTP：真实请求（临时分配 → 原样收回）")
    OUT.append("=" * 78)

    r = client.get(f"{BASE}/surveys/batches/{BATCH_ID}/assignable-users", headers=token(USER_MULTI))
    names = [i.get("realName") for i in (r.json().get("data") or [])] if r.status_code == 200 else []
    check(
        "非创建人（multi_scope_user(6)）拉调查员名单 → 200 且非空",
        r.status_code == 200 and len(names) > 0,
        f"status={r.status_code} body={r.text[:200]}",
    )
    OUT.append(f"  候选调查员 = {names}")

    # ⚠️ 这里期望 404 而不是 403：`_ensure_batch` 用 `db.get(SurveyBatch)` 取批次，
    # 而 `db.get` 同样走 `do_orm_execute` ⇒ 被全局区域过滤 ⇒ 不可见的批次在**进入闸门之前**
    # 就变成"不存在"。这比 403 更好（不泄漏存在性），但它的代价是"服务层闸门"这一层
    # 在 HTTP 路径上被短路了 —— 所以层1 直接用真实 batch 对象单独验了 403。
    r22 = client.get(f"{BASE}/surveys/batches/{BATCH_ID}/assignable-users", headers=token(USER_GROUP2))
    check(
        "不覆盖本批次的用户拉名单 → 404「调查批次不存在」（可见性过滤先于闸门）",
        r22.status_code == 404 and "调查批次不存在" in r22.text,
        f"status={r22.status_code} body={r22.text[:200]}",
    )
    r22b = client.put(
        f"{BASE}/surveys/batches/{BATCH_ID}/tasks/assign",
        json={"contractorUids": CBF_UIDS, "assigneeId": USER_MULTI},
        headers=token(USER_GROUP2),
    )
    check(
        "不覆盖本批次的用户执行分配 → 不是 200（越权被拒）",
        r22b.status_code in (403, 404) and r22b.status_code != 200,
        f"status={r22b.status_code} body={r22b.text[:200]}",
    )

    before = rows(
        "SELECT contractor_uid, assigned_to, assigned_to_name, assigned_at FROM survey_cbf_base"
        " WHERE batch_id = :b AND contractor_uid = ANY(:u) ORDER BY contractor_uid",
        b=BATCH_ID,
        u=CBF_UIDS,
    )
    OUT.append(f"  分配前 = {before}")
    check("分配前这 2 户均为未分配（否则不能当临时场景）", all(x[1] is None for x in before), before)

    assignee_id = scalar(
        "SELECT id FROM users WHERE status='active' AND tenant_code='321324' AND id <> :m ORDER BY id LIMIT 1",
        m=USER_MULTI,
    )
    r = client.put(
        f"{BASE}/surveys/batches/{BATCH_ID}/tasks/assign",
        json={"contractorUids": CBF_UIDS, "assigneeId": assignee_id},
        headers=token(USER_MULTI),
    )
    check(
        "非创建人执行分配 → 200（本次放宽的核心行为）",
        r.status_code == 200 and (r.json().get("data") or {}).get("updated") == len(CBF_UIDS),
        f"status={r.status_code} body={r.text[:300]}",
    )
    after = rows(
        "SELECT contractor_uid, assigned_to FROM survey_cbf_base"
        " WHERE batch_id = :b AND contractor_uid = ANY(:u) ORDER BY contractor_uid",
        b=BATCH_ID,
        u=CBF_UIDS,
    )
    check(
        "库内已落 assigned_to（不是只返回 200）",
        after and all(x[1] == assignee_id for x in after),
        after,
    )

    r = client.put(
        f"{BASE}/surveys/batches/{BATCH_ID}/tasks/assign",
        json={"contractorUids": CBF_UIDS, "assigneeId": None},
        headers=token(USER_MULTI),
    )
    restored = rows(
        "SELECT contractor_uid, assigned_to, assigned_to_name, assigned_at FROM survey_cbf_base"
        " WHERE batch_id = :b AND contractor_uid = ANY(:u) ORDER BY contractor_uid",
        b=BATCH_ID,
        u=CBF_UIDS,
    )
    check("收回分配 → 200", r.status_code == 200, f"status={r.status_code} {r.text[:200]}")
    check(
        "临时分配已原样收回（三列全 NULL）",
        restored and all(v is None for row in restored for v in row[1:]),
        restored,
    )
    TEMP_CLEARED = True

    r = client.post(f"{BASE}/surveys/batches/{BATCH_ID}/finish", headers=token(USER_MULTI))
    check(
        "非创建人结束批次 → 仍 403「只有该调查批次的创建人可以结束批次」",
        r.status_code == 403 and "结束批次" in r.text,
        f"status={r.status_code} body={r.text[:200]}",
    )
    check(
        "越权结束没有把批次状态改掉",
        scalar("SELECT status FROM survey_batches WHERE id = :b", b=BATCH_ID) == "active",
        scalar("SELECT status FROM survey_batches WHERE id = :b", b=BATCH_ID),
    )

    OUT.append("")
    OUT.append("=" * 78)
    OUT.append("层3 列表口径：createdByMe（前端「结束」按钮判据的来源）")
    OUT.append("=" * 78)

    # createdByMe 期望值按**本批次的真实创建人**算，别假设是 admin：
    # 批次 #41 的 created_by 是测试账号，admin 在这批里也该是 False。
    for uid, label in (
        (USER_MULTI, f"multi_scope_user({USER_MULTI})"),
        (USER_ADMIN, f"admin({USER_ADMIN})"),
        (creator, f"本批次创建人({creator})"),
    ):
        expect_mine = uid == creator
        resp = client.get(f"{BASE}/surveys/batches", params={"page": 1, "page_size": 200}, headers=token(uid))
        items = (resp.json().get("data") or {}).get("items") or [] if resp.status_code == 200 else []
        row = next((i for i in items if i.get("id") == BATCH_ID), None)
        if uid != creator and row is None:
            check(f"批次列表对 {label} 返回 createdByMe={expect_mine}", False, "该用户看不到本批次，无法断言")
            continue
        check(
            f"批次列表对 {label} 返回 createdByMe={expect_mine}",
            row is not None and row.get("createdByMe") is expect_mine,
            row,
        )

    db.close()

except Exception as exc:  # noqa: BLE001
    import traceback

    CHECKS["fail"] += 1
    FAILED.append(f"脚本异常：{exc!r}")
    OUT.append("!!! 脚本异常 !!!")
    OUT.append(traceback.format_exc())
finally:
    if not TEMP_CLEARED and BATCH_ID and CBF_UIDS:
        try:
            db2 = SessionLocal()
            set_current_user(db2, db2.get(User, USER_ADMIN))
            survey_service.assign_tasks(
                db2, BATCH_ID, {"contractorUids": CBF_UIDS, "assigneeId": None}, db2.get(User, USER_ADMIN)
            )
            db2.close()
            OUT.append("  [兜底] 异常路径已把临时分配收回")
        except Exception as exc:  # noqa: BLE001
            OUT.append(f"  [兜底失败] {exc!r}")

    try:
        residual = scalar(
            "SELECT count(*) FROM survey_cbf_base WHERE batch_id = :b AND assigned_to IS NOT NULL",
            b=BATCH_ID,
        )
        OUT.append(f"  残留检查：批次 #{BATCH_ID} 已分配户数 = {residual}")
    except Exception:  # noqa: BLE001
        pass

OUT.append("")
OUT.append(f"=== 通过 {CHECKS['ok']} 项，失败 {CHECKS['fail']} 项 ===")
if FAILED:
    OUT.append("失败项：")
    OUT.extend(f"  - {i}" for i in FAILED)
RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
sys.exit(1 if CHECKS["fail"] else 0)
