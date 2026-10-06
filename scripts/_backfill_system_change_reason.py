# -*- coding: utf-8 -*-
"""存量补齐：合户 / 分户生成的户，其「变化原因」按操作类型补上默认文案。

背景
    合户 / 分户是系统自己产生的结构化变更，「变化原因」就是这次操作本身。
    旧代码把 change_reason 直接取 `payload.get("reason")`，调查员没填 ⇒ 新户、成员、
    地块三处全为 NULL ⇒ 撞上 `_validate_confirmable` 的硬闸门 ⇒ **永久无法确认**。
    新代码已改为「人填了用人的、没填按操作类型生成」，但**存量行不会追溯**，
    所以用本脚本按同一套文案补齐（文案函数直接 import 后端，保证同源）。

用法
    python scripts/_backfill_system_change_reason.py                 # dry-run，只列出将改动
    python scripts/_backfill_system_change_reason.py --apply         # 实际写入（先自动备份）
    python scripts/_backfill_system_change_reason.py --apply --policy-basis "某某文件"

⛔ 只补 change_reason（「发生了什么」是系统已知的事实）。
    policy_basis（「凭什么」是政策法规凭据）需要人工提供，本脚本不臆造；
    如需一并写入，显式传 --policy-basis。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_PORT", "15432")
os.environ.setdefault("SECRET_KEY", "backfill-only")

_env_file = ROOT / "runtime" / ".state" / "runtime.env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8-sig").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.survey.household import (  # noqa: E402  同源文案，绝不各写一份
    MERGE_MEMBER_REASON,
    MERGE_PARCEL_REASON,
    SPLIT_MEMBER_REASON,
    SPLIT_PARCEL_REASON,
    merge_new_household_reason,
    resolve_change_reason,
    split_new_household_reason,
)

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

SYSTEM_TYPES = ("merge_household", "split_household")
BACKUP_DIR = ROOT / "runtime" / ".state" / "backup"


def parse_sources(remark: str | None, change_type: str) -> list[str]:
    """从新户 remark 里取参与合户/分户的源户 contractor_uid。

    remark 形如 `merge_group:<gid>;sources:uidA,uidB` / `split_group:<gid>;source:uid`。
    """
    text = remark or ""
    if "sources:" in text:
        return [u for u in text.split("sources:", 1)[1].split(";")[0].split(",") if u]
    if "source:" in text:
        one = text.split("source:", 1)[1].split(";")[0].strip()
        return [one] if one else []
    del change_type
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="实际写入（默认只演练）")
    parser.add_argument("--policy-basis", default="", help="一并写入承包方级的政策依据（选填）")
    args = parser.parse_args()

    plan: list[dict] = []
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        # ── 1. 找出「系统生成 + 变化原因为空」的承包方行 ──
        cur.execute(
            f"""
            select id, contractor_uid, cbfbm, cbfmc, change_type, result_status, remark
            from survey_cbf_result
            where change_type = any(%s)
              and coalesce(btrim(change_reason),'') = ''
            order by change_type, id
            """,
            (list(SYSTEM_TYPES),),
        )
        targets = cur.fetchall()
        if not targets:
            print("没有需要补齐的承包方行。")
            return

        for row_id, uid, cbfbm, cbfmc, change_type, result_status, remark in targets:
            source_uids = parse_sources(remark, change_type)
            names: list[str] = []
            if source_uids:
                cur.execute(
                    "select coalesce(cbfmc,'') from survey_cbf_result where contractor_uid = any(%s)",
                    (source_uids,),
                )
                names = [r[0] for r in cur.fetchall()]

            is_new = result_status == "added"
            if is_new:
                if change_type == "merge_household":
                    new_household_reason = merge_new_household_reason(None, names)
                    member_reason, parcel_reason = MERGE_MEMBER_REASON, MERGE_PARCEL_REASON
                else:
                    new_household_reason = split_new_household_reason(
                        None, names[0] if names else None
                    )
                    member_reason, parcel_reason = SPLIT_MEMBER_REASON, SPLIT_PARCEL_REASON
            else:
                # 源户：合户写"并入哪个新户"，分户写"析出几个新户"
                if change_type == "merge_household":
                    # 新户 cbfbm 从 remark 里拿不到，用同组合并时生成的 added 行反查
                    cur.execute(
                        """
                        select cbfbm, cbfmc from survey_cbf_result
                        where result_status = 'added' and change_type = 'merge_household'
                        limit 1
                        """
                    )
                    found = cur.fetchone()
                    target_text = f"（{found[0]} {found[1]}）" if found else ""
                    new_household_reason = resolve_change_reason(None, f"因合户并入新户{target_text}")
                else:
                    new_household_reason = resolve_change_reason(None, "因分户析出新的承包户")
                member_reason = parcel_reason = ""

            # 成员：挂在该承包方下的
            cur.execute(
                """
                select id, member_uid, cyxm, change_reason from survey_cbf_jtcy_result
                where contractor_uid = %s and coalesce(btrim(change_reason),'') = ''
                order by id
                """,
                (uid,),
            )
            members = cur.fetchall()
            # 地块：cbfbm 挂在改户下的
            cur.execute(
                """
                select id, dkbm, change_reason from survey_cbdkxx_result
                where cbfbm = %s and coalesce(btrim(change_reason),'') = ''
                order by id
                """,
                (cbfbm,),
            )
            parcels = cur.fetchall()

            plan.append(
                {
                    "result_id": row_id,
                    "contractor_uid": uid,
                    "cbfbm": cbfbm,
                    "cbfmc": cbfmc,
                    "change_type": change_type,
                    "result_status": result_status,
                    "new_result_reason": new_household_reason,
                    "members": [
                        {"id": m_id, "name": name, "reason": member_reason}
                        for m_id, _uid, name, _old in members
                    ]
                    if is_new
                    else [],
                    "parcels": [
                        {"id": p_id, "dkbm": dkbm, "reason": parcel_reason}
                        for p_id, dkbm, _old in parcels
                    ]
                    if is_new
                    else [],
                }
            )

        # ── 2. 政策依据缺口（不做自动填充，只报告） ──
        cur.execute(
            """
            select count(*) from survey_cbf_result
            where change_type = any(%s) and coalesce(btrim(policy_basis),'') = ''
            """,
            (list(SYSTEM_TYPES),),
        )
        policy_missing = cur.fetchone()[0]

        # ── 3. 预览 ──
        print("=" * 76)
        print("变更预览（dry-run）" if not args.apply else "写入中……")
        print("=" * 76)
        for item in plan:
            print(f"\n[{item['change_type']}] {item['cbfbm']} {item['cbfmc']}  ({item['result_status']})")
            print(f"  承包方变化原因 → {item['new_result_reason']!r}")
            for m in item["members"]:
                print(f"  成员 {m['name']} → {m['reason']!r}")
            for p in item["parcels"]:
                print(f"  地块 {p['dkbm']} → {p['reason']!r}")

        print("\n" + "-" * 76)
        print(f"合计：承包方行 {len(plan)} 行，"
              f"成员 {sum(len(i['members']) for i in plan)} 行，"
              f"地块 {sum(len(i['parcels']) for i in plan)} 行")
        print(f"政策依据仍为空的行：{policy_missing} 行"
              + ("（将按 --policy-basis 一并写入）" if args.policy_basis else "（需人工提供，本脚本不臆造）"))

        if not args.apply:
            print("\n这是演练，未写入任何数据。确认无误后加 --apply 执行。")
            return

        # ── 4. 备份后写入 ──
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = BACKUP_DIR / f"backfill-change-reason-{stamp}.json"
        backup.write_text(json.dumps({"plan": plan, "policyMissing": policy_missing},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已备份将改动的行 → {backup}")

        result_ids = [i["result_id"] for i in plan]
        # ⛔ psycopg3 的 `execute` **不做** executemany：传 [(a,b), …] 会被当成
        # 一次调用的参数序列 ⇒ 报 "query has 2 placeholders but 3 parameters were
        # passed"。批量更新必须用 `executemany`。
        cur.executemany(
            "update survey_cbf_result set change_reason = %s where id = %s",
            [(item["new_result_reason"], item["result_id"]) for item in plan],
        )
        member_rows = [(m["reason"], m["id"]) for item in plan for m in item["members"]]
        if member_rows:
            cur.executemany(
                "update survey_cbf_jtcy_result set change_reason = %s where id = %s", member_rows
            )
        parcel_rows = [(p["reason"], p["id"]) for item in plan for p in item["parcels"]]
        if parcel_rows:
            cur.executemany(
                "update survey_cbdkxx_result set change_reason = %s where id = %s", parcel_rows
            )
        if args.policy_basis:
            cur.execute(
                "update survey_cbf_result set policy_basis = %s where id = any(%s)",
                (args.policy_basis, result_ids),
            )
        conn.commit()
        print(f"完成：承包方 {len(plan)} 行、成员 {len(member_rows)} 行、地块 {len(parcel_rows)} 行已更新。")


if __name__ == "__main__":
    main()
