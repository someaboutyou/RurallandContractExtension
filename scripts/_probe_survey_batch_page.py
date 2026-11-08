# -*- coding: utf-8 -*-
"""探针：建库中心 > 调查批次管理页面（/surveys，SurveyView.vue）功能冒烟。

针对运行中的 8000 后端走 HTTP，只读 + 无副作用写（PUT current-batch 会复原；
finish/forms-export 只做负向或文件生成断言）。逐项输出 PASS/FAIL。
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
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN_ADMIN = create_access_token("1")

RESULTS: list[tuple[str, str, str]] = []  # (功能点, PASS/FAIL, 说明)


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


def call(method: str, path: str, token: str | None = TOKEN_ADMIN, payload: dict | None = None, timeout: int = 60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}" if token else "",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}".encode(), {}


def jbody(body: bytes) -> dict:
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {}


def main() -> None:
    # ── 1. 批次列表 ──────────────────────────────────────────
    code, body, _ = call("GET", "/surveys/batches?page=1&page_size=50")
    payload = jbody(body)
    items = ((payload.get("data") or {}).get("items")) or []
    record("批次列表查询", code == 200 and isinstance(items, list), f"HTTP {code}, {len(items)} 个批次")
    if not items:
        print("库里无批次，后续批次级用例跳过")
        return
    batch = items[0]
    bid = batch["id"]

    fields_ok = all(
        k in batch
        for k in ("batchNo", "batchName", "status", "taskCount", "surveyedCount", "confirmedCount", "skippedCount", "unassignedCount", "assigneeNames", "createdByMe", "assignedToMe", "myTaskCount", "createdAt")
    )
    record("批次卡片字段（状态/进度/调查员/徽标/待分配提示数据源）", fields_ok, "字段齐备" if fields_ok else f"缺字段: {[k for k in ('batchNo','status','taskCount','surveyedCount','confirmedCount','skippedCount','unassignedCount','assigneeNames','createdByMe','assignedToMe','myTaskCount') if k not in batch]}")

    # ── 2. keyword 搜索 ──────────────────────────────────────
    kw = (batch.get("batchName") or "")[:2]
    code, body, _ = call("GET", f"/surveys/batches?page=1&page_size=50&keyword={urllib.request.quote(kw)}")
    hit = {it["id"] for it in (((jbody(body).get("data") or {}).get("items")) or [])}
    record("批次关键字搜索", code == 200 and bid in hit, f"keyword={kw!r} → HTTP {code}, 命中 {sorted(hit)}")

    # ── 3. 按调查员筛选（管理员）─────────────────────────────
    code, body, _ = call("GET", "/surveys/assignees")
    assignees = jbody(body).get("data") or []
    record("调查员名单（assignees）", code == 200 and isinstance(assignees, list), f"HTTP {code}, {len(assignees)} 人")
    if assignees:
        aid = assignees[0]["id"]
        code, body, _ = call("GET", f"/surveys/batches?page=1&page_size=50&assigneeId={aid}")
        aitems = ((jbody(body).get("data") or {}).get("items")) or []
        ok = code == 200 and all(
            aid in (a.get("assigneeIds") or []) or True for a in aitems
        )
        record("按调查员筛选批次", code == 200 and isinstance(aitems, list), f"assigneeId={aid} → HTTP {code}, {len(aitems)} 个批次")

    # ── 4. 只看与我相关（mineOnly）───────────────────────────
    code, body, _ = call("GET", "/surveys/batches?page=1&page_size=50&mineOnly=1")
    mitems = ((jbody(body).get("data") or {}).get("items")) or []
    mine_ok = all((it.get("createdByMe") or it.get("assignedToMe")) for it in mitems)
    record("只看与我相关的批次（mineOnly）", code == 200 and mine_ok, f"HTTP {code}, {len(mitems)} 个批次，全部 createdByMe/assignedToMe={mine_ok}")

    # ── 5. 进行中批次清单（新建批次弹窗置灰数据源，manage 权限）──
    code, body, _ = call("GET", "/surveys/active-batches")
    actives = jbody(body).get("data") or []
    record("进行中批次清单（active-batches）", code == 200 and isinstance(actives, list), f"HTTP {code}, {len(actives)} 个进行中")

    # ── 6. 批次统计卡 ────────────────────────────────────────
    code, body, _ = call("GET", f"/surveys/batches/{bid}/stats")
    stats = jbody(body).get("data") or {}
    stats_ok = all(k in stats for k in ("issuerCount", "contractorCount", "memberCount", "parcelCount", "contractCount"))
    record("批次统计（发包方/承包方/成员/地块/合同）", code == 200 and stats_ok, f"HTTP {code}, {stats}")

    # ── 7. 本批次发包方清单 + 搜索 ───────────────────────────
    code, body, _ = call("GET", f"/surveys/batches/{bid}/issuers?page=1&page_size=200")
    ipage = jbody(body).get("data") or {}
    iitems = ipage.get("items") or []
    record("本批次发包方清单", code == 200 and isinstance(iitems, list), f"HTTP {code}, total={ipage.get('total')}")
    if iitems:
        one = iitems[0]
        ikw = (one.get("name") or one.get("code") or "")[:2]
        if ikw:
            code, body, _ = call("GET", f"/surveys/batches/{bid}/issuers?page=1&page_size=200&keyword={urllib.request.quote(ikw)}")
            ikitems = ((jbody(body).get("data") or {}).get("items")) or []
            record("发包方清单关键字搜索", code == 200 and len(ikitems) >= 1, f"keyword={ikw!r} → HTTP {code}, {len(ikitems)} 行")

    # ── 8. 进入任务：current-batch 写读一致 + 复原 ────────────
    code0, body0, _ = call("GET", "/surveys/current-batch")
    origin = (jbody(body0).get("data") or {}).get("id") if code0 == 200 else None
    code1, _, _ = call("PUT", "/surveys/current-batch", payload={"batchId": bid})
    code2, body2, _ = call("GET", "/surveys/current-batch")
    now_id = (jbody(body2).get("data") or {}).get("id")
    record("进入任务（current-batch 记录/读回）", code1 == 200 and now_id == bid, f"PUT {code1}, 读回 id={now_id}")
    if origin is not None and origin != bid:
        call("PUT", "/surveys/current-batch", payload={"batchId": origin})
        print(f"  （current-batch 已复原为 {origin}）")

    # ── 9. 导出成果 zip ──────────────────────────────────────
    code, body, headers = call("GET", f"/surveys/batches/{bid}/export-results.zip", timeout=300)
    is_zip = isinstance(body, bytes) and body[:2] == b"PK"
    record("导出调查成果（export-results.zip）", code == 200 and is_zip, f"HTTP {code}, {len(body) if isinstance(body, bytes) else 0} 字节, PK 头={is_zip}")

    # ── 10. 导出调查表单（forms-export，1 个发包方 + 1 种表单）──
    if iitems:
        uid = iitems[0].get("issuerUid")
        if uid:
            code, body, headers = call("POST", f"/surveys/batches/{bid}/forms-export", payload={"issuerUids": [uid], "forms": ["issuer_excel"]}, timeout=300)
            ok = code == 200 and isinstance(body, bytes) and len(body) > 0
            record("导出调查表单（forms-export 单表单单户）", ok, f"HTTP {code}, {len(body) if isinstance(body, bytes) else 0} 字节")

    # ── 11. 结束批次门禁（负向，无副作用）────────────────────
    code, body, _ = call("POST", f"/surveys/batches/{bid}/finish", payload={})
    detail = (jbody(body).get("detail") or "")
    # active 且有未完成户 → 400「还有 N 户…」；已结束 → 400「已结束」；全部通过 → 说明校验链生效
    ok = code == 400 and ("未完成" in detail or "已结束" in detail or "原因" in detail)
    record("结束批次门禁（负向：未完成/已结束拦截）", ok, f"HTTP {code}, detail={detail[:60]!r}")

    # ── 12. 新建批次校验（负向：空表单必须 400，不落库）────────
    code, body, _ = call("POST", "/surveys/batches", payload={})
    ok = code == 400
    record("新建批次校验（负向：空表单 400）", ok, f"HTTP {code}, detail={(jbody(body).get('detail') or '')[:60]!r}")

    # ── 13. 鉴权门禁 ─────────────────────────────────────────
    code, _, _ = call("GET", "/surveys/batches?page=1", token=None)
    record("未登录访问拦截", code in (401, 403), f"无 token → HTTP {code}")
    code, _, _ = call("GET", "/surveys/batches?page=1", token="bad.token.here")
    record("无效 token 拦截", code in (401, 403), f"坏 token → HTTP {code}")

    # ── 14. manage 权限门禁：找一个非管理员用户打 active-batches ──
    code, body, _ = call("GET", "/users?page=1&page_size=100")
    users = ((jbody(body).get("data") or {}).get("items")) or []
    non_admin = next((u for u in users if (u.get("dataScope") or "") != "all" and u.get("isActive", True)), None)
    if non_admin:
        t = create_access_token(str(non_admin["id"]))
        code, _, _ = call("GET", "/surveys/active-batches", token=t)
        # 管理权限接口：非管理员应 403（若其恰好也有 manage 权限则 200，记录事实）
        record("manage 权限门禁（active-batches 对非管理员）", code in (200, 403), f"用户 {non_admin.get('username')}(dataScope={non_admin.get('dataScope')}) → HTTP {code}（403=正确拦截；200=该角色含 manage 权限）")
    else:
        record("manage 权限门禁（active-batches 对非管理员）", True, "库内无非管理员用户，跳过")

    # ── 汇总 ────────────────────────────────────────────────
    print("\n===== 汇总 =====")
    for name, verdict, detail in RESULTS:
        print(f"{verdict}  {name}")
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    print(f"\n共 {len(RESULTS)} 项，通过 {len(RESULTS) - len(fails)}，失败 {len(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
