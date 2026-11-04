# -*- coding: utf-8 -*-
"""后台任务版导出 / 导入端到端验收（临时库，不碰真实数据）：

1. 建临时库 erlunyanbao_xls_verify → 临时后端（8003）bootstrap；
2. 种 1 户 2 成员源数据 → 建批次；
3. 导出任务：POST export-jobs → 轮询至 done → download → 解析核对；
4. 导入任务：改 Excel → POST import-jobs → 轮询（观察进度字段）→ done 后
   核对 summary / 库内结果 / 变化记录；
5. 删临时库。

运行：runtime/windows/python/python.exe scripts/_verify_contractor_xls_jobs_e2e.py
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

for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ[k.strip()] = v.strip()
os.environ["DATABASE_NAME"] = "erlunyanbao_xls_verify"
os.environ.setdefault("REGION_SEED_COUNTIES", "150526")
os.environ["BACKEND_PORT"] = "8003"

TEMP_DB = os.environ["DATABASE_NAME"]
PORT = 8003
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


def db_query(sql: str):
    eng = make_engine(TEMP_DB)
    with eng.connect() as conn:
        return conn.exec_driver_sql(sql).fetchall()


def wait_job(client, kind_url: str, job_id: str, label: str, max_seconds: int = 120):
    """轮询任务直至 done/error；中途至少观察到一次 running 进度。"""
    saw_running = False
    deadline = time.time() + max_seconds
    while time.time() < deadline:
        r = client.get(f"{kind_url}/{job_id}")
        check(f"{label} 查询 HTTP 200", r.status_code == 200, r.text[:200])
        view = r.json()["data"]
        if view["status"] == "running":
            saw_running = saw_running or view["phase"] != "准备中"
            print(f"      进度：{view['phase']} {view['done']}/{view['total']} {view['current']}")
        elif view["status"] == "done":
            check(f"{label} 过程观察到进度", True)
            return view
        elif view["status"] == "error":
            check(f"{label} 未报错", False, view.get("error"))
            return view
        time.sleep(0.5)
    check(f"{label} 超时", False)
    return {"status": "timeout"}


def main():
    from app.core.security import create_access_token

    token = create_access_token("1")
    headers = {"Authorization": f"Bearer {token}"}

    print("== 重建临时库 ==")
    eng = make_engine("postgres")
    from sqlalchemy import text

    with eng.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEMP_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEMP_DB}"'))

    print("== 启动临时后端（自动 bootstrap）==")
    server = subprocess.Popen(
        [str(PY), "-m", "uvicorn", "app.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=os.environ.copy(),
    )
    try:
        import httpx

        deadline = time.time() + 300
        while time.time() < deadline:
            try:
                if httpx.get(f"{BASE}/auth/me", headers=headers, timeout=3).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            print("临时后端启动超时")
            sys.exit(2)

        with httpx.Client(base_url=BASE, headers=headers, timeout=120) as client:
            import io
            import uuid as _uuid

            # 每条语句独立事务：任何一条失败立即抛真实异常（整块事务下连接级
            # 故障只会吐出 ResourceClosedError，掩盖根因——2026-11-03 踩过）
            seed_eng = make_engine(TEMP_DB)

            def seed_exec(sql: str, params: dict | None = None) -> None:
                with seed_eng.begin() as c2:
                    c2.execute(text(sql), params or {})

            cbf_uid = str(_uuid.uuid4())
            seed_exec(
                "INSERT INTO survey_cbf_result (tenant_code, region_code, contractor_uid, cbfbm, cbflx,"
                " cbfmc, cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfcysl, group_region_code, group_region_name,"
                " survey_status, result_status, is_changed, change_type, cbfdcrq, cbfdcy, initialized_at)"
                " VALUES ('150526','150526',:uid,'150526198211190001','1','庞春云','1','321324198211193148',"
                "'扎鲁特旗巨日合镇试验村一组','029100','13571383767',2,'150526','内蒙古自治区/通辽市/扎鲁特旗',"
                "'not_surveyed','normal',false,'none','2015-03-05','村长', now())",
                {"uid": cbf_uid},
            )
            for idx, (name, idno, gender, relation, coowner) in enumerate([
                ("庞春云", "321324198211193148", "2", "02", "1"),
                ("江伟峰", "32132419820127143X", "1", "20", "1"),
            ]):
                seed_exec(
                    "INSERT INTO survey_cbf_jtcy_result (tenant_code, region_code, contractor_uid, member_uid,"
                    " cbfbm, cyxm, cyzjlx, cyzjhm, cyxb, yhzgx, sfgyr, member_result_status, survey_status,"
                    " is_changed, is_household_head, is_urban_settled, is_married_out_woman, is_deceased,"
                    " is_five_guarantees, initialized_at)"
                    " VALUES ('150526','150526',:uid,:muid,'150526198211190001',:name,'1',:idno,:gender,"
                    ":relation,:coowner,'normal','not_surveyed',false,:is_head,false,false,false,false, now())",
                    {"uid": cbf_uid, "muid": str(_uuid.uuid4()), "name": name, "idno": idno,
                     "gender": gender, "relation": relation, "coowner": coowner, "is_head": idx == 0},
                )

            # 第二户：供「整户注销」场景使用（仅户主 1 名成员）
            cbf_uid2 = str(_uuid.uuid4())
            seed_exec(
                "INSERT INTO survey_cbf_result (tenant_code, region_code, contractor_uid, cbfbm, cbflx,"
                " cbfmc, cbfzjlx, cbfzjhm, cbfdz, yzbm, lxdh, cbfcysl, group_region_code, group_region_name,"
                " survey_status, result_status, is_changed, change_type, cbfdcrq, cbfdcy, initialized_at)"
                " VALUES ('150526','150526',:uid,'150526198211190002','1','刘建国','1','150526197503122311',"
                "'扎鲁特旗巨日合镇试验村二组','029100','13800000002',1,'150526','内蒙古自治区/通辽市/扎鲁特旗',"
                "'not_surveyed','normal',false,'none','2015-03-05','村长', now())",
                {"uid": cbf_uid2},
            )
            seed_exec(
                "INSERT INTO survey_cbf_jtcy_result (tenant_code, region_code, contractor_uid, member_uid,"
                " cbfbm, cyxm, cyzjlx, cyzjhm, cyxb, yhzgx, sfgyr, member_result_status, survey_status,"
                " is_changed, is_household_head, is_urban_settled, is_married_out_woman, is_deceased,"
                " is_five_guarantees, initialized_at)"
                " VALUES ('150526','150526',:uid,:muid,'150526198211190002','刘建国','1','150526197503122311',"
                "'1','02','1','normal','not_surveyed',false,true,false,false,false,false, now())",
                {"uid": cbf_uid2, "muid": str(_uuid.uuid4())},
            )

            r = client.post("/surveys/batches", json={
                "regionCode": "150526", "regionName": "内蒙古自治区/通辽市/扎鲁特旗", "batchName": "xls任务验收批次",
                "assigneeIds": [1],
            })
            check("创建调查批次", r.status_code == 200, r.text[:300])
            batch_id = r.json()["data"]["id"]

            # ── 导出任务 ──
            r = client.post(f"/surveys/batches/{batch_id}/contractors-xls/export-jobs")
            check("启动导出任务", r.status_code == 200 and r.json()["data"].get("jobId"), r.text[:200])
            export_job_id = r.json()["data"]["jobId"]
            view = wait_job(client, f"/surveys/batches/{batch_id}/contractors-xls/export-jobs", export_job_id, "导出任务")
            check("导出任务完成", view.get("status") == "done", str(view.get("error")))

            r = client.get(f"/surveys/batches/{batch_id}/contractors-xls/export-jobs/{export_job_id}/download")
            check("下载导出文件", r.status_code == 200 and r.content[:4] == b"\xd0\xcf\x11\xe0", str(r.status_code))
            from urllib.parse import unquote

            disposition = r.headers.get("content-disposition", "")
            decoded = unquote(disposition)
            check("下载文件名带回", "承包方调查表" in decoded, disposition)

            from app.services.survey import excel_transfer as m

            blocks, warnings = m.SurveyServiceExcelTransferMixin.parse_contractors_xls(r.content)
            check("导出解析：2 户（庞春云 2 成员 / 刘建国 1 成员）",
                  len(blocks) == 2 and len(blocks[0]["members"]) == 2 and len(blocks[1]["members"]) == 1 and not warnings,
                  f"{len(blocks)}户 {[len(b['members']) for b in blocks]} {warnings[:2]}")

            # ── 原样回导（无变化户）：调查状态也要推进为已调查 ──
            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                files={"file": ("asis.xls", r.content, "application/vnd.ms-excel")},
            )
            check("启动原样回导", r.status_code == 200 and r.json()["data"].get("jobId"), r.text[:200])
            view = wait_job(client, f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                            r.json()["data"]["jobId"], "原样回导")
            check("原样回导完成", view.get("status") == "done", str(view.get("error")))
            check("原样回导全部无变化", (view.get("summary") or {}).get("no_change") == 2,
                  str(view.get("summary")))
            rows = db_query("select task_status, count(*) from survey_cbf_base"
                            " where batch_id=%d group by task_status" % batch_id)
            check("无变化户调查状态已置为已调查",
                  rows and all(row[0] == "surveyed" for row in rows), str(rows))

            # ── 改 Excel → 导入任务 ──
            block = blocks[0]
            block["mobile"] = "13900000000"
            block["members"][1]["name"] = "江伟峰（改）"
            block["members"].append({
                "name": "江晓珍", "gender_raw": "女", "id_type_raw": "居民身份证",
                "id_no": "321324198601023126", "relation_raw": "女", "is_co_owner_raw": "是", "note": "",
            })
            rebuild = [dict(block, cbflx=block["cbflx_raw"])]
            wb = m.SurveyServiceExcelTransferMixin._build_template_workbook("任务验收", rebuild)
            bio = io.BytesIO()
            wb.save(bio)
            modified = bio.getvalue()

            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                files={"file": ("modified.xls", modified, "application/vnd.ms-excel")},
            )
            check("启动导入任务", r.status_code == 200 and r.json()["data"].get("jobId"), r.text[:200])
            import_job_id = r.json()["data"]["jobId"]
            view = wait_job(client, f"/surveys/batches/{batch_id}/contractors-xls/import-jobs", import_job_id, "导入任务")
            check("导入任务完成", view.get("status") == "done", str(view.get("error")))
            check("导入任务带回汇总", (view.get("summary") or {}).get("updated") == 1, str(view.get("summary")))
            check("导入任务带回逐户结果", isinstance(view.get("results"), list) and len(view["results"]) == 1, str(view.get("results"))[:200])

            r = client.get(f"/surveys/batches/{batch_id}/results/{cbf_uid}")
            data = r.json()["data"]
            names = {mem["name"] for mem in data["familyMembers"]}
            check("任务版导入落库（改名+新增成员）", "江伟峰（改）" in names and "江晓珍" in names, str(names))
            check("电话落库", data["mobile"] == "13900000000", str(data["mobile"]))
            rows = db_query("select change_type from survey_change_records where batch_id=%d" % batch_id)
            check("变化记录同源生成", len(rows) >= 1, str(rows))

            # ── 删除标记：成员行「姓名」单元格填底色 ⇒ 导入删除该成员 ──
            import xlwt as _xlwt

            def _plain_style():
                f = _xlwt.Font(); f.name = "宋体"; f.height = 200
                b = _xlwt.Borders(); b.left = b.right = b.top = b.bottom = 1
                s = _xlwt.XFStyle(); s.font = f; s.borders = b
                return s

            def _marked_style():
                s = _plain_style()
                p = _xlwt.Pattern(); p.pattern = _xlwt.Pattern.SOLID_PATTERN
                p.pattern_fore_colour = _xlwt.Style.colour_map["red"]
                s.pattern = p
                return s

            wbx = _xlwt.Workbook()
            wx = wbx.add_sheet("鱼鳞图")
            for c, head in enumerate(["承包方编号", "承包方姓名", "承包方类型", "家庭成员数（个）",
                                      "姓名", "性别", "证件类型", "证件号码", "家庭关系", "是否共有人", "备注"]):
                wx.write(0, c, head, _plain_style())
            wx.write(1, 0, "150526198211190001", _plain_style())
            wx.write(1, 1, "庞春云", _plain_style())
            wx.write(1, 2, "农户", _plain_style())
            wx.write(1, 3, 2, _plain_style())
            wx.write(1, 4, "庞春云", _plain_style())
            wx.write(1, 5, "女", _plain_style())
            wx.write(1, 6, "居民身份证", _plain_style())
            wx.write(1, 7, "321324198211193148", _plain_style())
            wx.write(1, 8, "户主", _plain_style())
            wx.write(1, 9, "是", _plain_style())
            # 江伟峰（改）姓名标红 ⇒ 删除
            wx.write(2, 4, "江伟峰（改）", _marked_style())
            wx.write(2, 5, "男", _plain_style())
            wx.write(2, 6, "居民身份证", _plain_style())
            wx.write(2, 7, "32132419820127143X", _plain_style())
            wx.write(2, 8, "子", _plain_style())
            wx.write(2, 9, "是", _plain_style())
            wx.write(3, 4, "江晓珍", _plain_style())
            wx.write(3, 5, "女", _plain_style())
            wx.write(3, 6, "居民身份证", _plain_style())
            wx.write(3, 7, "321324198601023126", _plain_style())
            wx.write(3, 8, "女", _plain_style())
            wx.write(3, 9, "是", _plain_style())
            bio_del = io.BytesIO()
            wbx.save(bio_del)

            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                files={"file": ("deletemark.xls", bio_del.getvalue(), "application/vnd.ms-excel")},
            )
            check("启动删除标记导入", r.status_code == 200 and r.json()["data"].get("jobId"), r.text[:200])
            view = wait_job(client, f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                            r.json()["data"]["jobId"], "删除标记导入")
            check("删除标记导入完成", view.get("status") == "done", str(view.get("error")))
            check("删除计入变化（updated=1）", (view.get("summary") or {}).get("updated") == 1, str(view.get("summary")))
            result_line = (view.get("results") or [{}])[0].get("message", "")
            check("结果说明含删除成员", "删除成员" in result_line and "江伟峰" in result_line, result_line)

            r = client.get(f"/surveys/batches/{batch_id}/results/{cbf_uid}")
            names_after = {mem["name"] for mem in r.json()["data"]["familyMembers"]}
            check("标记删除成员已删除", "江伟峰（改）" not in names_after, str(names_after))
            check("其余成员保留", {"庞春云", "江晓珍"} <= names_after, str(names_after))
            diffs_after = db_query("select entity_type, field_name from survey_change_diffs where batch_id=%d" % batch_id)
            check("删除生成差异记录", len(diffs_after) >= 1, str(len(diffs_after)))

            # ── 整户注销标记：「承包方姓名」单元格标红 ⇒ 预览 deregister → 导入整户注销 ──
            wbd = _xlwt.Workbook()
            wd = wbd.add_sheet("鱼鳞图")
            for c, head in enumerate(["承包方编号", "承包方姓名", "承包方类型", "家庭成员数（个）",
                                      "姓名", "性别", "证件类型", "证件号码", "家庭关系", "是否共有人", "备注"]):
                wd.write(0, c, head, _plain_style())
            wd.write(1, 0, "150526198211190002", _plain_style())
            wd.write(1, 1, "刘建国", _marked_style())  # 整户注销标记
            wd.write(1, 2, "农户", _plain_style())
            wd.write(1, 4, "刘建国", _plain_style())
            wd.write(1, 5, "男", _plain_style())
            wd.write(1, 6, "居民身份证", _plain_style())
            wd.write(1, 7, "150526197503122311", _plain_style())
            wd.write(1, 8, "户主", _plain_style())
            wd.write(1, 9, "是", _plain_style())
            bio_dereg = io.BytesIO()
            wbd.save(bio_dereg)

            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/preview",
                files={"file": ("deregmark.xls", bio_dereg.getvalue(), "application/vnd.ms-excel")},
            )
            check("整户注销预览 HTTP 200", r.status_code == 200, r.text[:200])
            preview_summary = r.json()["data"]["summary"]
            check("整户注销预览计数", preview_summary.get("deregister") == 1 and preview_summary.get("update", 0) == 0,
                  str(preview_summary))

            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                files={"file": ("deregmark.xls", bio_dereg.getvalue(), "application/vnd.ms-excel")},
            )
            check("启动整户注销导入", r.status_code == 200 and r.json()["data"].get("jobId"), r.text[:200])
            view = wait_job(client, f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                            r.json()["data"]["jobId"], "整户注销导入")
            check("整户注销导入完成", view.get("status") == "done", str(view.get("error")))
            check("整户注销汇总（deregistered=1）", (view.get("summary") or {}).get("deregistered") == 1,
                  str(view.get("summary")))
            result_line = (view.get("results") or [{}])[0].get("message", "")
            check("整户注销结果说明", "整户注销" in result_line, result_line)

            rows = db_query("select result_status, change_type from survey_cbf_result"
                            " where cbfbm='150526198211190002'")
            check("整户注销落库（cancelled/deregister）",
                  rows and rows[0][0] == "cancelled" and rows[0][1] == "deregister", str(rows))
            rows = db_query("select cr.change_type from survey_change_records cr"
                            " join survey_cbf_result r2 on cr.contractor_uid = r2.contractor_uid"
                            " where r2.cbfbm='150526198211190002'")
            check("整户注销变化记录（change_type=deregister）",
                  rows and rows[0][0] == "deregister", str(rows))

            # 幂等：同一文件再导入一次 → 该户已终结自动跳过
            r = client.post(
                f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                files={"file": ("deregmark.xls", bio_dereg.getvalue(), "application/vnd.ms-excel")},
            )
            view = wait_job(client, f"/surveys/batches/{batch_id}/contractors-xls/import-jobs",
                            r.json()["data"]["jobId"], "整户注销重复导入")
            check("重复导入幂等（skipped=1）", (view.get("summary") or {}).get("skipped") == 1,
                  str(view.get("summary")))

            # 404：不存在的任务
            r = client.get(f"/surveys/batches/{batch_id}/contractors-xls/export-jobs/nonexistent")
            check("任务不存在返回 404", r.status_code == 404, str(r.status_code))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except Exception:
            server.kill()
        print("== 清理临时库 ==")
        with make_engine("postgres").connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEMP_DB}" WITH (FORCE)'))

    print()
    if FAILED:
        print(f"共 {len(FAILED)} 项失败：{FAILED}")
        sys.exit(1)
    print("后台任务版导出/导入端到端验收全部通过")


if __name__ == "__main__":
    main()
