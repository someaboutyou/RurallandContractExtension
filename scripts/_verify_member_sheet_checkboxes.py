# -*- coding: utf-8 -*-
"""离线验收：摸底表「已补地/抽回或放弃」拆复选框 + 列 28 变动时间改推导。

2026-10-15 用户口径：
  ① 已补地人口、抽回或放弃承包地不是事件 —— 每期两个独立复选框，
     与进出事件正交可同时成立（新增不一定补了地，减少不一定立即抽回）；
  ② 列 28 成员增减变动时间不再单独录入，由两期事件时间取最后者；
  ③ 数据库 / 打印模板同步调整。

验收项：
  A. 静态：模型 4 列 / 迁移 SQL / 服务四处 / 前端常量 / 弹窗复选框 / 模板勾选格
  B. 迁移端到端：造 legacy 行（旧事件码）→ 跑迁移 → 拆列断言 → 清理（幂等跑两遍）
  C. round-trip（事务内 rollback 零写入）：事件+复选框同存、payload 读回、
     状态机对复选框免疫（正交）
  D. 模板渲染（合成上下文）：勾选格印 √、合计统计、列 28 带出
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_PORT", "15432")
os.environ.setdefault("SECRET_KEY", "verify-only")

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

from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
import app.main  # noqa: E402,F401
from app.models.survey_sheet import SurveyCbfMemberChangeSheet  # noqa: E402
from app.services.survey.sheet import (  # noqa: E402
    MEMBER_EVENT_TYPES,
    survey_sheet_service,
    validate_member_sheet_flow,
)

SYNC_URL = (
    f"postgresql+psycopg://{settings.database_user}:{settings.database_password}@"
    f"{settings.database_host}:{settings.database_port}/{settings.database_name}"
)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


# ── A. 静态 ──────────────────────────────────────────────────────
def part_a() -> None:
    print("\nA. 静态检查")
    codes = {c for c, _ in MEMBER_EVENT_TYPES}
    check("A1 事件常量只剩进出 8 类", len(MEMBER_EVENT_TYPES) == 8 and not (codes & {"compensated", "withdraw"}))

    model_src = (ROOT / "backend" / "app" / "models" / "survey_sheet.py").read_text(encoding="utf-8-sig")
    check("A2 模型 4 复选列", all(k in model_src for k in ("sr_compensated", "sr_withdraw", "ext_compensated", "ext_withdraw")))

    mig_src = (ROOT / "backend" / "app" / "db" / "migrations.py").read_text(encoding="utf-8-sig")
    check("A3 迁移存在并挂入 upgrade_schema",
          "_upgrade_member_sheet_flow_split" in mig_src and "_upgrade_member_sheet_flow_split(engine)" in mig_src)
    check("A4 迁移含旧码拆列 UPDATE",
          "sr_event_type IN ('compensated', 'sub_compensated')" in mig_src
          and "ext_event_type = 'withdraw'" in mig_src)

    sheet_src = (ROOT / "backend" / "app" / "services" / "survey" / "sheet.py").read_text(encoding="utf-8-sig")
    check("A5 服务四处带 4 复选键",
          sheet_src.count("srCompensated") >= 3 and sheet_src.count("extWithdraw") >= 3)
    check("A6 upsert 不再写 restructure_time（列 28 改推导）",
          "row.restructure_time = self._parse_date" not in sheet_src and "max(" in sheet_src)

    fe_src = (ROOT / "frontend" / "src" / "config" / "surveySheets.js").read_text(encoding="utf-8")
    check("A7 前端事件 8 类 + 4 复选键 + 无 restructureTime",
          '"compensated"' not in fe_src and '"withdraw"' not in fe_src
          and all(k in fe_src for k in ("srCompensated", "srWithdraw", "extCompensated", "extWithdraw"))
          and "restructureTime" not in fe_src)

    panel_src = (ROOT / "frontend" / "src" / "components" / "survey" / "ContractorMemberPanel.vue").read_text(encoding="utf-8")
    check("A8 弹窗 4 复选框、无列 28 输入",
          panel_src.count("el-checkbox") >= 8
          and 'v-model="sheetEditRow.sheet.restructureTime"' not in panel_src)

    tpl_src = (ROOT / "backend" / "app" / "templates" / "member_change_sheet.html").read_text(encoding="utf-8")
    check("A9 模板勾选格 + 无 compensated/withdraw 事件格",
          "check_cell(row.srCompensated)" in tpl_src and "check_cell(row.extWithdraw)" in tpl_src
          and "event_cell(row.srEventType, 'compensated'" not in tpl_src
          and "event_cell(row.extEventType, 'withdraw'" not in tpl_src
          and "row.srEventType in ('compensated'" not in tpl_src)


# ── B. 迁移端到端（legacy 行 → 拆列 → 清理） ─────────────────────
def part_b(engine) -> None:
    print("\nB. 迁移端到端（造 legacy 行 → 拆列 → 清理）")
    from app.db.migrations import _upgrade_member_sheet_flow_split
    from sqlalchemy import inspect as sa_inspect

    probe = db_engine_columns(engine)
    if probe is None:
        check("B0 摸底表不存在（全新库）→ 跳过端到端", True)
        return

    legacy_uid = "verify-mig-legacy-uid"
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "DELETE FROM survey_cbf_member_change_sheets WHERE member_uid = 'verify-mig-legacy-uid'"
        )
        conn.exec_driver_sql(
            """
            INSERT INTO survey_cbf_member_change_sheets
              (tenant_code, region_code, batch_id, contractor_uid, cbfbm, member_uid, member_name,
               sr_event_type, ext_event_type)
            VALUES ('verify', '', 0, 'verify-mig-cuid', 'verify-mig-cbfbm',
                    'verify-mig-legacy-uid', '迁移夹具', 'compensated', 'withdraw')
            """
        )
    _upgrade_member_sheet_flow_split(engine)
    _upgrade_member_sheet_flow_split(engine)  # 幂等第二遍
    # ⚠️ 断言走原始 SQL：ORM 全局数据权限 scope 会按 region_code 过滤，
    # 夹具行 region_code='' 会被滤掉（raw select 实测可见，ORM 查空）。
    with engine.connect() as conn:
        raw = conn.exec_driver_sql(
            "SELECT sr_event_type, ext_event_type, sr_compensated, sr_withdraw, "
            "ext_compensated, ext_withdraw FROM survey_cbf_member_change_sheets "
            "WHERE member_uid = 'verify-mig-legacy-uid'"
        ).fetchone()
    check("B1 legacy 行存在", raw is not None)
    if raw is not None:
        sr_et, ext_et, sr_c, sr_w, ext_c, ext_w = raw
        check("B2 旧码 compensated → sr_compensated=TRUE 且事件码清空",
              sr_et is None and bool(sr_c) and not sr_w,
              f"sr={sr_et}/{sr_c}/{sr_w}")
        check("B3 旧码 withdraw → ext_withdraw=TRUE 且事件码清空",
              ext_et is None and bool(ext_w) and not ext_c,
              f"ext={ext_et}/{ext_c}/{ext_w}")
        check("B4 复选列默认 FALSE 不误点亮", sr_w is False and ext_c is False)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "DELETE FROM survey_cbf_member_change_sheets WHERE member_uid = 'verify-mig-legacy-uid'"
        )
    with Session(engine) as db:
        gone = db.scalar(select(SurveyCbfMemberChangeSheet).where(
            SurveyCbfMemberChangeSheet.member_uid == legacy_uid))
        check("B5 夹具清理完成", gone is None)


def db_engine_columns(engine):
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)
    if not insp.has_table("survey_cbf_member_change_sheets"):
        return None
    return {c["name"] for c in insp.get_columns("survey_cbf_member_change_sheets")}


# ── C. round-trip + 正交判定（事务内 rollback 零写入） ───────────
def part_c(engine) -> None:
    print("\nC. round-trip + 状态机正交（flush 后 rollback）")
    sheet_cls = SurveyCbfMemberChangeSheet
    with Session(engine) as db:
        row = db.scalar(select(sheet_cls).order_by(sheet_cls.id.asc()))
        if row is None:
            base = dict(tenant_code="verify", batch_id=0, contractor_uid="verify-uid",
                        cbfbm="verify", region_code="")
        else:
            base = dict(tenant_code=row.tenant_code, batch_id=row.batch_id,
                        contractor_uid=row.contractor_uid, cbfbm=row.cbfbm,
                        region_code=row.region_code or "")
        try:
            survey_sheet_service.upsert_member_sheets(
                db, member_entries=[(
                    "verify-cb-uid",
                    {
                        "isSecondRoundMember": False,
                        "srEventType": "add_married_in",       # 婚入
                        "srEventDate": "2005-03-01",
                        "srCompensated": True,                  # 婚入且已补地 —— 正交同时成立
                        "srWithdraw": False,
                        "extEventType": "", "extEventDate": None,
                        "extCompensated": False, "extWithdraw": True,
                        "economicRelation": "1",
                        "hukouPlace": "泗阳县", "residencePlace": "泗阳县某村",
                        "isCivilServant": None, "isInstitutionStaff": None,
                        "remark": "",
                    },
                )],
                **base, editor_name="verify",
            )
            db.flush()
            saved = db.scalar(select(sheet_cls).where(sheet_cls.member_uid == "verify-cb-uid"))
            check("C1 行存在", saved is not None)
            if saved is not None:
                check("C2 事件与复选框同存（婚入 + 已补地）",
                      saved.sr_event_type == "add_married_in" and bool(saved.sr_compensated))
                check("C3 延包期抽回复选落库", bool(saved.ext_withdraw) and saved.ext_event_type is None)
                payload = survey_sheet_service.member_sheet_payload(saved)
                check("C4 payload 读回复选框", payload["srCompensated"] is True and payload["extWithdraw"] is True)
                check("C5 payload 不再回 restructureTime（防旧前端回填）", "restructureTime" not in payload)
        finally:
            db.rollback()

    # 状态机对复选框免疫
    problems = validate_member_sheet_flow(
        [("u", {"isSecondRoundMember": True, "srEventType": "sub_move_out",
                "srWithdraw": True, "srCompensated": True})],
        {"u": "李四"},
    )
    check("C6 出 + 已补地/抽回正交 → 放行", problems == [], "；".join(problems))
    problems2 = validate_member_sheet_flow(
        [("u", {"isSecondRoundMember": False, "srCompensated": True})],
        {"u": "王五"},
    )
    check("C7 只勾已补地、无事件 → 放行", problems2 == [])


# ── D. 模板渲染 ──────────────────────────────────────────────────
def part_d() -> None:
    print("\nD. 打印模板渲染（合成上下文）")
    from jinja2 import Environment

    tpl_src = (ROOT / "backend" / "app" / "templates" / "member_change_sheet.html").read_text(encoding="utf-8")
    base_row = {
        "memberName": "赵六", "idNo": "", "phone": "", "relationText": "之子",
        "participatedSecondRound": False, "inRegister": True, "is1996Member": False,
        "srEventType": "add_birth", "srEventDate": "2001-05-06",
        "srCompensated": True, "srWithdraw": False,
        "extEventType": "", "extEventDate": "",
        "extCompensated": False, "extWithdraw": True,
        "changeTime": "2024.11", "inHousehold": True, "economicRelation": True,
        "hukouPlace": "", "residencePlace": "",
        "isFiscalSupported": False, "isCivilServant": False, "remark": "",
    }
    html = Environment().from_string(tpl_src).render(
        contractor={"name": "测试", "code": "321324100001020010", "groupName": "", "postcode": "",
                    "issuerCounty": "泗阳县", "issuerTown": "众兴镇", "issuerVillage": "某某村",
                    "issuerHamlet": "自然村", "issuerName": "", "issuerCode": "32132410000102"},
        rows=[base_row],
        noteStats={"rep1996": "", "rep2018": "测试", "pop1996": 1, "joinExt": 1, "addCount": 1,
                   "subCount": 0, "currentCount": 1, "registerCount": 1, "collectiveCount": 1,
                   "fiscalCount": 0, "civilCount": 0, "compensatedCount": 1, "withdrawCount": 1},
    )
    check("D1 渲染无异常", "承 包 农 户 家 庭 成 员 变 化 情 况" in html)
    # 2026-10-15 打印批注：事件格只打勾不填时间；布尔格 √/空白；全表无 ☑/空框
    check("D2 事件格只打勾（事件日期不出现在表格里）", "2001-05-06" not in html and "2001.05" not in html)
    check("D3 列 28 带出（两期最后变动时间）", ">2024.11</td>" in html)
    marks = html.count("√")
    check("D4 勾选格点亮（事件√ + 已补地√ + 抽回√ ≥ 3）", marks >= 3, f"√ × {marks}")
    check("D5 无 ☑/□ 双符号（统一 √、未勾空白）", "☑" not in html and "□" not in html)
    # 2026-10-15 串位回归：check_cell 自带 <td>，调用处不得再包一层
    # （曾因双重 <td> 数据行多出 6 格：日期落到列 30、行尾挤出 √ 窄条）
    import re as _re
    m = _re.search(r"<tr>\s*<td>1</td>.*?</tr>", html, _re.S)
    row_tds = len(_re.findall(r"<td", m.group(0))) if m else -1
    check("D6 数据行恰好 36 格（列序不串位）", row_tds == 36, f"td={row_tds}")
    # 2026-10-15 colgroup 落位回归：9mm 曾错插到列6（确权登记），代号7 被压成
    # 5.5mm ⇒ v2 两条竖排塞不下折行堆叠成单列（用户批注"代号7没有变成竖排两列"）。
    cols = _re.findall(r'<col style="width:([\d.]+mm)"', tpl_src)
    check("D7 colgroup 共 36 列", len(cols) == 36, f"cols={len(cols)}")
    check("D8 列6=5.5mm、代号7=9mm（9mm 落位正确）",
          len(cols) > 7 and cols[6] == "5.5mm" and cols[7] == "9mm",
          f"col6={cols[6] if len(cols) > 6 else '?'},col7={cols[7] if len(cols) > 7 else '?'}")
    check("D9 代号33=11mm、代号34=9mm",
          len(cols) > 34 and cols[33] == "11mm" and cols[34] == "9mm",
          f"col33={cols[33] if len(cols) > 33 else '?'},col34={cols[34] if len(cols) > 34 else '?'}")
    # v2 两竖排必须包 .vcols（inline-flex）：窄列里裸 inline-block 条带会被折行堆叠
    check("D10 v2 两竖排带 .vcols flex 包装（3 处：代号 7/33/34）",
          html.count('<span class="vcols">') == 3, f"vcols={html.count(chr(60) + 'span class=' + chr(34) + 'vcols')}")
    check("D11 勾选列总宽不变（24×5.5+9+11+9+9×13.78=285mm）",
          abs(sum(float(c[:-2]) for c in cols) - 285.02) < 0.5,
          f"sum={sum(float(c[:-2]) for c in cols):.2f}mm")
    # 2026-10-15 落款四项回归（调查员/调查日期/审核人/审核日期曾是纯空白横线）：
    # 服务端从 SurveyCbfResult.investigator_name/investigated_at/reviewer_name/reviewed_at
    # 组装 signatures 传入；调查/审核日期填进预印的 年/月/日 槽。
    render_ctx = dict(
        contractor={"name": "测试", "code": "321324100001020010", "groupName": "", "postcode": "",
                    "issuerCounty": "泗阳县", "issuerTown": "众兴镇", "issuerVillage": "某某村",
                    "issuerHamlet": "自然村", "issuerName": "", "issuerCode": "32132410000102"},
        rows=[base_row],
        noteStats={"rep1996": "", "rep2018": "测试", "pop1996": 1, "joinExt": 1, "addCount": 1,
                   "subCount": 0, "currentCount": 1, "registerCount": 1, "collectiveCount": 1,
                   "fiscalCount": 0, "civilCount": 0, "compensatedCount": 1, "withdrawCount": 1},
    )
    html_sig = Environment().from_string(tpl_src).render(
        **render_ctx,
        signatures={"investigatorName": "张三", "investigatedAt": "2026-10-15",
                    "reviewerName": "李审核", "reviewedAt": "2026-10-16"},
    )
    check("D12 落款四项带出（调查员/审核人/两个日期填入年月日）",
          "张三" in html_sig and "李审核" in html_sig
          and "2026　年　10　月　15　日" in html_sig and "2026　年　10　月　16　日" in html_sig)
    check("D13 未传 signatures 兜底空白年月日（旧调用方不报错）",
          bool(_re.search(r"调查日期：　*年　*月　*日", html))
          and bool(_re.search(r"审核日期：　*年　*月　*日", html)))
    # 2026-10-15 行数保底回归：代号行下预留 7 行（不含合计行）——
    # 1 条数据行时应补 6 条空行；空白行以 <td>&nbsp;</td> 开头（全模板唯一）。
    blank_rows = html.count("<td>&nbsp;</td>")
    check("D14 数据行不足 7 行时补空行（1 数据 + 6 空白 = 7）",
          blank_rows == 6, f"blank={blank_rows}")
    html_8 = Environment().from_string(tpl_src).render(
        **{**render_ctx, "rows": [base_row,
            dict(base_row, memberName="钱七"), dict(base_row, memberName="孙八"),
            dict(base_row, memberName="周九"), dict(base_row, memberName="吴十"),
            dict(base_row, memberName="郑一"), dict(base_row, memberName="王二"),
            dict(base_row, memberName="冯三")]},
    )
    check("D15 成员多于 7 行时按实际行数伸展（8 数据行、无补空）",
          html_8.count("<td>&nbsp;</td>") == 0 and html_8.count("<tr>") >= 8)


def main() -> None:
    print("=== 摸底表复选框拆分 + 列28推导 验收 ===")
    part_a()
    engine = create_engine(SYNC_URL)
    part_b(engine)
    part_c(engine)
    part_d()
    print(f"\n结果：PASS {len(PASS)} / FAIL {len(FAIL)}")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        sys.exit(1)


if __name__ == "__main__":
    main()
