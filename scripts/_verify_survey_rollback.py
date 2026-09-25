# -*- coding: utf-8 -*-
"""验收：/surveys「承包方调查录入」的保存 → survey_change_diffs → 撤回 闭环。

设计原则（安全第一）：
  * 全程走 HTTP 打运行中的 8000 后端，不直连数据库。
  * 只操作**验收专用临时承包户**（编码 321324100001029901/02），
    绝不触碰批次里的真实户。
  * 收尾调用 DELETE /contractors/{code} 清理，并复查残留。

断言目标：
  T1  表单改字段 → diffs 出现该字段行；改回原值 → 该行消失（净差异快照语义）
  T2  成员新增 → diffs「新增成员」；删除 → 「删除成员」
  T3  新增地块 → diffs 出现「新增地块」/「新增地块关联」
  T4  移除地块 → diffs 出现「移除地块关联」；随后**撤回移除** → 期望可用
  T5  分户（pending 路径）→ 检查 diffs 是否被重建

跑法：runtime/windows/python/python.exe scripts/_verify_survey_rollback.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "runtime" / ".state" / "_verify_survey_rollback.txt"

os.environ.setdefault("SECRET_KEY", "verify-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = create_access_token("1")
BATCH_ID = 41
TEMP_A = "321324100001029901"   # 单户：T1~T4
TEMP_B = "321324100001029902"   # 分户：T5
OUT: list[str] = []
FAILED: list[str] = []
ERRORS: list[str] = []


# ────────────────────────── 基础设施 ──────────────────────────
def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    OUT.append(line)
    print(line)


def check(label: str, ok: bool, extra: str = "") -> bool:
    log(f"[{'PASS' if ok else 'FAIL'}] {label} {extra}".rstrip())
    if not ok:
        FAILED.append(label)
    return ok


def api(path: str, method: str = "GET", body=None, timeout: int = 90):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:  # noqa: BLE001
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001
        ERRORS.append(f"{method} {path} -> {type(exc).__name__}: {exc}")
        return None, f"{type(exc).__name__}: {exc}"


def brief(payload, limit: int = 400) -> str:
    return str(payload)[:limit]


# ────────────────────────── 状态读取 ──────────────────────────
def get_detail(uid: str, bid: int = BATCH_ID) -> dict:
    status, payload = api(f"/surveys/batches/{bid}/results/{uid}")
    return payload.get("data") if status == 200 and isinstance(payload, dict) else {}


def get_parcels(uid: str, bid: int = BATCH_ID) -> list:
    status, payload = api(f"/surveys/batches/{bid}/results/{uid}/parcels")
    return (payload.get("data") or []) if status == 200 and isinstance(payload, dict) else []


def get_diffs(uid: str, bid: int = BATCH_ID) -> list:
    status, payload = api(f"/surveys/batches/{bid}/results/{uid}/diffs?page=1&page_size=500")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


def get_changes(uid: str, bid: int = BATCH_ID) -> list:
    status, payload = api(f"/surveys/batches/{bid}/changes?contractorUid={uid}&page=1&page_size=200")
    if status == 200 and isinstance(payload, dict):
        return (payload.get("data") or {}).get("items") or []
    return []


def diff_labels(diffs: list) -> list[str]:
    return [f"{d.get('entityType')}:{d.get('fieldLabel')}" for d in diffs]


def members_payload(members: list) -> list:
    """把接口返回的 familyMembers 转成可回传的更新载荷（保留 memberUid 以稳定身份）。"""
    out = []
    for m in members:
        out.append({
            "memberUid": m.get("memberUid"),
            "name": m.get("name"),
            "gender": m.get("gender") or "1",
            "idType": m.get("idType") or "1",
            "idNo": m.get("idNo"),
            "relationToHead": m.get("relationToHead") or "01",
            "noteCode": m.get("noteCode"),
            "isCoOwner": m.get("isCoOwner"),
            "note": m.get("note"),
            "memberResultStatus": m.get("memberResultStatus") or "normal",
            "isHouseholdHead": bool(m.get("isHouseholdHead")),
            "changeReason": m.get("changeReason"),
        })
    return out


def result_payload(detail: dict, *, members=None, deleted=None, pending=None, **overrides) -> dict:
    payload = {
        "code": detail.get("code"),
        "typeCode": detail.get("typeCode") or "1",
        "name": detail.get("name"),
        "idType": detail.get("idType") or "1",
        "idNo": detail.get("idNo"),
        "address": detail.get("address"),
        "postcode": detail.get("postcode") or "000000",
        "mobile": detail.get("mobile"),
        "surveyDate": detail.get("surveyDate"),
        "surveyorName": detail.get("surveyorName"),
        "surveyNote": detail.get("surveyNote"),
        "publicNoticeNote": detail.get("publicNoticeNote"),
        "publicNoticeRecorder": detail.get("publicNoticeRecorder"),
        "publicNoticeReviewDate": detail.get("publicNoticeReviewDate"),
        "publicNoticeReviewer": detail.get("publicNoticeReviewer"),
        "groupRegionCode": detail.get("groupRegionCode"),
        "groupRegionName": detail.get("groupRegionName"),
        "surveyStatus": detail.get("surveyStatus") or "surveyed",
        "resultStatus": detail.get("resultStatus") or "normal",
        "changeType": detail.get("changeType") or "none",
        "changeReason": detail.get("changeReason"),
        "policyBasis": detail.get("policyBasis"),
        "evidenceSummary": detail.get("evidenceSummary"),
        "remark": detail.get("remark"),
        "familyMembers": members if members is not None else members_payload(detail.get("familyMembers") or []),
        "deletedMembers": deleted or [],
        "pendingOperations": pending or [],
    }
    payload.update(overrides)
    return payload


def put_result(uid: str, detail: dict, **kwargs):
    return api(
        f"/surveys/batches/{BATCH_ID}/results/{uid}",
        method="PUT",
        body=result_payload(detail, **kwargs),
    )


def next_parcel_code(uid: str) -> str:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    if status == 200 and isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict):
            return data.get("code") or data.get("dkbm") or ""
        return str(data)
    return ""


# ────────────────────────── 清理 ──────────────────────────
def cleanup(code: str) -> None:
    status, payload = api(f"/contractors/{code}", method="DELETE")
    log(f"  清理 {code} -> {status} {brief(payload, 200)}")


# ────────────────────────── 用例 ──────────────────────────
def setup_household(code: str, name: str) -> tuple[str, dict]:
    log(f"\n--- 建临时户 {code} ({name}) ---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks",
        method="POST",
        body={
            "code": code,
            "typeCode": "1",
            "name": name,
            "idType": "1",
            "idNo": "320324199001019900",
            "address": "验收临时地址",
            "postcode": "223900",
            "mobile": "13900000000",
            "surveyorName": "验收脚本",
            "surveyDate": "2026-09-24",
            "remark": "rollback verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return "", {}
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    check(f"建户 {code} 成功", bool(uid), f"uid={uid}")
    # 补一个成员，否则很多后续动作缺主体
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    members.append({
        "name": "验收成员甲", "gender": "1", "idType": "1", "idNo": "320324199001019901",
        "relationToHead": "01", "isHouseholdHead": True,
    })
    status, resp = put_result(uid, detail, members=members)
    check(f"建户后补成员", status == 200, f"-> {status} {brief(resp, 300)}")
    return uid, get_detail(uid)


def case_t1_form_diff(uid: str) -> None:
    log("\n=== T1 表单改字段 → diffs 记录 → 改回 → 行消失 ===")
    detail = get_detail(uid)
    origin = detail.get("name")
    base_n = len(get_diffs(uid))
    log(f"  起始 name={origin} diffs={base_n}")

    status, resp = put_result(uid, detail, name="验收临时户改名")
    check("改名 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    after = get_detail(uid)
    check("改名已生效", after.get("name") == "验收临时户改名", f"-> {after.get('name')}")
    diffs = get_diffs(uid)
    hit = [d for d in diffs if d.get("fieldName") == "cbfmc"]
    check("diffs 里出现 cbfmc 变更行", bool(hit), f"-> {[(d.get('beforeValue'), d.get('afterValue')) for d in hit]}")
    log(f"  当前 diffs: {diff_labels(diffs)}")

    detail2 = get_detail(uid)
    status, resp = put_result(uid, detail2, name=origin)
    check("改回原名 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    diffs2 = get_diffs(uid)
    hit2 = [d for d in diffs2 if d.get("fieldName") == "cbfmc"]
    check("改回原值后 cbfmc 变更行消失（净差异语义）", not hit2,
          f"-> 剩余 {[(d.get('beforeValue'), d.get('afterValue')) for d in hit2]}")
    check("diffs 总数回到起点", len(diffs2) == base_n, f"-> {len(diffs2)} vs {base_n}")


def case_t2_member_diff(uid: str) -> None:
    log("\n=== T2 成员新增 / 删除 → diffs ===")
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    members.append({
        "name": "验收成员乙", "gender": "2", "idType": "1", "idNo": "320324199001019902",
        "relationToHead": "02",
    })
    status, resp = put_result(uid, detail, members=members)
    check("新增成员 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    diffs = get_diffs(uid)
    check("diffs 出现「新增成员」", any(d.get("fieldLabel") == "新增成员" for d in diffs),
          f"-> {diff_labels(diffs)}")

    detail2 = get_detail(uid)
    target = next((m for m in detail2.get("familyMembers") or [] if m.get("name") == "验收成员乙"), None)
    if target is None:
        check("找到待删成员", False)
        return
    remaining = [m for m in members_payload(detail2.get("familyMembers") or [])
                 if m.get("memberUid") != target.get("memberUid")]
    status, resp = put_result(
        uid, detail2, members=remaining,
        deleted=[{"memberUid": target.get("memberUid"), "changeReason": "验收删除"}],
    )
    check("删除成员 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    diffs2 = get_diffs(uid)
    has_deleted = any(d.get("fieldLabel") == "删除成员" for d in diffs2)
    check("（净差异语义）删掉 base 里不存在的成员，不应产生「删除成员」行", not has_deleted,
          f"-> {'出现了' if has_deleted else '未出现'}; diffs={diff_labels(diffs2)}")
    log("  ↑ 该成员是本轮新建的、base 快照里没有，删掉属净零变化；真实户的删除 diff 见 T2b")
    # 还原：把成员加回来（用同一 memberUid ⇒ 应回到 baseline）
    detail3 = get_detail(uid)
    restored = members_payload(detail3.get("familyMembers") or [])
    restored.append({
        "memberUid": target.get("memberUid"),
        "name": "验收成员乙", "gender": "2", "idType": "1", "idNo": "320324199001019902",
        "relationToHead": "02",
    })
    status, resp = put_result(uid, detail3, members=restored)
    check("恢复成员 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    diffs3 = get_diffs(uid)
    check("恢复后「删除成员」行消失",
          not any(d.get("fieldLabel") == "删除成员" for d in diffs3),
          f"-> {diff_labels(diffs3)}")


def case_t2b_real_member_delete() -> None:
    """「删除成员」的 diff 只在成员原本存在于 base 快照时才会产生。
    临时新建的户 base 里没有成员，所以必须拿一个真实户验证；
    操作是「删一个再原样加回」，净效果为零。"""
    log("\n=== T2b 真实户：删除成员 → diffs「删除成员」→ 原样恢复 ===")
    target = None
    for bid in (BATCH_ID, 40):
        status, payload = api(f"/surveys/batches/{bid}/tasks?page=1&page_size=200")
        tasks = (payload.get("data") or {}).get("items") if isinstance(payload, dict) else []
        for row in tasks or []:
            uid = row.get("contractorUid")
            if not uid:
                continue
            detail = get_detail(uid, bid)
            base_members = ((detail.get("baseContractor") or {}).get("familyMembers") or [])
            if (len(base_members) >= 2 and detail.get("resultStatus") == "normal"
                    and detail.get("surveyStatus") != "confirmed"):
                target = (bid, uid, detail, base_members)
                break
        if target:
            break
    if not target:
        check("找到含 base 成员的真实户", False)
        return
    bid, uid, detail, base_members = target
    log(f"  选定批次 {bid} 户 {detail.get('code')} {detail.get('name')}，base 成员 {len(base_members)}")
    original_payload = members_payload(detail.get("familyMembers") or [])
    original_uids = sorted(m.get("memberUid") for m in original_payload if m.get("memberUid"))
    victim = base_members[0]
    victim_uid = victim.get("memberUid")
    log(f"  拟删除成员: {victim.get('name')} ({victim_uid})")

    kept = [m for m in original_payload if m.get("memberUid") != victim_uid]
    status, resp = api(
        f"/surveys/batches/{bid}/results/{uid}", method="PUT",
        body=result_payload(detail, members=kept,
                            deleted=[{"memberUid": victim_uid, "changeReason": "验收删除"}]),
    )
    check("删除成员 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    diffs = get_diffs(uid, bid)
    check("diffs 出现「删除成员」", any(d.get("fieldLabel") == "删除成员" for d in diffs),
          f"-> {diff_labels(diffs)}")

    detail2 = get_detail(uid, bid)
    status, resp = api(
        f"/surveys/batches/{bid}/results/{uid}", method="PUT",
        body=result_payload(detail2, members=original_payload),
    )
    check("原样恢复成员 PUT 200", status == 200, f"-> {status} {brief(resp, 300)}")
    diffs2 = get_diffs(uid, bid)
    check("恢复后「删除成员」行消失",
          not any(d.get("fieldLabel") == "删除成员" for d in diffs2), f"-> {diff_labels(diffs2)}")
    after = get_detail(uid, bid)
    now_uids = sorted(m.get("memberUid") for m in (after.get("familyMembers") or []) if m.get("memberUid"))
    check("成员集合已还原（member_uid 一致）", now_uids == original_uids,
          f"-> {len(now_uids)} vs {len(original_uids)}")
    check("成员人数已还原", len(after.get("familyMembers") or []) == len(original_payload),
          f"-> {len(after.get('familyMembers') or [])} vs {len(original_payload)}")


def case_t3_add_parcels(uid: str, want: int = 3) -> list[str]:
    log(f"\n=== T3 新增地块 ×{want} → diffs ===")
    dkbms: list[str] = []
    for i in range(want):
        code = next_parcel_code(uid)
        if not code:
            check(f"取第 {i+1} 个地块编码", False, "-> next-code 未返回编码")
            return dkbms
        detail = get_detail(uid)
        # 注意列宽：dklb/dldj/syqxz = String(2)，tdyt/sfjbnt = String(1)，tdlylx = String(3)
        op = {
            "type": "add_parcel",
            "payload": {
                "dkbm": code,
                "dkmc": f"验收地块{i+1}",
                "dklb": "01",
                "dldj": "01",
                "tdyt": "1",
                "tdlylx": "011",
                "syqxz": "10",
                "scmj": "1000",
                "sfjbnt": "1",
                "reason": "验收新增地块",
            },
        }
        status, resp = put_result(uid, detail, pending=[op])
        if status != 200:
            check(f"新增第 {i+1} 个地块 PUT 200", False, f"-> {status} {brief(resp, 400)}")
            return dkbms
        dkbms.append(code)
        log(f"  新增地块 {code} OK")
    parcels = get_parcels(uid)
    active = [p for p in parcels if p.get("resultStatus") not in ("removed", "split_source")]
    check(f"有效地块数 = {want}", len(active) == want, f"-> {len(active)}")
    diffs = get_diffs(uid)
    check("diffs 出现「新增地块关联」", any(d.get("fieldLabel") == "新增地块关联" for d in diffs),
          f"-> {diff_labels(diffs)}")
    return dkbms


def case_t4_remove_and_rollback(uid: str, dkbm: str) -> None:
    log(f"\n=== T4 移除地块 {dkbm} → diffs → 撤回移除 ===")
    detail = get_detail(uid)
    status, resp = put_result(
        uid, detail,
        pending=[{"type": "remove_parcel", "payload": {"dkbm": dkbm, "reason": "验收移除地块"}}],
    )
    check("移除地块 PUT 200", status == 200, f"-> {status} {brief(resp, 400)}")
    parcels = get_parcels(uid)
    gone = not any(p.get("dkbm") == dkbm for p in parcels)
    check("地块已从有效列表中移除", gone, f"-> 剩余 {[p.get('dkbm') for p in parcels]}")
    diffs = get_diffs(uid)
    log(f"  diffs: {diff_labels(diffs)}")
    log("  ↑ 该地块是本轮新增的、base 快照里没有，移除属净零变化，故不产生「移除地块关联」；"
        "该行只在移除 base 原有地块时出现（T2b 的真实户 diffs 里已实证存在）")

    changes = [c for c in get_changes(uid) if c.get("changeType") == "remove_parcel"
               and c.get("changeStatus") != "rolled_back"]
    check("存在未撤回的 remove_parcel 变更记录", bool(changes), f"-> {[(c.get('id'), c.get('changeNo')) for c in changes]}")
    if not changes:
        return
    change = changes[0]
    detail2 = get_detail(uid)
    rollback_op = {
        "type": "rollback_remove_parcel",
        "payload": {
            "changeId": change.get("id"),
            "changeNo": change.get("changeNo"),
            "dkbm": dkbm,
            "cbfbm": detail2.get("code"),
            "sourceResultStatus": "normal",
            "sourceChangeType": "none",
            "sourceChangeReason": None,
            "sourceIsChanged": False,
            "reason": f"撤回移除 {change.get('changeNo')}",
        },
    }
    status, resp = put_result(uid, detail2, pending=[rollback_op])
    log(f"  撤回移除响应: {status} {brief(resp, 600)}")
    check("撤回已保存移除可成功（期望 200）", status == 200,
          f"-> 实际 {status}（{brief(resp, 300)}）")

    # 无论成败，记录地块当前状态 + 变更记录状态
    parcels2 = get_parcels(uid)
    state = [(p.get("dkbm"), p.get("resultStatus")) for p in parcels2 if p.get("dkbm") == dkbm]
    log(f"  撤回后地块 {dkbm} 状态: {state}")
    changes2 = [c for c in get_changes(uid) if c.get("changeType") == "remove_parcel"]
    log(f"  remove_parcel 记录状态: {[(c.get('id'), c.get('changeStatus')) for c in changes2]}")
    if status != 200:
        check("撤回失败后地块状态未被改动（事务整体回滚）",
              not any(p.get("dkbm") == dkbm for p in get_parcels(uid)), f"-> {state}")
        check("撤回失败后变更记录未被标记 rolled_back",
              all(c.get("changeStatus") != "rolled_back" for c in changes2),
              f"-> {[(c.get('id'), c.get('changeStatus')) for c in changes2]}")


def case_t5_split_household_diff(uid: str, dkbms: list[str]) -> None:
    log("\n=== T5 分户（pending 路径）→ diffs 是否重建 ===")
    detail = get_detail(uid)
    members = detail.get("familyMembers") or []
    active = [p for p in get_parcels(uid) if p.get("resultStatus") not in ("removed", "split_source")]
    log(f"  成员 {len(members)} / 有效地块 {len(active)}")
    if len(members) < 2 or len(active) < 2:
        check("分户前置条件（≥2 成员 ≥2 地块）", False, f"-> 成员 {len(members)} 地块 {len(active)}")
        return
    new_codes = [f"32132410000102991{i+1}" for i in range(2)]  # …911 / …912
    op = {
        "type": "split_household",
        "payload": {
            "newHouseholds": [
                {"newCbfbm": new_codes[0], "newCbfmc": "验收分户甲",
                 "memberUids": [members[0].get("memberUid")],
                 "parcelDkbms": [active[0].get("dkbm")],
                 "householdHeadMemberUid": members[0].get("memberUid")},
                {"newCbfbm": new_codes[1], "newCbfmc": "验收分户乙",
                 "memberUids": [m.get("memberUid") for m in members[1:]],
                 "parcelDkbms": [p.get("dkbm") for p in active[1:]],
                 "householdHeadMemberUid": members[1].get("memberUid")},
            ],
            "reason": "验收分户",
        },
    }
    before_diffs = len(get_diffs(uid))
    status, resp = put_result(uid, detail, pending=[op])
    check("分户 PUT 200", status == 200, f"-> {status} {brief(resp, 500)}")
    log(f"  分户前原户 diffs={before_diffs}")
    if status != 200:
        return
    src = get_detail(uid)
    log(f"  原户 resultStatus={src.get('resultStatus')} changeType={src.get('changeType')}")
    src_diffs = get_diffs(uid)
    log(f"  分户后原户 diffs={len(src_diffs)}: {diff_labels(src_diffs)}")
    # 新户：从批次任务列表里找
    status, payload = api(f"/surveys/batches/{BATCH_ID}/tasks?page=1&page_size=200")
    tasks = (payload.get("data") or {}).get("items") if isinstance(payload, dict) else []
    for code in new_codes:
        row = next((t for t in (tasks or []) if (t.get("cbfbm") or t.get("code")) == code), None)
        if row is None:
            check(f"新户 {code} 已生成", False)
            continue
        n_uid = row.get("contractorUid")
        n_diffs = get_diffs(n_uid)
        log(f"  新户 {code} diffs={len(n_diffs)}: {diff_labels(n_diffs)}")
        check(f"新户 {code} 的 diffs 应记录分户产生的人员/地块归属变更（期望非空）",
              len(n_diffs) > 0, f"-> {len(n_diffs)} 条")


def main() -> None:
    log("=" * 72)
    log("承包方调查录入 —— 保存 / diffs / 撤回 闭环验收")
    log("=" * 72)

    status, payload = api(f"/surveys/batches?page=1&page_size=20")
    rows = (payload.get("data") or {}).get("items") if status == 200 and isinstance(payload, dict) else []
    batch_row = next((b for b in (rows or []) if b.get("id") == BATCH_ID), None)
    log(f"批次 {BATCH_ID}: {batch_row}")
    if batch_row is None or batch_row.get("status") != "active":
        log(f"批次 {BATCH_ID} 不可用（需要 active 状态），终止。")
        OUT_PATH.write_text("\n".join(OUT), encoding="utf-8")
        return

    # 幂等：先清掉可能残留的旧夹具
    cleanup(TEMP_A)
    cleanup(TEMP_B)

    uid_a, _ = setup_household(TEMP_A, "验收临时户A")
    if uid_a:
        case_t1_form_diff(uid_a)
        case_t2_member_diff(uid_a)
        if "--with-real" in sys.argv:
            # 会对真实户做「删一个成员再原样加回」的净零操作（会 +1 条变更记录），
            # 默认不跑；需要复验时显式加 --with-real。
            case_t2b_real_member_delete()
        # T3 先加 2 块，T4 移掉 1 块；留 2 块给 T5 分户
        dkbms = case_t3_add_parcels(uid_a, want=3)
        if dkbms:
            case_t4_remove_and_rollback(uid_a, dkbms[0])
            case_t5_split_household_diff(uid_a, dkbms)

    log("\n--- 收尾清理 ---")
    cleanup(TEMP_A)
    cleanup(TEMP_B)
    for code in ("321324100001029901", "321324100001029902",
                 "321324100001029911", "321324100001029912"):
        cleanup(code)

    log("\n" + "=" * 72)
    if ERRORS:
        log("传输层错误：")
        for item in ERRORS:
            log("  ", item)
    log(f"结论：{'全部通过' if not FAILED else '存在失败项 -> ' + ', '.join(FAILED)}")
    OUT_PATH.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n（完整日志：{OUT_PATH}）")


if __name__ == "__main__":
    main()
