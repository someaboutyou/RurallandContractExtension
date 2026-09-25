# -*- coding: utf-8 -*-
"""验收（第二批）：注销 / 撤回注销 / 确认 / 删除户残留，仍只在临时户上做。

T6  注销（pending）→ diffs 记录 → 撤回注销 → diffs 回到基线 + 状态还原
T7  确认调查结果 → 已确认后不能再保存（400）
T8  删除承包方后，其地块编码是否仍被占用（⇒ 地块/关联行未连带清理）

跑法：runtime/windows/python/python.exe scripts/_verify_survey_rollback2.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "runtime" / ".state" / "_verify_survey_rollback2.txt"

os.environ.setdefault("SECRET_KEY", "verify-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = create_access_token("1")
BATCH_ID = 41
TEMP_C = "321324100001029921"
TEMP_D = "321324100001029922"

OUT: list[str] = []
FAILED: list[str] = []


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
        f"{BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json; charset=utf-8"},
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
        return None, f"{type(exc).__name__}: {exc}"


def brief(payload, limit: int = 260) -> str:
    return str(payload)[:limit]


def get_detail(uid):
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")
    return payload.get("data") if status == 200 and isinstance(payload, dict) else {}


def get_diffs(uid):
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/diffs?page=1&page_size=500")
    return ((payload.get("data") or {}).get("items") or []) if status == 200 and isinstance(payload, dict) else []


def get_parcels(uid):
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels")
    return (payload.get("data") or []) if status == 200 and isinstance(payload, dict) else []


def labels(diffs):
    return [f"{d.get('entityType')}:{d.get('fieldLabel')}" for d in diffs]


def next_parcel_code(uid):
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    if status == 200 and isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict):
            return data.get("code") or data.get("dkbm") or ""
        return str(data)
    return ""


def members_payload(members):
    return [{
        "memberUid": m.get("memberUid"), "name": m.get("name"),
        "gender": m.get("gender") or "1", "idType": m.get("idType") or "1",
        "idNo": m.get("idNo"), "relationToHead": m.get("relationToHead") or "01",
        "noteCode": m.get("noteCode"), "isCoOwner": m.get("isCoOwner"), "note": m.get("note"),
        "memberResultStatus": m.get("memberResultStatus") or "normal",
        "isHouseholdHead": bool(m.get("isHouseholdHead")), "changeReason": m.get("changeReason"),
    } for m in members]


def payload_of(detail, *, members=None, pending=None, **over):
    body = {
        "code": detail.get("code"), "typeCode": detail.get("typeCode") or "1",
        "name": detail.get("name"), "idType": detail.get("idType") or "1",
        "idNo": detail.get("idNo"), "address": detail.get("address"),
        "postcode": detail.get("postcode") or "000000", "mobile": detail.get("mobile"),
        "surveyDate": detail.get("surveyDate"), "surveyorName": detail.get("surveyorName"),
        "surveyNote": detail.get("surveyNote"), "publicNoticeNote": detail.get("publicNoticeNote"),
        "publicNoticeRecorder": detail.get("publicNoticeRecorder"),
        "publicNoticeReviewDate": detail.get("publicNoticeReviewDate"),
        "publicNoticeReviewer": detail.get("publicNoticeReviewer"),
        "groupRegionCode": detail.get("groupRegionCode"), "groupRegionName": detail.get("groupRegionName"),
        "surveyStatus": detail.get("surveyStatus") or "surveyed",
        "resultStatus": detail.get("resultStatus") or "normal",
        "changeType": detail.get("changeType") or "none",
        "changeReason": detail.get("changeReason"), "policyBasis": detail.get("policyBasis"),
        "evidenceSummary": detail.get("evidenceSummary"), "remark": detail.get("remark"),
        "familyMembers": members if members is not None else members_payload(detail.get("familyMembers") or []),
        "deletedMembers": [], "pendingOperations": pending or [],
    }
    body.update(over)
    return body


def put(uid, detail, **kw):
    return api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT", body=payload_of(detail, **kw))


def cleanup(code):
    status, payload = api(f"/contractors/{code}", method="DELETE")
    log(f"  清理 {code} -> {status} {brief(payload, 120)}")


def add_parcel_op(code, name):
    return {"type": "add_parcel", "payload": {
        "dkbm": code, "dkmc": name, "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": "1000", "sfjbnt": "1", "reason": "验收地块"}}


def setup(code, name):
    log(f"\n--- 建临时户 {code} ---")
    api(f"/contractors/{code}", method="DELETE")
    status, payload = api(f"/surveys/batches/{BATCH_ID}/tasks", method="POST", body={
        "code": code, "typeCode": "1", "name": name, "idType": "1",
        "idNo": "320324199001019920", "address": "验收临时地址", "postcode": "223900",
        "mobile": "13900000000", "surveyorName": "验收脚本", "surveyDate": "2026-09-24",
        "remark": "rollback verify fixture 2",
    })
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return ""
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    members.append({"name": "验收成员甲", "gender": "1", "idType": "1", "idNo": "320324199001019921",
                    "relationToHead": "01", "isHouseholdHead": True})
    put(uid, detail, members=members)
    check(f"建户 {code} 成功", bool(uid), f"uid={uid}")
    return uid


def case_t6(uid):
    log("\n=== T6 注销（pending）→ diffs → 撤回注销 → diffs/状态回基线 ===")
    detail = get_detail(uid)
    baseline = labels(get_diffs(uid))
    before_status = detail.get("resultStatus")
    log(f"  基线 diffs({len(baseline)}): {baseline} / resultStatus={before_status}")

    status, resp = put(uid, detail, pending=[{"type": "deregister", "payload": {"reason": "验收注销"}}])
    check("注销 PUT 200", status == 200, f"-> {status} {brief(resp)}")
    after = get_detail(uid)
    check("result_status 变为 cancelled", after.get("resultStatus") == "cancelled",
          f"-> {after.get('resultStatus')} / changeType={after.get('changeType')}")
    diffs = get_diffs(uid)
    log(f"  注销后 diffs({len(diffs)}): {labels(diffs)}")
    check("diffs 出现承包方状态变更行",
          any(d.get("fieldName") == "result_status" for d in diffs), f"-> {labels(diffs)}")

    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/rollback-deregister", method="POST")
    check("撤回注销 API 200", status == 200, f"-> {status} {brief(resp)}")
    back = get_detail(uid)
    check(f"撤回注销后 result_status 回到注销前的 {before_status}",
          back.get("resultStatus") == before_status,
          f"-> {back.get('resultStatus')} / changeType={back.get('changeType')}")
    diffs2 = get_diffs(uid)
    log(f"  撤回后 diffs({len(diffs2)}): {labels(diffs2)}")
    check("撤回注销后 diffs 回到基线", labels(diffs2) == baseline, f"-> {labels(diffs2)}")


def case_t7(uid):
    log("\n=== T7 确认调查结果 → 已确认后不可再保存 ===")
    d = get_detail(uid)
    members = members_payload(d.get("familyMembers") or [])
    # 确认校验：member_result_status != normal 的成员必须各自填变化原因
    for m in members:
        m["changeReason"] = m.get("changeReason") or "验收成员变化原因"
    status, resp = put(uid, d, members=members,
                       surveyStatus="surveyed", changeReason="验收变化", policyBasis="验收政策依据")
    check("先保存为 surveyed 200", status == 200, f"-> {status} {brief(resp)}")
    saved = get_detail(uid)
    check("survey_status = surveyed", saved.get("surveyStatus") == "surveyed",
          f"-> {saved.get('surveyStatus')}")
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/confirm", method="POST")
    check("确认 API 200", status == 200, f"-> {status} {brief(resp)}")
    conf = get_detail(uid)
    check("survey_status = confirmed", conf.get("surveyStatus") == "confirmed",
          f"-> {conf.get('surveyStatus')}")
    if status == 200:
        d2 = get_detail(uid)
        status, resp = put(uid, d2, name="确认后改名")
        check("已确认后保存被拒（期望 400）", status == 400, f"-> {status} {brief(resp)}")


def case_t8():
    log("\n=== T8 删除承包方 → 其地块编码是否仍被占用 ===")
    uid = setup(TEMP_D, "验收临时户D")
    if not uid:
        return
    code = next_parcel_code(uid)
    if not code:
        check("取地块编码", False)
        return
    d = get_detail(uid)
    status, resp = put(uid, d, pending=[add_parcel_op(code, "验收残留地块")])
    check("加地块 200", status == 200, f"-> {status} {brief(resp)}")
    check("地块已存在", len(get_parcels(uid)) >= 1, f"-> {len(get_parcels(uid))}")
    cleanup(TEMP_D)

    uid2 = setup(TEMP_D, "验收临时户D2")
    if not uid2:
        return
    d2 = get_detail(uid2)
    status, resp = put(uid2, d2, pending=[add_parcel_op(code, "验收复用地块")])
    log(f"  复用同一地块编码 {code} -> {status} {brief(resp)}")
    check("删除户后地块编码仍被占用（⇒ 地块/关联行未连带清理）",
          status == 400 and "already exists" in str(resp), f"-> {status} {brief(resp)}")
    cleanup(TEMP_D)


def main():
    log("=" * 72)
    log("承包方调查录入 —— 注销 / 撤回注销 / 确认 / 删除残留 验收")
    log("=" * 72)
    cleanup(TEMP_C)
    cleanup(TEMP_D)

    uid = setup(TEMP_C, "验收临时户C")
    if uid:
        case_t6(uid)
        case_t7(uid)
        cleanup(TEMP_C)
    case_t8()

    log("\n" + "=" * 72)
    log(f"结论：{'全部通过' if not FAILED else '存在失败项 -> ' + ', '.join(FAILED)}")
    OUT_PATH.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n（完整日志：{OUT_PATH}）")


if __name__ == "__main__":
    main()
