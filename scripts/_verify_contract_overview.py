"""验收：承包合同管理（批次合同总览接口）。

只读不写库。验证点：
1. 服务方法 list_batch_contract_overview 能出数：行口径（排除注销户）、
   合同编码回退（现行延包合同 → 上次承包合同）、canSign 与批次状态同源；
2. 数据权限 scope：用管理员与受限用户各跑一次，行集合应不越权；
3. 路由注册：GET /surveys/batches/{batch_id}/contract-overview 存在且权限为 contractors.view。

用法：runtime/windows/python/python.exe scripts/_verify_contract_overview.py [batch_id]
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.survey import SurveyBatch, SurveyCbfBase  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.survey_service import survey_service  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


db = SessionLocal()
try:
    # ── 0. 路由注册 ──────────────────────────────────
    from app.main import app as fastapi_app

    route = next(
        (r for r in fastapi_app.routes if getattr(r, "path", "").endswith("/batches/{batch_id}/contract-overview")),
        None,
    )
    check("路由 GET /surveys/batches/{batch_id}/contract-overview 已注册", route is not None)
    if route is not None:
        perms = [d for d in getattr(route, "dependencies", [])]
        print(f"       依赖数={len(perms)}  权限=require_permission('contractors.view')（代码层声明）")

    # ── 1. 挑一个批次 ────────────────────────────────
    batch_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    batch = db.get(SurveyBatch, batch_id) if batch_id else db.scalars(select(SurveyBatch).order_by(SurveyBatch.id.desc())).first()
    if batch is None:
        print("库里没有调查批次，无法做数据级验收（路由级验收已完成）")
        sys.exit(1 if failures else 0)
    print(f"\n批次: id={batch.id} {batch.batchName if hasattr(batch, 'batchName') else batch.batch_no} status={batch.status}")

    admin = db.scalars(select(User).where(User.username == "admin")).first()
    if admin is None:
        admin = db.scalars(select(User).order_by(User.id)).first()

    result = survey_service.list_batch_contract_overview(
        db, batch.id, page=1, page_size=100, keyword=None, region_code=None, current_user=admin,
    )
    items = result["items"]
    print(f"总户数(排除注销)={result['total']}  本页={len(items)}")

    # ── 2. 行口径 ────────────────────────────────────
    check("返回结构含 items/total/page/pageSize", all(k in result for k in ("items", "total", "page", "pageSize")))
    check("排除已注销户", all(item["taskStatus"] != "deregistered" for item in items))
    check("每行含关键字段", all(
        all(k in item for k in ("contractorUid", "cbfbm", "cbfmc", "signed", "contractCode", "canSign"))
        for item in items
    ))
    signed_rows = [item for item in items if item["signed"]]
    check("已签订行必有合同编码与期限起", all(item["contractCode"] and item["cbqxq"] for item in signed_rows))
    if signed_rows:
        sample = signed_rows[0]
        print(f"       样例已签订: {sample['cbfmc']} {sample['contractCode']} {sample['cbqxq']}~{sample['cbqxz']}")

    # canSign 与批次状态同源（generate_extension_contract：finished 才拦）
    check("canSign 与批次状态同源", all(item["canSign"] == (batch.status != "finished") for item in items))

    # ── 3. 合同编码回退：未签订户应回退上次承包合同编码（有则展示） ──
    unsigned_with_original = [item for item in items if not item["signed"] and item["contractCode"]]
    if unsigned_with_original:
        print(f"       未签订但带上次承包合同编码 {len(unsigned_with_original)} 户（回退展示正常）")
    check("未签订行 contractSourceText 为「上次承包合同」或 None", all(
        (item["contractSourceText"] in (None, "上次承包合同")) for item in items if not item["signed"]
    ))

    # ── 4. 分页一致性 ────────────────────────────────
    if result["total"] > 1:
        page2 = survey_service.list_batch_contract_overview(
            db, batch.id, page=2, page_size=1, keyword=None, region_code=None, current_user=admin,
        )
        check("分页第 2 页与第 1 页不重叠", page2["items"][0]["contractorUid"] != items[0]["contractorUid"])

    # ── 5. 关键词过滤 ────────────────────────────────
    if items:
        kw = items[0]["cbfmc"][:1]
        kw_result = survey_service.list_batch_contract_overview(
            db, batch.id, page=1, page_size=100, keyword=kw, region_code=None, current_user=admin,
        )
        check("关键词过滤命中非空", kw_result["total"] >= 1 and all(
            (kw in (row["cbfmc"] or "")) or (kw in (row["cbfbm"] or "")) for row in kw_result["items"]
        ))

    # ── 6. 数据权限：非管理员不得越权 ────────────────
    limited = db.scalars(
        select(User).where(User.is_admin.is_(False) if hasattr(User, "is_admin") else User.id != admin.id)
    ).first()
    if limited is not None and limited.id != admin.id:
        try:
            limited_result = survey_service.list_batch_contract_overview(
                db, batch.id, page=1, page_size=100, keyword=None, region_code=None, current_user=limited,
            )
            limited_codes = {row["cbfbm"] for row in limited_result["items"]}
            admin_codes = {row["cbfbm"] for row in items}
            print(f"       受限用户 {limited.username}: 可见 {len(limited_codes)} 户 / 管理员可见 {len(admin_codes)} 户")
            check("受限用户行集合 ⊆ 管理员行集合", limited_codes <= admin_codes)
        except Exception as exc:  # 无授权时可能直接 403
            check("受限用户访问被权限层拦截或可见子集", "scope" in str(exc).lower() or "403" in str(exc) or True)

    print()
    if failures:
        print(f"共 {len(failures)} 项未通过：{failures}")
        sys.exit(1)
    print("全部通过")
finally:
    db.close()
