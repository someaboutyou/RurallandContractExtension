# -*- coding: utf-8 -*-
"""探查（只读）：列出候选批次里每个户的地块 / 成员 / 差异 / 可撤回变更，挑测试夹具。

跑法：runtime/windows/python/python.exe scripts/_probe_batch_fixture.py [batch_id ...]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
TOKEN = create_access_token("1")
BATCH_IDS = [int(x) for x in sys.argv[1:]] or [41, 40]


def api(path: str, method: str = "GET", body: dict | None = None, timeout: int = 60):
    data = json.dumps(body).encode("utf-8") if body is not None else None
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
            return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def main() -> None:
    for batch_id in BATCH_IDS:
        print(f"\n{'=' * 70}\n批次 {batch_id}")
        status, payload = api(f"/surveys/batches/{batch_id}/tasks?page=1&page_size=100")
        if status != 200:
            print(f"  取任务失败 {status}: {str(payload)[:300]}")
            continue
        items = (payload.get("data") or {}).get("items") or []
        print(f"  任务数 {len(items)} / total={(payload.get('data') or {}).get('total')}")
        for task in items:
            uid = task.get("contractorUid")
            code = task.get("cbfbm") or task.get("code")
            name = task.get("cbfmc") or task.get("name")
            status_code, detail = api(f"/surveys/batches/{batch_id}/results/{uid}")
            d = detail.get("data") if status_code == 200 else {}
            _, parcels = api(f"/surveys/batches/{batch_id}/results/{uid}/parcels")
            plist = parcels.get("data") if isinstance(parcels, dict) else []
            _, changes = api(f"/surveys/batches/{batch_id}/changes?contractorUid={uid}&page=1&page_size=50")
            clist = (changes.get("data") or {}).get("items") if isinstance(changes, dict) else []
            _, diffs = api(f"/surveys/batches/{batch_id}/results/{uid}/diffs?page=1&page_size=200")
            n_diffs = (diffs.get("data") or {}).get("total") if isinstance(diffs, dict) else "?"
            active_parcels = [p for p in (plist or []) if p.get("resultStatus") not in ("removed", "split_source")]
            print(
                f"    uid={uid[:8]}… code={code} name={name}"
                f" canWrite={task.get('canWrite')} taskStatus={task.get('taskStatus')}"
            )
            print(
                f"        result: survey={d.get('surveyStatus')} result={d.get('resultStatus')}"
                f" changeType={d.get('changeType')} isChanged={d.get('isChanged')}"
                f" members={len(d.get('familyMembers') or [])}"
            )
            print(f"        parcels: {len(plist or [])} 条（有效地块 {len(active_parcels)}）diffs={n_diffs}")
            if clist:
                for c in clist:
                    print(
                        f"        change#{c.get('id')} {c.get('changeNo')} type={c.get('changeType')}"
                        f" status={c.get('changeStatus')} reason={c.get('changeReason')}"
                    )


if __name__ == "__main__":
    main()
