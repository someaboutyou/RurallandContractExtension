"""离线联调：验证「新建批次即指派」这条线（服务层）。

① 新建调查批次**必须**指派调查员 —— 2026-09-23 起必填**只对管理员成立**
   （非管理员自动派给自己，传别人会被判 403）。所以这里的建批次者用管理员，
   非管理员 `creator` 改当「被指派人」，顺带覆盖越权分支；
② 指派后每个承包户都落到人头上（含批次内「新增承包方」）；
③ 调查员登录后，自己创建的批次与分给自己的批次在批次列表里都看得见，
   且「只看与我相关」开关能筛出这两类。

★ 完整的「按角色分流」矩阵（管理员必填 / 非管理员派给自己 / 传他人 403）在
  `scripts/_verify_batch_create_role.py`，本脚本不重复覆盖。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_assign_mandatory.py

会真实创建一个组级临时批次（数据体量最大的一块空闲区域）做验收，
结束时把本次产生的所有行删干净，可重复运行。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 控制台默认 GBK，输出里的 ✓/✗ 会直接抛 UnicodeEncodeError 把脚本打断。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_assign_mandatory.txt"


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
from pydantic import ValidationError  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, set_current_user  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.survey import SurveyBatchCreate, SurveyBatchRead  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402

OUT: list[str] = []
TEMP_BATCH_IDS: list[int] = []
TEST_CODES: list[str] = []
FAILED = 0


def log(*parts) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def check(label: str, ok: bool, extra: str = "") -> None:
    global FAILED
    if not ok:
        FAILED += 1
    OUT.append(f"   {'✓' if ok else '✗'} {label}{(' | ' + extra) if extra else ''}")


def expect_error(label: str, fn, code: int | None = None, keyword: str | None = None) -> None:
    try:
        result = fn()
        check(label, False, f"没有报错，返回 {result!r}")
    except HTTPException as exc:
        ok = (code is None or exc.status_code == code) and (not keyword or keyword in str(exc.detail))
        check(label, ok, f"{exc.status_code}: {exc.detail}")
    except ValidationError as exc:
        ok = code is None or code == 422
        check(label, ok, f"ValidationError: {exc.errors()[0]['msg']}")


def as_user(db, user):
    """切换会话当前用户（loader criteria 依赖 session.info）。"""
    set_current_user(db, user)
    return user


def dump(row: dict | None) -> str:
    if row is None:
        return "None"
    return (
        f"batch#{row['id']} {row['batchName']} createdByMe={row['createdByMe']} "
        f"assignedToMe={row['assignedToMe']} myTaskCount={row['myTaskCount']} "
        f"assignees={row['assigneeCount']} unassigned={row['unassignedCount']} total={row['taskCount']}"
    )


db = SessionLocal()
try:
    admin = as_user(db, db.get(User, 1))

    log("=== 1. 入口 schema：assigneeIds 可缺省（按角色的必填校验在服务层） ===")
    # ⛔ 2026-09-23 口径变更：必填**只对管理员成立**（非管理员自动派给自己）。
    # Pydantic 拿不到 current_user，做不了「按角色必填」，所以入口不能再写
    # min_length=1 —— 否则非管理员（前端不显示选择器、也不传该字段）会被 422 拦死。
    # 必填校验统一在 assignment.py::resolve_batch_create_assignees 按角色判。
    check(
        "不带 assigneeIds 可通过入口（schema 不再强制）",
        SurveyBatchCreate.model_validate({"batchName": "x", "regionCode": "32132410000102"}).assigneeIds is None,
    )
    check(
        "assigneeIds=[] 可通过入口",
        SurveyBatchCreate.model_validate(
            {"batchName": "x", "regionCode": "32132410000102", "assigneeIds": []}
        ).assigneeIds == [],
    )
    check(
        "带名单时通过",
        SurveyBatchCreate.model_validate(
            {"batchName": "x", "regionCode": "32132410000102", "assigneeIds": [5]}
        ).assigneeIds == [5],
    )

    log("=== 2. 找一块「有承包方数据、且没有进行中批次」的空闲组区域 ===")
    candidate = db.execute(
        text(
            """
            SELECT r.group_region_code AS code, r.group_region_name AS name, count(*) AS n
            FROM survey_cbf_result r
            WHERE r.group_region_code IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM survey_batches b
                WHERE b.status = 'active' AND b.region_code LIKE r.group_region_code || '%'
              )
            GROUP BY r.group_region_code, r.group_region_name
            ORDER BY n DESC
            LIMIT 1
            """
        )
    ).first()
    log("   candidate =", candidate)
    if candidate is None:
        raise RuntimeError("找不到可用于验收的空闲区域")
    code, name, _n = candidate

    covering = [item for item in survey_service.list_assignees(db, admin, region_code=code) if item["coversRegion"]]
    log("   覆盖该区域的候选调查员 =", [(item["id"], item["realName"]) for item in covering])
    # 非管理员候选（管理员 data_scope=all，当被指派人会让数据不真实）。
    candidates = [item for item in covering if db.get(User, item["id"]).role.data_scope != "all"]
    if not candidates:
        raise RuntimeError("该区域没有非管理员的调查员可指派，换个候选区域")
    creator = db.get(User, candidates[0]["id"])
    assignee_ids = list(dict.fromkeys([creator.id] + [item["id"] for item in candidates] + [admin.id]))
    log(f"   creator = #{creator.id} {creator.real_name}")
    log("   指派名单 =", [(item, db.get(User, item).real_name) for item in assignee_ids])
    set_current_user(db, creator)

    log("=== 3. 服务层按角色分流：管理员必填 / 非管理员只能派自己 ===")
    baseline_residue = db.execute(
        text("SELECT count(*) FROM survey_batches WHERE batch_name = '__必填验收批次__'")
    ).scalar()
    log("   运行前已存在的同名残留批次 =", baseline_residue, "（上次异常退出的遗留，结束时一并清掉）")

    # 3a 管理员（data_scope=all）：必须指派 → 400。
    as_user(db, admin)
    expect_error(
        "管理员 create_batch(assigneeIds=[]) → 400「请先指派调查员」",
        lambda: survey_service.create_batch(
            db,
            {"batchName": "__必填验收批次__", "regionCode": code, "regionName": name, "assigneeIds": []},
            admin,
        ),
        code=400,
        keyword="请先指派调查员",
    )
    expect_error(
        "管理员 create_batch(不传 assigneeIds) → 400「请先指派调查员」",
        lambda: survey_service.create_batch(
            db,
            {"batchName": "__必填验收批次__", "regionCode": code, "regionName": name},
            admin,
        ),
        code=400,
        keyword="请先指派调查员",
    )

    # 3b 非管理员：只能派给自己 → 名单里出现别人必须 403（越权在这里收口）。
    as_user(db, creator)
    expect_error(
        "非管理员 create_batch(assigneeIds=[管理员]) → 403「只有管理员可以指派其他调查员」",
        lambda: survey_service.create_batch(
            db,
            {"batchName": "__必填验收批次__", "regionCode": code, "regionName": name, "assigneeIds": [admin.id]},
            creator,
        ),
        code=403,
        keyword="只有管理员可以指派其他调查员",
    )
    check(
        "以上三类被拒后库内均无新增残留批次",
        db.execute(
            text("SELECT count(*) FROM survey_batches WHERE batch_name = '__必填验收批次__'")
        ).scalar() == baseline_residue,
        f"baseline={baseline_residue}",
    )

    log("=== 4. 带名单创建：每个承包户都必须落到人头上 ===")
    # ⛔ 2026-09-23：**只有管理员能指派多人**（非管理员传他人名单会被
    # resolve_batch_create_assignees 判 403）。所以这支脚本里"批次创建人"必须是 admin，
    # 非管理员 `creator` 只能当"被指派人"用——它仍覆盖「非管理员传他人 → 403」这条分支。
    as_user(db, admin)
    created = survey_service.create_batch(
        db,
        {"batchName": "__必填验收批次__", "regionCode": code, "regionName": name, "assigneeIds": assignee_ids},
        admin,
    )
    batch_id = created["id"]
    TEMP_BATCH_IDS.append(batch_id)
    log("   创建结果：", dump(created))
    for row in db.execute(
        text(
            "SELECT assigned_to, assigned_to_name, count(*) FROM survey_cbf_base "
            "WHERE batch_id = :bid GROUP BY assigned_to, assigned_to_name ORDER BY assigned_to"
        ),
        {"bid": batch_id},
    ).all():
        log("      户数分布 ", row)
    unassigned = db.execute(
        text("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_to IS NULL"),
        {"bid": batch_id},
    ).scalar()
    check("创建后未分配户数为 0", unassigned == 0, f"unassigned={unassigned}")
    no_time = db.execute(
        text("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_at IS NULL"),
        {"bid": batch_id},
    ).scalar()
    check("assigned_at 全部非空", no_time == 0, f"null={no_time}")
    tasks = survey_service.list_tasks(db, batch_id, 1, 5, None, None, None, creator)
    log("   调查列表前 5 行 assignedToName =", [item["assignedToName"] for item in tasks["items"]])
    check("调查列表「调查员」列有值", all(item["assignedToName"] for item in tasks["items"]))

    log("=== 5. 批次内「新增承包方」也要有归属人 ===")
    as_user(db, admin)
    added_by_creator = survey_service.create_contractor(
        db,
        batch_id,
        {
            "code": f"{code}9901",
            "name": "验收新增户甲",
            "idType": "1",
            "idNo": "321324199001019991",
            "address": "验收地址甲",
            "postcode": "223900",
            "groupRegionCode": code,
            "groupRegionName": name,
        },
        admin,
    )
    TEST_CODES.append(f"{code}9901")
    log("   由批次创建人（管理员）新增 ->", added_by_creator["cbfbm"], added_by_creator.get("assignedToName"))
    check("创建人新增的户归创建人", added_by_creator.get("assignedToName") == admin.real_name)
    rows = db.execute(
        text(
            "SELECT assigned_to FROM survey_cbf_base WHERE batch_id = :bid AND cbfbm = :code ORDER BY id"
        ),
        {"bid": batch_id, "code": f"{code}9901"},
    ).all()
    log("   该户在快照表里的全部行 assigned_to =", [row[0] for row in rows], "（应全部归到创建人）")
    check("新增户的所有行都有归属人", rows and all(row[0] == admin.id for row in rows))

    # 第二个操作人换成本批次**被指派但不是创建人**的非管理员 creator：
    # 命中 default_new_task_assignee 的分支①「操作人本身就是本批次的调查员 → 归他」。
    as_user(db, creator)
    added_by_assignee = survey_service.create_contractor(
        db,
        batch_id,
        {
            "code": f"{code}9902",
            "name": "验收新增户乙",
            "idType": "1",
            "idNo": "321324199001019992",
            "address": "验收地址乙",
            "postcode": "223900",
            "groupRegionCode": code,
            "groupRegionName": name,
        },
        creator,
    )
    TEST_CODES.append(f"{code}9902")
    log("   由「被指派但不是创建人」的非管理员新增 ->", added_by_assignee.get("assignedToName"))
    check("被指派人新增的户归自己", added_by_assignee.get("assignedToName") == creator.real_name)
    unassigned = db.execute(
        text("SELECT count(*) FROM survey_cbf_base WHERE batch_id = :bid AND assigned_to IS NULL"),
        {"bid": batch_id},
    ).scalar()
    check("两次新增后仍未分配户数仍为 0", unassigned == 0, f"unassigned={unassigned}")

    log("=== 6. 调查员视角：自己创建 / 分给自己的批次都要看得见 ===")
    others = [item for item in (2, 3, 4, 5, 6, 7) if item not in assignee_ids and item != creator.id]
    for user_id in assignee_ids + others:
        user = as_user(db, db.get(User, user_id))
        default_page = survey_service.list_batches(db, 1, 50, None, None, None, user)
        mine_page = survey_service.list_batches(db, 1, 50, None, None, None, user, mine_only=True)
        in_default = any(row["id"] == batch_id for row in default_page["items"])
        mine_row = next((row for row in mine_page["items"] if row["id"] == batch_id), None)
        log(
            f"   user#{user.id} {user.real_name:8s} 默认列表含本批次={in_default} "
            f"mineOnly={[row['id'] for row in mine_page['items']]}"
        )
        log("      mine_only 命中详情 =", dump(mine_row))
        if user_id == admin.id:  # 本批次的创建人现在是管理员（非管理员指派不了多人）
            check("创建人默认列表可见", in_default)
            check("创建人命中 createdByMe", bool(mine_row and mine_row["createdByMe"]))
        if user_id in assignee_ids:
            check(f"被指派人 #{user_id} 命中 assignedToMe", bool(mine_row and mine_row["assignedToMe"]))
        if user_id in others:
            check(f"无关用户 #{user_id} 不出现在「只看我相关」", mine_row is None)
            check(f"无关用户 #{user_id} 不越权看到本批次", not in_default)

    log("=== 7. response_model 不能把新字段滤掉 ===")
    as_user(db, admin)
    page = survey_service.list_batches(db, 1, 50, "__必填验收批次__", None, None, admin)
    parsed = SurveyBatchRead.model_validate(page["items"][0])
    log("   SurveyBatchRead ->", parsed.createdByMe, parsed.assignedToMe, parsed.myTaskCount)
    check("新字段透传", parsed.createdByMe and parsed.myTaskCount > 0)

    log("=== 8. 改派 / 收回分配（保留的再分配能力） ===")
    first = db.execute(
        text("SELECT contractor_uid, assigned_to FROM survey_cbf_base WHERE batch_id = :bid ORDER BY cbfbm LIMIT 1"),
        {"bid": batch_id},
    ).first()
    uid, before = first
    # 改派/收回走 `_ensure_batch_assigner`（管理员 / 批次创建人 / 数据权限覆盖本批次区域），
    # 所以这里用 admin 最省事；口径细节与反向断言见 `_verify_batch_assign_scope.py`。
    as_user(db, admin)
    survey_service.assign_tasks(db, batch_id, {"contractorUids": [uid], "assigneeId": None}, admin)
    after_clear = db.execute(
        text("SELECT assigned_to FROM survey_cbf_base WHERE batch_id = :bid AND contractor_uid = :uid"),
        {"bid": batch_id, "uid": uid},
    ).scalar()
    check("可以收回分配（回到未分配）", after_clear is None, f"assigned_to={after_clear}")
    # 改派目标用 admin（≠ 该户当前归属人 creator），否则改派到同一个人是空操作、验不出效果。
    survey_service.assign_tasks(db, batch_id, {"contractorUids": [uid], "assigneeId": admin.id}, admin)
    after_reassign = db.execute(
        text("SELECT assigned_to, assigned_to_name FROM survey_cbf_base WHERE batch_id = :bid AND contractor_uid = :uid"),
        {"bid": batch_id, "uid": uid},
    ).first()
    check("可以改派给别人", after_reassign[0] == admin.id, f"assigned_to={after_reassign[0]} name={after_reassign[1]}")
    log(f"   （原本 assigned_to={before}，改派后 ={after_reassign[0]}）")
finally:
    try:
        # 断言失败可能已经把事务搞脏（PG 里后续语句会一律 "current transaction is aborted"），
        # 先回滚再做清理，否则清理会静默失败、留下垃圾数据。
        db.rollback()
        for row in db.execute(
            text("SELECT id FROM survey_batches WHERE batch_name = '__必填验收批次__'")
        ).all():
            if row[0] not in TEMP_BATCH_IDS:
                TEMP_BATCH_IDS.append(row[0])
        for _bid in TEMP_BATCH_IDS:
            for _table in (
                "survey_cbf_jtcy_base",
                "survey_cbdkxx_base",
                "survey_dk_base",
                "survey_fbf_base",
                "survey_change_diffs",
                "survey_change_records",
                "survey_cbf_base",
            ):
                db.execute(text(f"DELETE FROM {_table} WHERE batch_id = :bid"), {"bid": _bid})
            db.execute(text("DELETE FROM survey_batches WHERE id = :bid"), {"bid": _bid})
        for _code in TEST_CODES:
            db.execute(text("DELETE FROM survey_cbf_result WHERE cbfbm = :code"), {"code": _code})
        db.commit()
        OUT.append("")
        OUT.append("=== cleanup ===")
        OUT.append("deleted temp batches = " + str(TEMP_BATCH_IDS))
        OUT.append("deleted temp contractors = " + str(TEST_CODES))
        OUT.append(
            "残留验收批次 = "
            + str(db.execute(text("SELECT count(*) FROM survey_batches WHERE batch_name LIKE '%验收批次%'")).scalar())
        )
        OUT.append(
            "残留验收承包方 = "
            + str(db.execute(text("SELECT count(*) FROM survey_cbf_result WHERE cbfmc LIKE '验收新增户%'")).scalar())
        )
        OUT.append(
            "残留未分配户（全库，应为 0 + 既有历史批次）= "
            + str(db.execute(text("SELECT count(*) FROM survey_cbf_base WHERE assigned_to IS NULL")).scalar())
        )
    except Exception as exc:  # noqa: BLE001
        OUT.append(f"CLEANUP FAILED: {exc}")
    OUT.append("")
    OUT.append(f"=== 断言失败项 = {FAILED} ===")
    db.close()

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
