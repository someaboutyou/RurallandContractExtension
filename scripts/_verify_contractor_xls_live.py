# -*- coding: utf-8 -*-
"""在线验收（只读）：承包方调查表 Excel 导出 + 导入预览 + 错误路径。

在 8001 端口临时起后端（同库），验证：
1. GET  /surveys/batches/{id}/contractors-xls      → 导出成功、可被解析、户数与批次一致
2. POST .../contractors-xls/preview（原样文件）     → 全部 no_change（导出↔导入闭环）
3. POST .../contractors-xls/preview（编号改坏）     → 前缀校验拦截
4. POST .../contractors-xls/import（编号改坏文件）  → 逐户失败、不落库
不修改任何业务数据。运行：runtime/windows/python/python.exe scripts/_verify_contractor_xls_live.py
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "runtime" / "windows" / "python" / "python.exe"
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# 与 start-backend.ps1 同源：注入 runtime.env（否则 config 默认 5432 连不上）
_runtime_env = ROOT / "runtime" / ".state" / "runtime.env"
if _runtime_env.exists():
    for line in _runtime_env.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import httpx  # noqa: E402
from app.core.security import create_access_token  # noqa: E402

PORT = 8001
BASE = f"http://127.0.0.1:{PORT}/api/v1"
TOKEN = create_access_token("1")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
OUT_DIR = ROOT / "runtime" / ".state" / "xls_verify"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FAILED = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))
    if not cond:
        FAILED.append(name)


def main():
    from app.services.survey import excel_transfer as m

    server = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        # 等待启动
        for _ in range(60):
            try:
                httpx.get(f"{BASE}/auth/me", headers=HEADERS, timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            print("后端启动超时")
            sys.exit(2)

        # 选一个活动批次
        with httpx.Client(base_url=BASE, headers=HEADERS, timeout=60) as client:
            resp = client.get("/surveys/batches", params={"page": 1, "pageSize": 10})
            batches = resp.json()["data"]["items"]
            if not batches:
                print("没有任何调查批次，无法在线验收")
                sys.exit(2)
            batch = batches[0]
            batch_id = batch["id"]
            print(f"使用批次 id={batch_id} {batch['batchName']} 区域码={batch['regionCode']}")

            # 1. 导出
            resp = client.get(f"/surveys/batches/{batch_id}/contractors-xls")
            check("导出 HTTP 200", resp.status_code == 200, f"{resp.status_code} {resp.text[:200]}")
            check("导出为 xls（OLE2 魔数）", resp.content[:4] == b"\xd0\xcf\x11\xe0")
            xls_path = OUT_DIR / f"export_batch_{batch_id}.xls"
            xls_path.write_bytes(resp.content)
            print(f"      导出文件：{xls_path}")

            blocks, warnings = m.SurveyServiceExcelTransferMixin.parse_contractors_xls(resp.content)
            print(f"      导出户数={len(blocks)} 告警={len(warnings)}")
            check("导出可被解析且无告警", len(blocks) > 0 and not warnings, f"{len(blocks)}户 {warnings[:3]}")

            # 2. 原样预览 → 全部 no_change
            with open(xls_path, "rb") as f:
                resp = client.post(
                    f"/surveys/batches/{batch_id}/contractors-xls/preview",
                    files={"file": ("export.xls", f, "application/vnd.ms-excel")},
                )
            check("预览 HTTP 200", resp.status_code == 200, f"{resp.status_code} {resp.text[:300]}")
            preview = resp.json()["data"]
            summary = preview["summary"]
            print(f"      预览汇总：{summary} 总户数={preview['totalHouseholds']}")
            check(
                "原样文件全部无变化（导出↔导入闭环）",
                summary.get("no_change", 0) == preview["totalHouseholds"] and summary.get("error", 0) == 0,
                str(summary),
            )
            for h in preview["households"][:5]:
                if h["warnings"]:
                    print(f"      样例告警 {h['cbfbm']}: {h['warnings'][:2]}")

            # 3. 编号改坏 → 前缀拦截（错误路径）
            bad_households = [dict(b, cbfbm=("9" + b["cbfbm"][1:]) if b["cbfbm"].startswith(batch["regionCode"]) else b["cbfbm"]) for b in blocks[:3]]
            wb = m.SurveyServiceExcelTransferMixin._build_template_workbook("改坏编号", bad_households)
            bio_path = OUT_DIR / "bad_prefix.xls"
            import io

            bio = io.BytesIO()
            wb.save(bio)
            bio_path.write_bytes(bio.getvalue())
            with open(bio_path, "rb") as f:
                resp = client.post(
                    f"/surveys/batches/{batch_id}/contractors-xls/preview",
                    files={"file": ("bad.xls", f, "application/vnd.ms-excel")},
                )
            bad_preview = resp.json()["data"]
            check(
                "改坏编号的户被标记 error 且错误信息含区域码",
                bad_preview["summary"].get("error", 0) >= 3
                and all(any("开头" in e for e in h["errors"]) for h in bad_preview["households"][:3]),
                str(bad_preview["summary"]),
            )

            # 4. 导入错误文件 → 逐户失败、不落库
            with open(bio_path, "rb") as f:
                resp = client.post(
                    f"/surveys/batches/{batch_id}/contractors-xls/import",
                    files={"file": ("bad.xls", f, "application/vnd.ms-excel")},
                )
            check("导入（错误文件）HTTP 200", resp.status_code == 200, f"{resp.status_code} {resp.text[:300]}")
            imported = resp.json()["data"]
            check(
                "错误文件逐户失败",
                imported["summary"].get("failed", 0) >= 3,
                str(imported["summary"]),
            )
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()

    print()
    if FAILED:
        print(f"共 {len(FAILED)} 项失败：{FAILED}")
        sys.exit(1)
    print("在线验收全部通过（未修改任何业务数据）")


if __name__ == "__main__":
    main()
