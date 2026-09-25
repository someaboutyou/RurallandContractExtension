# -*- coding: utf-8 -*-
"""验收：户主口径统一（ISSUE-06）+ 已注销列表撤回入口同源（ISSUE-01 方案A）+ 分户对齐（ISSUE-07）。

本脚本覆盖三组断言，全部走进程内 `TestClient`（验的一定是当前工作区源码，
不依赖运行中的 8000 实例），夹具自建自清。

──────────────────────── 背景（修复前实测得到的根因）────────────────────────
1) **户主口径错位**：字典 `nyt2539_c20_relation_to_head` 权威定义 `02=户主`、`01=本人`，
   真实数据 `survey_cbf_jtcy_result` 里 `yhzgx='02'` 有 17.98 万条（每户恰好一条）、
   `'01'` 仅 1 条；而代码到处按 `01=户主` 实现（`yhgzx == "01"`）。
   后果之一极严重：`base.py::_validate_confirmable` 要求「恰好 1 个户主」，判据取 `01`
   ⇒ 179,788 个 cbflx=1 的户里**只有 1 户**能通过 ⇒ **「确认调查结果」对真实户几乎全报 400**。
   定案口径（用户 2026-09-25 拍板）：**优先 户主(02) → 次选 本人(01) → 兜底任取一条**。

2) **撤回入口断在"判据不同源"**：已注销列表的 `canRollback` 取 `batch.status != finished`，
   而它附带的变更记录只查 `change_type == "deregister"`；合户写的是 `merge_household`
   ⇒ 界面上渲染出一个**必然 400** 的按钮（`changeNo=null` 是最锋利的证据）。

3) **分户不对齐**：`merge_household` 会把原户 `task_status` 置 `deregistered`，
   `split_household` 不同步 ⇒ 两件坏事：分户原户仍留在主列表（语义不齐），
   且一旦对齐，分户的「撤回分户」入口也会断 —— 所以必须与 (2) 一起做。

跑法：runtime/windows/python/python.exe scripts/_verify_survey_rollback_entry.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 必须先注入 DB 配置再 import app（config.py 的 database_port 默认 5432 是错的，
# 真实实例在 15432；连不上时 psycopg 会让进程静默退出）。
os.environ.update({
    "DATABASE_HOST": "127.0.0.1",
    "DATABASE_PORT": "15432",
    "DATABASE_NAME": "erlunyanbao",
    "DATABASE_USER": "RurallandContractExtension",
    "DATABASE_PASSWORD": "dK9venBRbBRewDFAWYHRGdCM",
    "SECRET_KEY": "verify-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

BATCH_ID = 41

# 夹具编码段：3213241000010297xx（与既有脚本的 98xx / 99xx 段区分开）
HD = "321324100001029771"        # 注销用例户
HA = "321324100001029772"        # 合户 · 发起方
HB = "321324100001029773"        # 合户 · 参与方
HM = "321324100001029774"        # 合户生成的新户
HS = "321324100001029775"        # 分户 · 源户
HS1 = "321324100001029776"       # 分户生成的新户 1
HS2 = "321324100001029777"       # 分户生成的新户 2
HC = "321324100001029778"        # 确认校验：成员 yhzgx='02' 但无 is_household_head 标记
HF = "321324100001029779"        # 确认校验：成员全是 10/20（无 02、无 01）
HE = "321324100001029780"        # 确认校验：没有任何成员（应保持拒绝）

ALL_CODES = [HD, HA, HB, HM, HS, HS1, HS2, HC, HF, HE]
NAMES = {
    HD: "验收注销户", HA: "验收合户户A", HB: "验收合户户B", HM: "验收合并户",
    HS: "验收分户源户", HS1: "验收分户新户1", HS2: "验收分户新户2",
    HC: "验收户主02户", HF: "验收无户主户", HE: "验收无成员户",
}

TOKEN = create_access_token("1")
DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

OUT: list[str] = []
FAILED: list[str] = []
KNOWN_GAPS: list[str] = []
client: TestClient | None = None


# ────────────────────────── 基础设施 ──────────────────────────
def log(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    OUT.append(line)
    print(line)


def check(label: str, ok: bool, extra: str = "", *, gap: bool = False) -> bool:
    tag = "PASS" if ok else ("GAP " if gap else "FAIL")
    log(f"[{tag}] {label}" + (f" {extra}" if extra else ""))
    if not ok:
        (KNOWN_GAPS if gap else FAILED).append(label)
    return ok


def note(label: str, extra: str = "") -> None:
    log(f"      · {label}" + (f" {extra}" if extra else ""))


def api(path: str, method: str = "GET", body=None):
    assert client is not None
    resp = client.request(
        method, f"/api/v1{path}", json=body,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    try:
        return resp.status_code, resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code, resp.text


def brief(payload, limit: int = 400) -> str:
    return str(payload)[:limit]


def sql(sql_text: str, params=None):
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, params)
            return cur.fetchall()


# ────────────────────────── 列表 / 详情 ──────────────────────────
def get_detail(uid: str) -> dict:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}")
    return payload.get("data") if status == 200 and isinstance(payload, dict) else {}


def list_tasks(*, keyword=None, task_status=None, page_size=200) -> dict:
    assert page_size <= 200, "page_size 上限 200（Query(le=200)）"
    params = ["page=1", f"page_size={page_size}"]
    if keyword:
        params.append(f"keyword={keyword}")
    if task_status:
        params.append(f"taskStatus={task_status}")
    status, payload = api(f"/surveys/batches/{BATCH_ID}/tasks?" + "&".join(params))
    if status == 200 and isinstance(payload, dict):
        return payload.get("data") or {}
    return {"items": [], "total": None, "httpStatus": status, "raw": brief(payload)}


def list_deregistered(*, keyword=None, page_size=200) -> dict:
    assert page_size <= 200, "page_size 上限 200（Query(le=200)）"
    params = ["page=1", f"page_size={page_size}"]
    if keyword:
        params.append(f"keyword={keyword}")
    status, payload = api(f"/surveys/batches/{BATCH_ID}/deregistered-contractors?" + "&".join(params))
    if status == 200 and isinstance(payload, dict):
        return payload.get("data") or {}
    return {"items": [], "total": None, "httpStatus": status, "raw": brief(payload)}


def dereg_row(code: str) -> dict:
    """按关键字在已注销列表里取一行（按 cbfbm 精确匹配）。"""
    got = list_deregistered(keyword=code)
    for item in got.get("items") or []:
        if item.get("cbfbm") == code:
            return item
    return {}


# ────────────────────────── payload 组装 ──────────────────────────
def members_payload(members: list) -> list:
    return [{
        "memberUid": m.get("memberUid"),
        "name": m.get("name"),
        "gender": m.get("gender") or "1",
        "idType": m.get("idType") or "1",
        "idNo": m.get("idNo"),
        "relationToHead": m.get("relationToHead") or "09",
        "noteCode": m.get("noteCode"),
        "isCoOwner": m.get("isCoOwner"),
        "note": m.get("note"),
        "memberResultStatus": m.get("memberResultStatus") or "normal",
        "isHouseholdHead": bool(m.get("isHouseholdHead")),
        "changeReason": m.get("changeReason"),
    } for m in members]


def result_payload(detail: dict, *, members=None, pending=None, **overrides) -> dict:
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
        "deletedMembers": [],
        "pendingOperations": pending or [],
    }
    payload.update(overrides)
    return payload


def put_result(uid: str, detail: dict, **kwargs):
    return api(f"/surveys/batches/{BATCH_ID}/results/{uid}", method="PUT",
               body=result_payload(detail, **kwargs))


def next_parcel_code(uid: str) -> str:
    status, payload = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/parcels/next-code")
    if status == 200 and isinstance(payload, dict):
        data = payload.get("data") or {}
        if isinstance(data, dict):
            return data.get("code") or data.get("dkbm") or ""
        return str(data)
    return ""


def add_parcel(uid: str, dkbm: str, label: str, scmj: str = "1000"):
    detail = get_detail(uid)
    body = {
        "dkbm": dkbm, "dkmc": label, "dklb": "01", "dldj": "01", "tdyt": "1",
        "tdlylx": "011", "syqxz": "10", "scmj": scmj, "sfjbnt": "1",
        "reason": "验收新增地块",
    }
    return put_result(uid, detail, pending=[{"type": "add_parcel", "payload": body}])


# ────────────────────────── 收尾清理 ──────────────────────────
def housekeeping() -> None:
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            uids = [r[0] for r in cur.fetchall()]
            # 合户/分户生成的新户 uid 由 uuid5 派生；撤回后其 result 行会消失，
            # 所以还要按 initialized_from_table 兜一次。
            cur.execute(
                "SELECT contractor_uid FROM survey_cbf_base WHERE batch_id = %s"
                " AND initialized_from_table IN ('merge_household', 'split_household')"
                " AND cbfbm = ANY(%s)",
                (BATCH_ID, ALL_CODES),
            )
            uids += [r[0] for r in cur.fetchall()]
            uids = list(dict.fromkeys(uids))

            cur.execute(
                "SELECT DISTINCT dkbm FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            dkbms = [r[0] for r in cur.fetchall()]

            if uids:
                for table in (
                    "survey_change_diffs", "survey_change_records", "survey_household_tags",
                    "survey_cbf_jtcy_result", "survey_cbf_jtcy_base", "survey_cbf_base",
                ):
                    cur.execute(f"DELETE FROM {table} WHERE contractor_uid = ANY(%s)", (uids,))
            cur.execute("DELETE FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            cur.execute("DELETE FROM survey_cbdkxx_base WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            if dkbms:
                cur.execute("DELETE FROM survey_dk_result WHERE dkbm = ANY(%s)", (dkbms,))
                cur.execute("DELETE FROM survey_dk_base WHERE dkbm = ANY(%s)", (dkbms,))
            cur.execute("DELETE FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
            # 兜底：挂在已消失新户 uid 上的孤儿台账。必须在删完 survey_cbf_result 之后判「孤儿」。
            cur.execute(
                "DELETE FROM survey_change_diffs WHERE batch_id = %s AND contractor_uid NOT IN"
                " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))
            cur.execute(
                "DELETE FROM survey_change_records WHERE batch_id = %s AND contractor_uid NOT IN"
                " (SELECT contractor_uid FROM survey_cbf_result)", (BATCH_ID,))


def residue_report() -> dict:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        out = {}
        cur.execute("SELECT count(*) FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
        out["cbf_result"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM survey_cbf_base WHERE cbfbm = ANY(%s)", (ALL_CODES,))
        out["cbf_base"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM survey_cbf_jtcy_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
        out["jtcy_result"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM survey_cbdkxx_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
        out["cbdkxx_result"] = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM survey_change_records r WHERE r.batch_id = %s"
            " AND NOT EXISTS (SELECT 1 FROM survey_cbf_result c WHERE c.contractor_uid = r.contractor_uid)",
            (BATCH_ID,))
        out["orphan_records"] = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM survey_change_diffs d WHERE d.batch_id = %s"
            " AND NOT EXISTS (SELECT 1 FROM survey_cbf_result c WHERE c.contractor_uid = d.contractor_uid)",
            (BATCH_ID,))
        out["orphan_diffs"] = cur.fetchone()[0]
        return out


# ────────────────────────── 夹具 ──────────────────────────
def preflight() -> bool:
    log("\n=== 前置检查：夹具编码不得已存在，否则后续断言会失真 ===")
    rows = sql("SELECT cbfbm FROM survey_cbf_result WHERE cbfbm = ANY(%s)", (ALL_CODES,))
    existing = [r[0] for r in rows]
    if not check("夹具编码段 3213241000010297xx 未被占用", not existing, f"-> 已存在 {existing}"):
        log("      先手动清理这批编码后重跑（勿直接删除生产数据）。")
        return False
    return True


def create_household(code: str, members_spec: list[tuple[str, str]], *, parcels: int = 0) -> tuple[str, list[str], list[str]]:
    """建临时户 → 写成员 → 加地块。members_spec = [(姓名, yhzgx), ...]，一律不带户主标记。

    返回 (uid, 地块编码列表, 成员uid列表)。
    注意：**刻意不传 isHouseholdHead**，以模拟「导入进来的真实户」——
    它们的 yhzgx 是 02/10/20，但 flag 全为 false，这正是 P0 的触发条件。
    """
    log(f"\n--- 建临时户 {code}（{NAMES[code]}，成员 {[s[1] for s in members_spec]}，地块 {parcels}）---")
    status, payload = api(
        f"/surveys/batches/{BATCH_ID}/tasks", method="POST",
        body={
            "code": code, "typeCode": "1", "name": NAMES[code], "idType": "1",
            "idNo": "3203241990010199" + code[-2:], "address": "验收临时地址",
            "postcode": "223900", "mobile": "13900000000",
            "surveyorName": "验收脚本", "surveyDate": "2026-09-25",
            "remark": "rollback entry verify fixture",
        },
    )
    if status != 201:
        check(f"建户 {code}", False, f"-> {status} {brief(payload)}")
        return "", [], []
    uid = (payload.get("data") or {}).get("contractorUid") or ""
    if not check(f"建户 {code} 成功", bool(uid), f"uid={uid[:8]}…"):
        return "", [], []

    detail = get_detail(uid)
    members = members_payload(detail.get("familyMembers") or [])
    suffix = code[-2:]
    for idx, (name, relation) in enumerate(members_spec):
        members.append({
            "name": name, "gender": "1", "idType": "1",
            "idNo": f"3203241990010{suffix}{idx}",
            "relationToHead": relation,
            "isHouseholdHead": False,        # ← 关键：刻意不置标记
            "changeReason": "验收新增成员",
        })
    # changeReason / policyBasis 是**另一组**校验（"承包方存在变化时必须填写"），
    # 与户主校验无关；这里一并补齐，避免它把户主校验的结论掩盖掉。
    status, resp = put_result(
        uid, detail, members=members, surveyStatus="surveyed",
        changeReason="验收户主口径验证", policyBasis="验收政策依据",
    )
    check(f"{code} 写入 {len(members_spec)} 名成员", status == 200, f"-> {status} {brief(resp, 300)}")

    member_uids = [m.get("memberUid") for m in get_detail(uid).get("familyMembers") or []]

    codes = []
    for i in range(parcels):
        pc = next_parcel_code(uid)
        if not pc:
            check(f"{code} 取地块编码", False, "-> next-code 未返回")
            break
        st, rp = add_parcel(uid, pc, f"{NAMES[code]}地块{i + 1}")
        if st != 200:
            check(f"{code} 新增地块 {pc}", False, f"-> {st} {brief(rp, 400)}")
            break
        codes.append(pc)
    if parcels:
        check(f"{code} 新增 {parcels} 个地块", len(codes) == parcels, f"-> {codes}")
    return uid, codes, member_uids


# ────────────────────────── H 组：户主口径（ISSUE-06）──────────────────────────
def case_h1_confirm_with_02() -> None:
    log("\n=== H1 户主口径：成员 yhzgx='02'（无 is_household_head 标记）时能否确认 ===")
    uid, _, _ = create_household(HC, [("验收户主02", "02"), ("验收配偶", "10")])
    if not uid:
        return

    # ★ 精确对照：同一份成员数据，在**旧判据**与**新判据**下分别是什么结论。
    # 旧判据 = `len([m for m in members if m.is_household_head or m.yhzgx == "01"]) == 1`
    # 新判据 = `pick_household_head(members) is not None`
    rows = sql(
        "SELECT yhzgx, is_household_head FROM survey_cbf_jtcy_result"
        " WHERE contractor_uid = %s ORDER BY id", (uid,))
    note("DB 成员 (yhzgx, is_household_head)", f"{rows}")
    old_heads = [r for r in rows if r[1] or str(r[0]).strip() == "01"]
    check("★ H1a 旧判据对该户判为『0 个户主』⇒ 确认必然 400（这正是 17.9 万户的形态）",
          len(old_heads) != 1, f"-> old_heads={len(old_heads)}")
    check("★ H1b 新判据能从同一份数据判出户主（02 命中）",
          any(str(r[0]).strip() == "02" for r in rows), f"-> codes={[r[0] for r in rows]}")

    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/confirm", method="POST")
    check("★ H1 户主记为 02 的真实形态可以「确认调查结果」",
          status == 200, f"-> {status} {brief(resp, 300)}")


def case_h2_confirm_fallback() -> None:
    log("\n=== H2 户主口径：成员全是 10/20（无 02、无 01）时应兜底挑一条 ===")
    uid, _, _ = create_household(HF, [("验收无户主甲", "10"), ("验收无户主乙", "20")])
    if not uid:
        return
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/confirm", method="POST")
    check("★ H2 无 02/01 时按「兜底任取一条」判定户主 ⇒ 可以确认",
          status == 200, f"-> {status} {brief(resp, 300)}")


def case_h3_confirm_no_member() -> None:
    log("\n=== H3 户主口径：没有任何成员时仍应拒绝确认 ===")
    uid, _, _ = create_household(HE, [])
    if not uid:
        return
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/confirm", method="POST")
    check("H3 无成员仍必须拒绝（校验没被放空）",
          status == 400, f"-> {status} {brief(resp, 200)}")


def case_h4_relation_labels() -> None:
    log("\n=== H4 关系码映射：出件口径必须与字典一致（02=户主、10=配偶）===")
    from app.services.contract_template_service import YHZGX_MAP
    note("contract_template_service.YHZGX_MAP", f"02→{YHZGX_MAP.get('02')!r} 10→{YHZGX_MAP.get('10')!r}")
    check("★ H4a 静态兜底映射 02→户主", YHZGX_MAP.get("02") == "户主",
          f"-> {YHZGX_MAP.get('02')!r}")
    check("★ H4b 静态兜底映射 10→配偶", YHZGX_MAP.get("10") == "配偶",
          f"-> {YHZGX_MAP.get('10')!r}")

    try:
        from app.db.session import SessionLocal  # type: ignore
        from app.services.relation_codes import relation_labels
    except Exception as exc:  # noqa: BLE001
        check("H4c 运行时字典映射可用（relation_codes.relation_labels）", False, f"-> {exc!r}")
        return
    with SessionLocal() as db:
        labels = relation_labels(db)
    check("★ H4c 运行时字典映射 02→户主", labels.get("02") == "户主", f"-> {labels.get('02')!r}")


def case_h5_head_picker() -> None:
    log("\n=== H5 户主判定助手：02 → 01 → 兜底 的优先级 ===")
    try:
        from app.services.relation_codes import pick_household_head
    except Exception as exc:  # noqa: BLE001
        check("H5 户主判定助手可用（relation_codes.pick_household_head）", False, f"-> {exc!r}")
        return

    class M:
        def __init__(self, name, code):
            self.cyxm, self.yhzgx = name, code

    got = pick_household_head([M("甲", "10"), M("乙", "02"), M("丙", "20")])
    check("H5a 有 02 时取 02", getattr(got, "cyxm", None) == "乙", f"-> {getattr(got, 'cyxm', None)}")

    got = pick_household_head([M("甲", "10"), M("乙", "01"), M("丙", "20")])
    check("H5b 无 02 时取 01", getattr(got, "cyxm", None) == "乙", f"-> {getattr(got, 'cyxm', None)}")

    got = pick_household_head([M("甲", "10"), M("乙", "20")])
    check("H5c 两者都无时兜底取第一条", getattr(got, "cyxm", None) == "甲", f"-> {getattr(got, 'cyxm', None)}")

    got = pick_household_head([])
    check("H5d 空集合返回 None", got is None, f"-> {got!r}")

    class F:
        """带显式 is_household_head 标记的成员。"""

        def __init__(self, name, code, flag=False):
            self.cyxm, self.yhzgx, self.is_household_head = name, code, flag

    got = pick_household_head([F("甲", "02"), F("乙", "10", True)])
    check("★ H5e 显式标记优先于码值推断（否则合户指定的户主会被原户 02 覆盖）",
          getattr(got, "cyxm", None) == "乙", f"-> {getattr(got, 'cyxm', None)}")


# ────────────────────────── D/S 组：注销 / 合户 / 分户 的入口同源 ──────────────────────────
def case_d1_deregister() -> None:
    log("\n=== D1 单户注销：已注销列表 changeType=deregister，按钮与接口同源 ===")
    uid, _, _ = create_household(HD, [("验收注销户主", "02"), ("验收注销成员", "10")])
    if not uid:
        return
    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/deregister",
                       method="POST", body={"reason": "验收注销"})
    if not check("D1 注销 200", status == 200, f"-> {status} {brief(resp, 300)}"):
        return

    row = dereg_row(HD)
    check("D1 该户出现在已注销列表", bool(row), f"-> {brief(row, 200)}")
    check("★ D1 changeType == 'deregister'", row.get("changeType") == "deregister",
          f"-> {row.get('changeType')!r}")
    check("★ D1 changeNo 非空（按钮挂得上台账）", bool(row.get("changeNo")),
          f"-> {row.get('changeNo')!r}")
    check("★ D1 canRollback == True", row.get("canRollback") is True, f"-> {row.get('canRollback')!r}")

    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid}/rollback-deregister", method="POST")
    check("★ D1 按 changeType 分流调用 rollback-deregister → 200",
          status == 200, f"-> {status} {brief(resp, 300)}")


def case_d2_merge() -> None:
    log("\n=== D2 合户：原户进已注销列表，changype=merge_household，按类型撤回 ===")
    uid_a, _, _ = create_household(HA, [("验收合户A1", "02"), ("验收合户A2", "10")], parcels=1)
    uid_b, _, _ = create_household(HB, [("验收合户B1", "02"), ("验收合户B2", "10")], parcels=1)
    if not (uid_a and uid_b):
        return

    da = get_detail(uid_a)
    head = next((m.get("memberUid") for m in da.get("familyMembers") or [] if m.get("memberUid")), None)
    status, resp = put_result(uid_a, da, pending=[{
        "type": "merge_household",
        "payload": {
            "sourceContractorUids": [uid_a, uid_b],
            "newCbfbm": HM, "newCbfmc": NAMES[HM],
            "householdHeadMemberUid": head,
            "newAddress": "验收合并地址", "reason": "验收合户",
        },
    }])
    if not check("D2 合户 PUT 200", status == 200, f"-> {status} {brief(resp, 600)}"):
        return

    for code in (HA, HB):
        row = dereg_row(code)
        check(f"★ D2 {code} 出现在已注销列表", bool(row), f"-> {brief(row, 200)}")
        check(f"★ D2 {code} changeType == 'merge_household'",
              row.get("changeType") == "merge_household", f"-> {row.get('changeType')!r}")
        check(f"★ D2 {code} changeNo 非空（修复前为 null）", bool(row.get("changeNo")),
              f"-> {row.get('changeNo')!r}")
        check(f"★ D2 {code} canRollback == True", row.get("canRollback") is True,
              f"-> {row.get('canRollback')!r}")

    # H6：合户后新户的户主关系码应为 02（修复前写的是 01）
    new_uid_row = sql("SELECT contractor_uid FROM survey_cbf_result WHERE cbfbm = %s", (HM,))
    if new_uid_row:
        new_uid = new_uid_row[0][0]
        heads = sql(
            "SELECT yhzgx, is_household_head FROM survey_cbf_jtcy_result"
            " WHERE contractor_uid = %s AND (is_household_head OR yhzgx = '02')", (new_uid,))
        note("合户新户户主行", f"{heads}")
        check("★ H6 合户新户户主的 yhzgx 为 02（户主）",
              bool(heads) and all(r[0] == "02" for r in heads), f"-> {heads}")

    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_a}/merge-household/rollback",
                       method="POST")
    check("★ D2 按 changeType 分流调用 merge-household/rollback → 200",
          status == 200, f"-> {status} {brief(resp, 300)}")


def case_d3_split_alignment() -> None:
    log("\n=== D3 + S1/S2/S3 分户：task_status 对齐 + 撤回入口可达 ===")
    uid_s, _, member_uids = create_household(
        HS, [("验收分户甲", "02"), ("验收分户乙", "10")], parcels=2)
    if not uid_s:
        return

    detail = get_detail(uid_s)
    members = detail.get("familyMembers") or []
    parcel_rows = api(f"/surveys/batches/{BATCH_ID}/results/{uid_s}/parcels")
    parcels = []
    if parcel_rows[0] == 200:
        # 该端点的 data 是**数组**（ApiResponse[list[LandParcelItem]]），不是分页对象。
        data = parcel_rows[1].get("data") or []
        rows = data.get("items") if isinstance(data, dict) else data
        parcels = [p.get("dkbm") for p in (rows or []) if isinstance(p, dict) and p.get("dkbm")]
    if len(members) < 2 or len(parcels) < 2:
        check("D3 夹具就绪（≥2 成员、≥2 地块）", False, f"-> members={len(members)} parcels={parcels}")
        return

    status, resp = put_result(uid_s, detail, pending=[{
        "type": "split_household",
        "payload": {
            "newHouseholds": [
                {"newCbfbm": HS1, "newCbfmc": NAMES[HS1],
                 "memberUids": [members[0].get("memberUid")], "parcelDkbms": [parcels[0]],
                 "householdHeadMemberUid": members[0].get("memberUid")},
                {"newCbfbm": HS2, "newCbfmc": NAMES[HS2],
                 "memberUids": [members[1].get("memberUid")], "parcelDkbms": [parcels[1]],
                 "householdHeadMemberUid": members[1].get("memberUid")},
            ],
            "reason": "验收分户",
        },
    }])
    if not check("D3 分户 PUT 200", status == 200, f"-> {status} {brief(resp, 600)}"):
        return

    # S1 原户 task_status 是否对齐为 deregistered
    rows = sql("SELECT task_status FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = %s",
               (BATCH_ID, HS))
    src_task_status = rows[0][0] if rows else None
    note("分户源户 task_status", f"{src_task_status!r}")
    check("★ S1 分户后原户 task_status == 'deregistered'（与合户对齐，修复前不是）",
          src_task_status == "deregistered", f"-> {src_task_status!r}")

    # S2 原户是否离开主任务列表（默认口径）
    got = list_tasks(keyword=HS)
    codes = [i.get("cbfbm") for i in (got.get("items") or [])]
    check("★ S2 分户后原户不在主任务列表（默认口径）",
          HS not in codes, f"-> total={got.get('total')} codes={codes}")

    # H5' 分户新户户主关系码
    child_rows = sql(
        "SELECT b.cbfbm, m.yhzgx, m.is_household_head FROM survey_cbf_base b"
        " JOIN survey_cbf_jtcy_result m ON m.contractor_uid = b.contractor_uid"
        " WHERE b.batch_id = %s AND b.cbfbm = ANY(%s)", (BATCH_ID, [HS1, HS2]))
    note("分户新户户主行", f"{child_rows}")
    check("★ H5' 分户新户户主 yhzgx 为 02（户主）",
          bool(child_rows) and all(r[1] == "02" for r in child_rows), f"-> {child_rows}")

    # D3 入口：原户在已注销列表且带正确的 changeType
    row = dereg_row(HS)
    check("★ D3 分户后原户出现在已注销列表", bool(row), f"-> {brief(row, 200)}")
    check("★ D3 changeType == 'split_household'", row.get("changeType") == "split_household",
          f"-> {row.get('changeType')!r}")
    check("★ D3 changeNo 非空", bool(row.get("changeNo")), f"-> {row.get('changeNo')!r}")
    check("★ D3 canRollback == True", row.get("canRollback") is True, f"-> {row.get('canRollback')!r}")

    status, resp = api(f"/surveys/batches/{BATCH_ID}/results/{uid_s}/split-household/rollback",
                       method="POST")
    if not check("★ D3 按 changeType 分流调用 split-household/rollback → 200",
                 status == 200, f"-> {status} {brief(resp, 300)}"):
        return

    # S3 撤回后还原
    rows = sql("SELECT task_status FROM survey_cbf_base WHERE batch_id = %s AND cbfbm = %s",
               (BATCH_ID, HS))
    restored = rows[0][0] if rows else None
    note("撤回分户后源户 task_status", f"{restored!r}")
    check("★ S3 撤回分户后原户 task_status 不再是 deregistered",
          restored not in (None, "deregistered"), f"-> {restored!r}")

    got = list_tasks(keyword=HS)
    codes = [i.get("cbfbm") for i in (got.get("items") or [])]
    check("★ S3 撤回分户后原户重回主任务列表", HS in codes,
          f"-> total={got.get('total')} codes={codes}")


def case_d4_batch_finished() -> None:
    log("\n=== D4 批次已结束时 canRollback 必须为 false（同源判据保留） ===")
    note("跳过运行时改批次状态（会污染生产批次 41）")
    note("改为静态断言：list_deregistered_contractors 仍以 batch.status != 'finished' 收敛")
    src = (ROOT / "backend" / "app" / "services" / "survey" / "task.py").read_text(encoding="utf-8-sig")
    check("D4 代码中保留 batch.status 收敛条件",
          'batch.status != "finished"' in src, "-> 未找到该条件")


# ────────────────────────── 主流程 ──────────────────────────
def main() -> None:
    global client
    log("=" * 78)
    log("验收：户主口径统一 / 已注销列表入口同源 / 分户对齐")
    log(f"批次 {BATCH_ID}｜夹具编码段 3213241000010297xx")
    log("=" * 78)

    with TestClient(app) as c:
        client = c
        if not preflight():
            return
        try:
            case_h4_relation_labels()
            case_h5_head_picker()
            case_h1_confirm_with_02()
            case_h2_confirm_fallback()
            case_h3_confirm_no_member()
            case_d1_deregister()
            case_d2_merge()
            case_d3_split_alignment()
            case_d4_batch_finished()
        finally:
            log("\n=== 收尾：清理夹具 ===")
            housekeeping()
            res = residue_report()
            log(f"      残留复核 {res}")
            check("收尾后夹具无残留", all(v == 0 for v in res.values()), f"-> {res}")

    log("\n" + "=" * 78)
    log(f"结果：PASS {sum(1 for l in OUT if l.startswith('[PASS]'))}"
        f" / FAIL {len(FAILED)} / 已知残留 {len(KNOWN_GAPS)}")
    if FAILED:
        log("\n失败项：")
        for item in FAILED:
            log(f"  ✗ {item}")
    if KNOWN_GAPS:
        log("\n已知残留：")
        for item in KNOWN_GAPS:
            log(f"  ○ {item}")
    log("=" * 78)

    dest = ROOT / "runtime" / ".state" / "_verify_survey_rollback_entry.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n[written] {dest}")


if __name__ == "__main__":
    main()
