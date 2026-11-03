# -*- coding: utf-8 -*-
"""离线验收：家庭成员摸底表补「现户口所在地（列31）/ 现居住地（列32）」。

2026-10-14 按试点模板原件（用户再次发出）：
  - 摸底弹窗分三块：①1996 年是否家庭成员（列7） ②1996—2018 增减+已补地
    ③2018—2026 增减+已补地；两期各自可填变动时间。
  - 新增收集：列31 现户口所在地、列32 现居住地（此前无录入、打印空白）。
  - 列7 口径修正：调查员直填值直接点亮，不再与确权在册求交。

验收项：
  A. 静态：模型/迁移/服务/前端常量/弹窗/打印模板 六处同步
  B. 迁移：_upgrade_member_sheet_places 真库执行 + 幂等（跑两遍）
  C. round-trip（事务内 flush 后 rollback，零写入）：
     upsert_member_sheets 带户籍/居住地 → member_sheet_payload 读回一致
  D. 打印模板渲染（Jinja from_string，合成上下文）：列31/32 落格、列7 直填点亮
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

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
import app.main  # noqa: E402,F401
from app.models.survey_sheet import SurveyCbfMemberChangeSheet  # noqa: E402
from app.services.survey.sheet import survey_sheet_service  # noqa: E402

SYNC_URL = (
    f"postgresql+psycopg://{settings.database_user}:{settings.database_password}@"
    f"{settings.database_host}:{settings.database_port}/{settings.database_name}"
)

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  — {detail}" if detail else ""))


# ── A. 静态六处同步 ──────────────────────────────────────────────
def part_a() -> None:
    print("\nA. 静态检查（六处同步）")
    model_src = (ROOT / "backend" / "app" / "models" / "survey_sheet.py").read_text(encoding="utf-8-sig")
    check("A1 模型有 hukou_place/residence_place 列", "hukou_place" in model_src and "residence_place" in model_src)

    mig_src = (ROOT / "backend" / "app" / "db" / "migrations.py").read_text(encoding="utf-8-sig")
    check(
        "A2 迁移函数存在且已挂入 upgrade_schema",
        "_upgrade_member_sheet_places" in mig_src and mig_src.count("_upgrade_member_sheet_places(engine)") >= 1,
    )

    sheet_src = (ROOT / "backend" / "app" / "services" / "survey" / "sheet.py").read_text(encoding="utf-8-sig")
    check(
        "A3 服务四处同步（EMPTY/payload/upsert/上下文）",
        sheet_src.count("hukouPlace") >= 3
        and sheet_src.count("residencePlace") >= 3
        and sheet_src.count("hukou_place") >= 3,
    )
    check(
        "A4 列7 改为调查员直填（不再与确权在册求交）",
        '"is1996Member": bool(row.is_second_round_member)' in sheet_src,
    )

    fe_const = (ROOT / "frontend" / "src" / "config" / "surveySheets.js").read_text(encoding="utf-8")
    check("A5 前端空表单常量含两新键", "hukouPlace" in fe_const and "residencePlace" in fe_const)

    panel_src = (ROOT / "frontend" / "src" / "components" / "survey" / "ContractorMemberPanel.vue").read_text(encoding="utf-8")
    check(
        # 2026-10-15 界面重构：标签去「列 N」术语，改按字段键 + 新文案断言
        "A6 弹窗有现户口所在地/现居住地录入控件",
        "现户口所在地" in panel_src and "现居住地" in panel_src
        and 'v-model="sheetEditRow.sheet.hukouPlace"' in panel_src
        and 'v-model="sheetEditRow.sheet.residencePlace"' in panel_src,
    )

    tpl_src = (ROOT / "backend" / "app" / "templates" / "member_change_sheet.html").read_text(encoding="utf-8")
    check(
        "A7 打印模板列31/32 落数据",
        "row.hukouPlace" in tpl_src and "row.residencePlace" in tpl_src,
    )


# ── B. 迁移真库执行 + 幂等 ────────────────────────────────────────
def part_b(engine) -> None:
    print("\nB. 迁移（真库 + 幂等）")
    from app.db.migrations import _upgrade_member_sheet_places
    from sqlalchemy import inspect as sa_inspect

    _upgrade_member_sheet_places(engine)
    _upgrade_member_sheet_places(engine)  # 第二遍必须不抛
    cols = {c["name"] for c in sa_inspect(engine).get_columns("survey_cbf_member_change_sheets")}
    check("B1 两列已存在且迁移可重复执行", {"hukou_place", "residence_place"}.issubset(cols))


# ── C. round-trip（事务内，rollback 零写入） ─────────────────────
def part_c(engine) -> None:
    print("\nC. 保存 → 读回 round-trip（flush 后 rollback）")
    sheet_cls = SurveyCbfMemberChangeSheet
    with Session(engine) as db:
        row = db.scalar(select(sheet_cls).order_by(sheet_cls.id.asc()))
        if row is None:
            check("C0 库内无摸底行，改用临时构造", True)
            base = dict(
                tenant_code="verify", batch_id=0, contractor_uid="verify-uid", cbfbm="verify",
                region_code="",
            )
        else:
            base = dict(
                tenant_code=row.tenant_code, batch_id=row.batch_id,
                contractor_uid=row.contractor_uid, cbfbm=row.cbfbm,
                region_code=row.region_code or "",
            )
            check("C0 取真实摸底行做夹具", True, f"cbfbm={row.cbfbm}")
        try:
            survey_sheet_service.upsert_member_sheets(
                db, member_entries=[(
                    "verify-member-uid",
                    {
                        # 2026-10-15 起有「在户状态机」闸门 + 已补地/抽回复选框：
                        # 夹具必须合法 —— 列7=否 + 二轮期婚入（非 1996 成员婚入，
                        # 最常见的合法进）+ 延包期已补地（复选框，与事件正交）
                        "isSecondRoundMember": False,
                        "srEventType": "add_married_in",
                        "srEventDate": "2003-06-15",
                        "srCompensated": False,
                        "srWithdraw": False,
                        "extEventType": "",
                        "extEventDate": "2024-11-02",
                        "extCompensated": True,
                        "extWithdraw": False,
                        "economicRelation": "1",
                        "hukouPlace": "泗阳县众兴镇某某村",
                        "residencePlace": "泗阳县众兴镇某某村三组",
                        "isCivilServant": False,
                        "isInstitutionStaff": None,
                        "remark": "测试",
                    },
                )],
                **base, editor_name="verify",
            )
            db.flush()
            saved = db.scalar(
                select(sheet_cls).where(
                    sheet_cls.batch_id == base["batch_id"],
                    sheet_cls.contractor_uid == base["contractor_uid"],
                    sheet_cls.member_uid == "verify-member-uid",
                )
            )
            check("C1 upsert 后行存在", saved is not None)
            if saved is not None:
                check("C2 现户口所在地落库", saved.hukou_place == "泗阳县众兴镇某某村", str(saved.hukou_place))
                check("C3 现居住地落库", saved.residence_place == "泗阳县众兴镇某某村三组", str(saved.residence_place))
                payload = survey_sheet_service.member_sheet_payload(saved)
                check("C4 payload 读回一致", payload["hukouPlace"] == "泗阳县众兴镇某某村" and payload["residencePlace"] == "泗阳县众兴镇某某村三组")
                check("C5 payload 含两新键（老前端兼容）", "hukouPlace" in payload and "residencePlace" in payload)
        finally:
            db.rollback()
        gone = db.scalar(
            select(sheet_cls).where(
                sheet_cls.batch_id == base["batch_id"],
                sheet_cls.contractor_uid == base["contractor_uid"],
                sheet_cls.member_uid == "verify-member-uid",
            )
        )
        check("C6 rollback 后零写入", gone is None)


# ── D. 打印模板渲染 ──────────────────────────────────────────────
def part_d() -> None:
    print("\nD. 打印模板渲染（合成上下文）")
    from jinja2 import Environment

    tpl_src = (ROOT / "backend" / "app" / "templates" / "member_change_sheet.html").read_text(encoding="utf-8")
    html = Environment().from_string(tpl_src).render(
        contractor={"name": "张三", "code": "321324100001020010", "groupName": "", "postcode": "",
                    "issuerCounty": "泗阳县", "issuerTown": "众兴镇", "issuerVillage": "某某村",
                    "issuerHamlet": "自然村", "issuerName": "", "issuerCode": "32132410000102"},
        rows=[{
            "memberName": "李四", "idNo": "321324198001010011", "phone": "", "relationText": "户主",
            "participatedSecondRound": False, "inRegister": True, "is1996Member": True,
            "srEventType": "", "srEventDate": "", "extEventType": "", "extEventDate": "",
            "changeTime": "", "inHousehold": True, "economicRelation": True,
            "hukouPlace": "泗阳县众兴镇某某村", "residencePlace": "泗阳县众兴镇某某村三组",
            "isFiscalSupported": False, "isCivilServant": False, "remark": "",
        }],
        noteStats={"rep1996": "", "rep2018": "张三", "pop1996": 1, "joinExt": 1, "addCount": 0,
                   "subCount": 0, "currentCount": 1, "registerCount": 1, "collectiveCount": 1,
                   "fiscalCount": 0, "civilCount": 0, "compensatedCount": 0, "withdrawCount": 0},
    )
    check("D1 模板渲染无异常", "承 包 农 户 家 庭 成 员 变 化 情 况" in html)
    check("D2 列31/32 值落格", "泗阳县众兴镇某某村三组" in html)
    check("D3 列7 直填点亮（统一 √ 符号）", html.count("√") >= 1)
    check("D4 列6 表头按原件（无「发证」字样）", "土地确权登记发证家庭成员" not in html and "土地确权登记家庭成员" in html)


def main() -> None:
    print("=== 家庭成员摸底表：列31/32 现户口所在地/现居住地 验收 ===")
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
