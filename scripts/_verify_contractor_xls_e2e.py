# -*- coding: utf-8 -*-
"""端到端验收（临时库，不碰真实数据）：

1. 建临时库 erlunyanbao_xls_verify → 临时后端（8002）自动 bootstrap；
2. 建调查批次 + 1 户承包方（页面同源 create_contractor + update_result）；
3. 导出 xls → 解析 → 修改（改电话/改成员名/加成员）→ 预览 → 导入；
4. 核对：成员对比修改/新增正确、变化记录（survey_change_records/diffs）与页面
   保存同源生成、任务计数更新；
5. 再次导入同一文件 → 全部 no_change（幂等）；
6. 删除临时库。

运行：runtime/windows/python/python.exe scripts/_verify_contractor_xls_e2e.py
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

# 注入 runtime.env（数据库口令等），再覆盖为临时库
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip()
os.environ["DATABASE_NAME"] = "erlunyanbao_xls_verify"
# ⛔ 区域必须与 license 授权的系统区域码一致（本机 150526 扎鲁特旗），否则 403
os.environ.setdefault("REGION_SEED_COUNTIES", "150526")
os.environ["BACKEND_PORT"] = "8002"

TEMP_DB = os.environ["DATABASE_NAME"]
PORT = 8002
BASE = f"http://127.0.0.1:{PORT}/api/v1"

FAILED = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  {detail}" if not cond else ""))
    if not cond:
        FAILED.append(name)


def make_engine(dbname: str):
    from urllib.parse import quote_plus

    from sqlalchemy import create_engine

    uri = (
        f"postgresql+psycopg://{os.environ['DATABASE_USER']}:{quote_plus(os.environ['DATABASE_PASSWORD'])}"
        f"@{os.environ['DATABASE_HOST']}:{os.environ['DATABASE_PORT']}/{dbname}"
    )
    return create_engine(uri, isolation_level="AUTOCOMMIT")


def recreate_temp_db() -> None:
    from sqlalchemy import text

    eng = make_engine("postgres")
    with eng.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEMP_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEMP_DB}"'))


def drop_temp_db() -> None:
    from sqlalchemy import text

    eng = make_engine("postgres")
    with eng.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEMP_DB}" WITH (FORCE)'))


def db_query(sql: str):
    eng = make_engine(TEMP_DB)
    with eng.connect() as conn:
        return conn.exec_driver_sql(sql).fetchall()


def main():
    from app.core.security import create_access_token
    from app.services.survey import excel_transfer as m

    token = create_access_token("1")
    headers = {"Authorization": f"Bearer {token}"}

    print("== 重建临时库 ==")
    recreate_temp_db()

    print("== 启动临时后端（自动 bootstrap）==")
    server = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    try:
        import httpx

        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                r = httpx.get(f"{BASE}/auth/me", headers=headers, timeout=3)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            print("临时后端启动超时")
            sys.exit(2)

        with httpx.Client(base_url=BASE, headers=headers, timeout=120) as client:
            # ── 种源数据（临时库直接插源结果表，create_batch 从这里初始化快照）──
            import uuid as _uuid

            cbf_uid = str(_uuid.uuid4())
            eng = make_engine(TEMP_DB)
            from sqlalchemy import text

            with eng.begin() as conn:
                conn.execute(text(
                    "INSERT INTO survey_cbf_result (tenant_code, region_code, contractor_uid, cbfbm, cbflx,"
                    " cbfmc, cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfcysl, group_region_code, group_region_name,"
                    " survey_status, result_status, is_changed, change_type, cbfdcrq, cbfdcy, initialized_at)"
                    " VALUES ('150526','150526',:uid,'150526198211190001','1','庞春云','1','321324198211193148',"
                    "'扎鲁特旗巨日合镇试验村一组','029100','13571383767',2,'150526','内蒙古自治区/通辽市/扎鲁特旗',"
                    "'not_surveyed','normal',false,'none','2015-03-05','村长', now())"
                ), {"uid": cbf_uid})
                for idx, (name, idno, gender, relation, coowner) in enumerate([
                    ("庞春云", "321324198211193148", "2", "02", "1"),
                    ("江伟峰", "32132419820127143X", "1", "20", "1"),
                ]):
                    conn.execute(text(
                        "INSERT INTO survey_cbf_jtcy_result (tenant_code, region_code, contractor_uid, member_uid,"
                        " cbfbm, cyxm, cyzjlx, cyzjhm, cyxb, yhzgx, sfgyr, member_result_status, survey_status,"
                        " is_changed, is_household_head, is_urban_settled, is_married_out_woman, is_deceased,"
                        " is_five_guarantees, initialized_at)"
                        " VALUES ('150526','150526',:uid,:muid,'150526198211190001',:name,'1',:idno,:gender,"
                        ":relation,:coowner,'normal','not_surveyed',false,:is_head,false,false,false,false, now())"
                    ), {"uid": cbf_uid, "muid": str(_uuid.uuid4()), "name": name, "idno": idno,
                        "gender": gender, "relation": relation, "coowner": coowner, "is_head": idx == 0})
            print("      已种源数据：1 户 2 成员")

            # ── 建批次 ──
            r = client.post("/surveys/batches", json={
                "regionCode": "150526", "regionName": "内蒙古自治区/通辽市/扎鲁特旗", "batchName": "xls验收批次",
                "assigneeIds": [1],
            })
            check("创建调查批次", r.status_code == 200, r.text[:300])
            batch = r.json()["data"]
            batch_id = batch["id"]
            print(f"      批次 id={batch_id} 区域码={batch['regionCode']}")

            uid = cbf_uid

            # ── 导出 ──
            r = client.get(f"/surveys/batches/{batch_id}/contractors-xls")
            check("导出 xls", r.status_code == 200 and r.content[:4] == b"\xd0\xcf\x11\xe0", str(r.status_code))
            blocks, warnings = m.SurveyServiceExcelTransferMixin.parse_contractors_xls(r.content)
            check("导出解析：1 户 2 成员无告警", len(blocks) == 1 and len(blocks[0]["members"]) == 2 and not warnings,
                  f"{len(blocks)}户 {[len(b['members']) for b in blocks]} {warnings[:2]}")
            block = blocks[0]
            check("导出编号文本化", block["cbfbm"] == "150526198211190001", block["cbfbm"])
            check("导出关系码转中文", block["members"][0]["relation_raw"] == "户主", block["members"][0]["relation_raw"])
            check("导出调查日期", block["survey_date"] == "2015-03-05", str(block["survey_date"]))

            # ── 模拟用户改 Excel：改电话、改成员姓名、新增一名成员 ──
            block["mobile"] = "13900000000"
            block["address"] = "扎鲁特旗巨日合镇试验村一组（新）"
            block["members"][1]["name"] = "江伟峰（改）"
            block["members"].append({
                "name": "江晓珍", "gender_raw": "女", "id_type_raw": "居民身份证",
                "id_no": "321324198601023126", "relation_raw": "女", "is_co_owner_raw": "是", "note": "新增成员",
            })

            import io

            # 解析块（cbflx_raw 等原始键）还原成模板构建所需键后重写文件
            rebuild = [dict(b, cbflx=b["cbflx_raw"]) for b in blocks]
            wb = m.SurveyServiceExcelTransferMixin._build_template_workbook("xls验收批次", rebuild)
            bio = io.BytesIO()
            wb.save(bio)
            modified = bio.getvalue()

            # ── 预览 ──
            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/preview",
                files={"file": ("modified.xls", modified, "application/vnd.ms-excel")},
            )
            check("预览 HTTP 200", r.status_code == 200, r.text[:300])
            preview = r.json()["data"]
            house = preview["households"][0]
            print(f"      预览：action={house['action']} 承包方变化={house['contractorChanges']} 成员={house['memberSummary']}")
            check("预览动作=update", house["action"] == "update", house["action"])
            check("预览识别承包方字段变化", set(house["contractorChanges"]) >= {"联系电话", "承包方地址"}, str(house["contractorChanges"]))
            check("预览识别成员修改", len(house["memberSummary"]["updated"]) == 1, str(house["memberSummary"]))
            check("预览识别成员新增", house["memberSummary"]["added"] == ["江晓珍"], str(house["memberSummary"]))

            # ── 导入 ──
            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import",
                files={"file": ("modified.xls", modified, "application/vnd.ms-excel")},
            )
            check("导入 HTTP 200", r.status_code == 200, r.text[:300])
            result = r.json()["data"]
            print(f"      导入汇总：{result['summary']}")
            check("导入 1 户 updated", result["summary"].get("updated") == 1, str(result["summary"]))

            # ── 核对库内结果 ──
            r = client.get(f"/surveys/batches/{batch_id}/results/{uid}")
            data = r.json()["data"]
            check("联系电话已更新", data["mobile"] == "13900000000", str(data["mobile"]))
            check("地址已更新", data["address"].endswith("（新）"), data["address"])
            names = {mem["name"] for mem in data["familyMembers"]}
            check("成员改名落库", "江伟峰（改）" in names, str(names))
            check("新增成员落库", "江晓珍" in names, str(names))
            check("成员数=3", len(data["familyMembers"]) == 3 and data["memberCount"] == 3,
                  f"{len(data['familyMembers'])}/{data['memberCount']}")
            xiaozhen = next(mem for mem in data["familyMembers"] if mem["name"] == "江晓珍")
            check("新增成员 memberResultStatus=added", xiaozhen["memberResultStatus"] == "added", xiaozhen["memberResultStatus"])
            check("新增成员变化原因已写", bool(xiaozhen["changeReason"]), str(xiaozhen["changeReason"]))
            check("户主唯一", sum(1 for mem in data["familyMembers"] if mem["isHouseholdHead"]) == 1)

            # 变化记录（与页面保存同源）
            rows = db_query("select change_type, change_reason from survey_change_records where batch_id=%d" % batch_id)
            print(f"      变化记录：{rows}")
            check("生成 SurveyChangeRecord", len(rows) >= 1, str(rows))
            diffs = db_query("select entity_type, field_name from survey_change_diffs where batch_id=%d" % batch_id)
            print(f"      差异行数：{len(diffs)}")
            check("生成 SurveyChangeDiff", len(diffs) >= 1, str(diffs))
            task = db_query("select task_status, has_change, change_count from survey_cbf_base where batch_id=%d" % batch_id)
            print(f"      任务态：{task}")
            check("任务态=已调查且有变化", task and task[0][0] == "surveyed" and bool(task[0][1]), str(task))

            # ── 幂等：原样再导入 → 全部 no_change ──
            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import",
                files={"file": ("modified.xls", modified, "application/vnd.ms-excel")},
            )
            again = r.json()["data"]
            check("重复导入全部 no_change", again["summary"].get("no_change") == 1, str(again["summary"]))

            # ── 已确认户跳过 ──
            r = client.post(f"/surveys/batches/{batch_id}/results/{uid}/confirm", json={})
            check("确认该户", r.status_code == 200, r.text[:200])
            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import",
                files={"file": ("modified.xls", modified, "application/vnd.ms-excel")},
            )
            after_confirm = r.json()["data"]
            check("已确认户自动跳过", after_confirm["summary"].get("skipped") == 1, str(after_confirm["summary"]))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()
        print("== 清理临时库 ==")
        drop_temp_db()

    print()
    if FAILED:
        print(f"共 {len(FAILED)} 项失败：{FAILED}")
        sys.exit(1)
    print("端到端验收全部通过")


if __name__ == "__main__":
    main()
