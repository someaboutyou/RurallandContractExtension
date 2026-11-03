# -*- coding: utf-8 -*-
"""离线验收：成员摸底「在户状态机」——必须有进才有出，出了还可以再进。

2026-10-15 用户口径：
  - 事件可以为空；
  - 期初（1996）在户 ⇒ 本期只能"出"；期初不在户 ⇒ 本期只能"进"；
  - 二轮期"出"了 ⇒ 延包期还可以再"进"（回迁）；
  - 已补地 / 抽回或放弃涉地不涉成员进出，不参与判定。

验收项：
  A. 后端纯函数（sheet.py::_sheet_presence_* / validate_member_sheet_flow）
  B. 前后端同源静态：事件码集合、弹窗过滤、保存预检、后端闸门接线
  C. 端到端（真库事务内，flush 后 rollback 零写入）：
     违规 sheet → HTTPException 400；合法 sheet → 落行成功
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
from app.services.survey.sheet import (  # noqa: E402
    _sheet_presence_p1_start,
    _sheet_presence_p2_start,
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


# ── A. 后端纯函数 ────────────────────────────────────────────────
def part_a() -> None:
    print("\nA. 状态机纯函数")
    # 期初状态
    check("A1 列7=是 → 期初在户", _sheet_presence_p1_start({"isSecondRoundMember": True}) == "in")
    check("A2 列7=否且无事件 → 期初不在户", _sheet_presence_p1_start({"isSecondRoundMember": False}) == "out")
    check("A3 列7=未填 → 不可判定", _sheet_presence_p1_start({"isSecondRoundMember": None}) is None)
    s = {"isSecondRoundMember": False, "srEventType": "add_move_in"}
    check("A4 列7=否+二轮期进 → 期初仍不在户", _sheet_presence_p1_start(s) == "out")
    check("A5 同上 → 2018 期初在户", _sheet_presence_p2_start(s) == "in")
    s2 = {"isSecondRoundMember": True, "srEventType": "sub_married_out"}
    check("A6 列7=是+二轮期出 → 2018 期初不在户（出了可以再进）", _sheet_presence_p2_start(s2) == "out")

    def problems(sheet: dict) -> list[str]:
        return validate_member_sheet_flow([("u1", sheet)], {"u1": "张三"})

    check("A7 规则①：1996 不在户+二轮期迁出 → 拦", len(problems({"isSecondRoundMember": False, "srEventType": "sub_move_out"})) == 1)
    check("A8 规则②：1996 在户+二轮期婚入 → 拦", len(problems({"isSecondRoundMember": True, "srEventType": "add_married_in"})) == 1)
    check("A9 规则③：一直在户+延包期婚入 → 拦", len(problems({"isSecondRoundMember": True, "extEventType": "add_married_in"})) == 1)
    check("A10 规则④：二轮期迁出+延包期去世 → 拦", len(problems({"isSecondRoundMember": True, "srEventType": "sub_move_out", "extEventType": "sub_death"})) == 1)
    check("A11 出了再进：二轮期迁出+延包期迁入 → 放行", problems({"isSecondRoundMember": True, "srEventType": "sub_move_out", "extEventType": "add_move_in"}) == [])
    check("A12 全空 → 放行", problems({"isSecondRoundMember": None}) == [])
    check("A13 只填列7=是、无事件 → 放行", problems({"isSecondRoundMember": True}) == [])
    check("A14 已补地（复选框）不参与判定：在户+延包期已补地 → 放行",
          problems({"isSecondRoundMember": True, "extCompensated": True}) == [])
    check("A15 抽回（复选框）不参与判定：在户+二轮期抽回 → 放行",
          problems({"isSecondRoundMember": True, "srWithdraw": True}) == [])
    check("A20 已补地与减少事件正交：二轮期迁出+二轮期已补地 → 放行",
          problems({"isSecondRoundMember": True, "srEventType": "sub_move_out", "srCompensated": True}) == [])
    check("A18 回归：列7=否+二轮期迁入（最常见合法场景）→ 放行",
          problems({"isSecondRoundMember": False, "srEventType": "add_move_in"}) == [])
    check("A19 回归：列7=否+二轮期迁入 → 2018 期初在户", _sheet_presence_p2_start({"isSecondRoundMember": False, "srEventType": "add_move_in"}) == "in")
    # 事件时间边界（2026-10-15 用户口径）
    check("A21 二轮期事件时间 2019-01-01 → 拦",
          any("不能晚于" in p for p in problems({"isSecondRoundMember": False, "srEventType": "add_move_in", "srEventDate": "2019-01-01"})))
    check("A22 二轮期事件时间 2018-12-31（含边界）→ 放行",
          problems({"isSecondRoundMember": False, "srEventType": "add_move_in", "srEventDate": "2018-12-31"}) == [])
    check("A23 延包期事件时间 2018-12-31 → 拦",
          any("不能早于" in p for p in problems({"isSecondRoundMember": True, "extEventType": "sub_death", "extEventDate": "2018-12-31"})))
    check("A24 延包期事件时间 2019-01-01（含边界）→ 放行",
          problems({"isSecondRoundMember": True, "extEventType": "sub_death", "extEventDate": "2019-01-01"}) == [])
    check("A16 文案点名成员名", "张三" in problems({"isSecondRoundMember": True, "srEventType": "add_birth"})[0])
    multi = validate_member_sheet_flow(
        [("u1", {"isSecondRoundMember": True, "srEventType": "add_birth"}),
         ("u2", {"isSecondRoundMember": False, "srEventType": "sub_death"})],
        {"u1": "甲", "u2": "乙"},
    )
    check("A17 多成员多违规逐条点名", len(multi) == 2 and any("甲" in p for p in multi) and any("乙" in p for p in multi))


# ── B. 前后端同源静态 ────────────────────────────────────────────
def part_b() -> None:
    print("\nB. 前后端同源静态")
    sheet_src = (ROOT / "backend" / "app" / "services" / "survey" / "sheet.py").read_text(encoding="utf-8-sig")
    fe_src = (ROOT / "frontend" / "src" / "config" / "surveySheets.js").read_text(encoding="utf-8")
    for code in ("add_birth", "add_married_in", "add_move_in", "add_other",
                 "sub_death", "sub_married_out", "sub_move_out", "sub_other"):
        in_be = f'"{code}"' in sheet_src
        in_fe = f'"{code}"' in fe_src
        check(f"B 事件码 {code} 前后端同源", in_be and in_fe)
    check("B 后端闸门接线（upsert 内调用 validate_member_sheet_flow）",
          "problems = validate_member_sheet_flow(entries, name_map)" in sheet_src
          and "HTTPException(status_code=400" in sheet_src)
    panel_src = (ROOT / "frontend" / "src" / "components" / "survey" / "ContractorMemberPanel.vue").read_text(encoding="utf-8")
    check("B 弹窗两期下拉按状态过滤", "srEventOptions" in fe_src and "srOpts" in panel_src and "extOpts" in panel_src)
    check("B 弹窗矛盾自动清空（reconcileSheetEvents）", "reconcileSheetEvents" in panel_src)
    dialog_src = (ROOT / "frontend" / "src" / "components" / "survey" / "view" / "ContractorResultDialog.vue").read_text(encoding="utf-8")
    check("B 保存预检接线（handleSaveResult 调 validateMemberSheetFlow）", "validateMemberSheetFlow" in dialog_src)
    panel_src2 = panel_src
    check("B 弹窗日期选择器禁用越界日期（disabled-date 两期）",
          ":disabled-date=\"disableSrDate\"" in panel_src2 and ":disabled-date=\"disableExtDate\"" in panel_src2
          and "disableSrDate" in fe_src + panel_src2)


# ── C. 端到端（事务内 rollback 零写入） ──────────────────────────
def part_c(engine) -> None:
    print("\nC. 端到端（flush 后 rollback）")
    sheet_cls = SurveyCbfMemberChangeSheet
    with Session(engine) as db:
        row = db.scalar(select(sheet_cls).order_by(sheet_cls.id.asc()))
        if row is None:
            base = dict(tenant_code="verify", batch_id=0, contractor_uid="verify-uid",
                        cbfbm="verify", region_code="")
            check("C0 库内无摸底行，改用临时构造", True)
        else:
            base = dict(tenant_code=row.tenant_code, batch_id=row.batch_id,
                        contractor_uid=row.contractor_uid, cbfbm=row.cbfbm,
                        region_code=row.region_code or "")
            check("C0 取真实摸底行做夹具", True, f"cbfbm={row.cbfbm}")
        bad_sheet = {"isSecondRoundMember": False, "srEventType": "sub_move_out"}  # 没进就出
        good_sheet = {"isSecondRoundMember": True, "srEventType": "sub_move_out",
                      "extEventType": "add_move_in"}  # 出了再进
        raised = None
        try:
            survey_sheet_service.upsert_member_sheets(
                db, member_entries=[("verify-flow-uid", bad_sheet)],
                **base, editor_name="verify",
            )
            db.flush()
        except Exception as exc:  # noqa: BLE001
            raised = exc
        finally:
            db.rollback()
        check("C1 违规（没进就出）→ 400 拦截", raised is not None and getattr(raised, "status_code", None) == 400,
              str(raised)[:80] if raised else "未抛异常")
        check("C2 文案点名（必须有进才有出）", raised is not None and "必须有进才有出" in str(getattr(raised, "detail", "")))

        raised2 = None
        try:
            with Session(engine) as db2:
                survey_sheet_service.upsert_member_sheets(
                    db2, member_entries=[("verify-flow-uid", good_sheet)],
                    **base, editor_name="verify",
                )
                db2.flush()
                saved = db2.scalar(
                    select(sheet_cls).where(
                        sheet_cls.batch_id == base["batch_id"],
                        sheet_cls.contractor_uid == base["contractor_uid"],
                        sheet_cls.member_uid == "verify-flow-uid",
                    )
                )
                check("C3 合法（出了再进）→ 落行成功", saved is not None and saved.ext_event_type == "add_move_in")
        except Exception as exc:  # noqa: BLE001
            raised2 = exc
        check("C4 合法路径无异常", raised2 is None, str(raised2)[:80] if raised2 else "")
        with Session(engine) as db3:
            gone = db3.scalar(
                select(sheet_cls).where(sheet_cls.member_uid == "verify-flow-uid")
            )
        check("C5 rollback 后零写入", gone is None)


def main() -> None:
    print("=== 成员摸底在户状态机（进/出/回迁）验收 ===")
    part_a()
    part_b()
    engine = create_engine(SYNC_URL)
    part_c(engine)
    print(f"\n结果：PASS {len(PASS)} / FAIL {len(FAIL)}")
    if FAIL:
        print("失败项：" + "；".join(FAIL))
        sys.exit(1)


if __name__ == "__main__":
    main()
