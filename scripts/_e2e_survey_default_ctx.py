"""给「承包方调查录入 → 调查员 / 调查日期 默认取本次」的前端验收准备上下文（**只读，不写库**）。

要挑出这样一户来验：
  1. 属于用户 1 能写（canWrite 不是 False）的批次；
  2. 结果还没确认、没终结；
  3. **库里的调查员 / 调查日期仍等于批次快照（baseContractor）的值** —— 这正是
     「默认加载上次的调查员和时间」这个毛病的前提，也是前端 `isStillBaseline` 会命中的分支；
  4. 快照里的调查员**不等于当前登录用户姓名** —— 否则"改对了"和"本来就是对的"分不清，
     断言会假通过。

输出：runtime/.state/_e2e_survey_default_ctx.json
跑法：runtime/windows/python/python.exe scripts/_e2e_survey_default_ctx.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "runtime" / ".state" / "_e2e_survey_default_ctx.json"


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
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

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402

TODAY = date.today().isoformat()


def main() -> int:
    token = create_access_token("1")
    headers = {"Authorization": f"Bearer {token}"}
    report: dict = {"today": TODAY, "token": token, "picked": None, "scanned": {}}
    with TestClient(app) as client:
        me = client.get("/api/v1/auth/me", headers=headers).json()["data"]
        report["userId"] = me.get("id")
        report["userName"] = me.get("realName") or me.get("username")
        report["username"] = me.get("username")

        batches = client.get(
            "/api/v1/surveys/batches", headers=headers, params={"page": 1, "page_size": 50}
        ).json()["data"]["items"]
        report["batchCount"] = len(batches)

        candidates: list[dict] = []
        readonly_candidates: list[dict] = []
        for batch in batches[:12]:
            tasks = client.get(
                f"/api/v1/surveys/batches/{batch['id']}/tasks",
                headers=headers,
                params={"page": 1, "page_size": 200},
            ).json()["data"]["items"]
            report["scanned"][str(batch["id"])] = len(tasks)
            for task in tasks:
                if task.get("taskStatus") == "confirmed":
                    continue
                detail = client.get(
                    f"/api/v1/surveys/batches/{batch['id']}/results/{task['contractorUid']}",
                    headers=headers,
                )
                if detail.status_code != 200:
                    continue
                row = detail.json()["data"]
                if row.get("isTerminal") or row.get("surveyStatus") == "confirmed":
                    continue
                base = row.get("baseContractor")
                if not base:
                    continue
                # 前提：库里的值还等于快照值（没人在本批次改过）
                if (row.get("surveyorName") or "") != (base.get("surveyorName") or ""):
                    continue
                if (row.get("surveyDate") or "") != (base.get("surveyDate") or ""):
                    continue
                item = {
                    "batchId": batch["id"],
                    "batchName": batch.get("batchName") or batch.get("batchNo"),
                    "batchNo": batch.get("batchNo"),
                    "batchStatus": batch.get("status"),
                    "cbfbm": task.get("cbfbm"),
                    "cbfmc": task.get("cbfmc"),
                    "contractorUid": task["contractorUid"],
                    "assignedToName": task.get("assignedToName"),
                    "baseSurveyorName": base.get("surveyorName"),
                    "baseSurveyDate": base.get("surveyDate"),
                    "changedFromUser": (base.get("surveyorName") or "") != (me.get("realName") or ""),
                    "dateIsToday": (base.get("surveyDate") or "") == TODAY,
                }
                if task.get("canWrite") is False:
                    # 只读户（没分配 / 分给别人）：绝不能把默认值写进别人的记录视图。
                    readonly_candidates.append(item)
                else:
                    candidates.append(item)

        report["candidateCount"] = len(candidates)
        report["candidates"] = candidates[:8]
        report["readonlyCandidateCount"] = len(readonly_candidates)
        report["readonlyCandidates"] = readonly_candidates[:8]
        # 优先挑「快照调查员不是我、日期也不是今天」的户：这样"默认填成了本次"才可证伪。
        picked = next(
            (c for c in candidates if c["changedFromUser"] and not c["dateIsToday"]),
            next((c for c in candidates if c["changedFromUser"]), None),
        )
        report["picked"] = picked
        # 只读对照户：挑同一批次里的，省一次批次切换。
        picked_readonly = next(
            (c for c in readonly_candidates if picked and c["batchId"] == picked["batchId"]),
            readonly_candidates[0] if readonly_candidates else None,
        )
        report["pickedReadonly"] = picked_readonly

        # ---- 发包方侧（/surveys →「发包方调查」→「进入调查」）----
        # 口径与承包方侧完全一样，夹具挑法也照抄：库里值仍等于快照 baseIssuer、快照调查员不是我。
        issuer_candidates: list[dict] = []
        issuer_locked: list[dict] = []
        issuer_base_missing = 0
        for batch in batches[:12]:
            params = {"page": 1, "page_size": 200}
            if batch.get("regionCode"):
                params["regionCode"] = batch["regionCode"]
            issuer_rows = client.get(
                f"/api/v1/surveys/batches/{batch['id']}/issuers", headers=headers, params=params
            ).json()["data"]["items"]
            report.setdefault("issuerScanned", {})[str(batch["id"])] = len(issuer_rows)
            for row in issuer_rows:
                detail = client.get(
                    f"/api/v1/surveys/batches/{batch['id']}/issuers/{row['issuerUid']}",
                    headers=headers,
                )
                if detail.status_code != 200:
                    continue
                data = detail.json()["data"]
                base = data.get("baseIssuer")
                if not base:
                    # 没有本批次快照 ⇒ 前端会走"无快照"分支（与分户/合户新生成的户同一分支）。
                    issuer_base_missing += 1
                    continue
                if (data.get("surveyorName") or "") != (base.get("surveyorName") or ""):
                    continue
                if (data.get("surveyDate") or "") != (base.get("surveyDate") or ""):
                    continue
                item = {
                    "batchId": batch["id"],
                    "batchName": batch.get("batchName") or batch.get("batchNo"),
                    "batchStatus": batch.get("status"),
                    "code": data.get("code"),
                    "name": data.get("name"),
                    "issuerUid": row["issuerUid"],
                    "surveyStatus": data.get("surveyStatus"),
                    "baseSurveyorName": base.get("surveyorName"),
                    "baseSurveyDate": base.get("surveyDate"),
                    "changedFromUser": (base.get("surveyorName") or "") != (me.get("realName") or ""),
                    "dateIsToday": (base.get("surveyDate") or "") == TODAY,
                }
                # 只读对照：已确认 或 所属批次已结束 ⇒ 保存按钮不显示，默认值不得落进表单。
                if data.get("surveyStatus") == "confirmed" or batch.get("status") == "finished":
                    issuer_locked.append(item)
                else:
                    issuer_candidates.append(item)

        report["issuerBaseMissing"] = issuer_base_missing
        report["issuerCandidateCount"] = len(issuer_candidates)
        report["issuerCandidates"] = issuer_candidates[:8]
        picked_issuer = next(
            (c for c in issuer_candidates if c["changedFromUser"] and not c["dateIsToday"]),
            next((c for c in issuer_candidates if c["changedFromUser"]), None),
        )
        report["issuerPicked"] = picked_issuer
        report["issuerLocked"] = issuer_locked[0] if issuer_locked else None

        # 只读对照账号：镇级业务员（user 5）。非管理员 ⇒ 界面是「查看详情」只读，
        # 用来证明默认值**不会**写进只读视图。先确认它真能看到目标批次且该户不可写。
        ro_token = create_access_token("5")
        ro_headers = {"Authorization": f"Bearer {ro_token}"}
        ro_me = client.get("/api/v1/auth/me", headers=ro_headers).json()["data"]
        report["readonlyUserName"] = ro_me.get("realName")
        if picked:
            ro_tasks = client.get(
                f"/api/v1/surveys/batches/{picked['batchId']}/tasks",
                headers=ro_headers,
                params={"page": 1, "page_size": 200, "keyword": picked["cbfbm"]},
            ).json()["data"]["items"]
            hit = next((t for t in ro_tasks if t.get("cbfbm") == picked["cbfbm"]), None)
            if hit is None:
                report["readonlyToken"] = None
                report["readonlySkipReason"] = "镇级业务员看不到该户，跳过只读对照"
            elif hit.get("canWrite") is not False:
                report["readonlyToken"] = None
                report["readonlySkipReason"] = "该户对镇级业务员仍可写，跳过只读对照"
            else:
                report["readonlyToken"] = ro_token

    OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "token"}, ensure_ascii=False, indent=2))
    print(f"\nwrote {OUT_PATH}")
    return 0 if picked else 1


if __name__ == "__main__":
    raise SystemExit(main())
