"""验收：登记（延包）申请书（集体 / 单户）打印与导出。

离线渲染 + 断言内容；配合 E2E（HTTP）验证接口。
用法：runtime/windows/python/python.exe scripts/_verify_registration_application.py [batch_id]
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
from app.services.contract_template_service import contract_template_service  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


db = SessionLocal()
try:
    batch_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    batch = db.get(SurveyBatch, batch_id) if batch_id else db.scalars(select(SurveyBatch).order_by(SurveyBatch.id.desc())).first()
    if batch is None:
        print("库里没有调查批次，无法做数据级验收")
        sys.exit(1)
    print(f"批次: id={batch.id} region={batch.region_name} code={getattr(batch, 'region_code', None)}")

    # ── 集体申请书 ────────────────────────────────────
    html = contract_template_service.render_collective_application(db, batch_id=batch.id)
    print("--- 集体申请书渲染片段 ---")
    print(html[:300].replace("\n", " "))
    check("集体申请书：含标题", "农村土地承包经营权证登记申请书" in html)
    check("集体申请书：含申请编号句式", "农地证请［" in html)
    check("集体申请书：含农户数", "个农户符合" in html)
    check("集体申请书：含土地面积", "涉及农村集体土地" in html)
    check("集体申请书：无未渲染 Jinja 变量", "{{" not in html and "{%" not in html)
    for var in ("county_name", "town_name", "village_name", "term_start", "family_number"):
        check(f"集体申请书：变量 {var} 已填充", f"{{{var}}}" not in html)

    # ── 单户申请书 ────────────────────────────────────
    uid = db.scalars(
        select(SurveyCbfBase.contractor_uid)
        .where(SurveyCbfBase.batch_id == batch.id, SurveyCbfBase.task_status != "deregistered")
        .limit(1)
    ).first()
    if uid is None:
        print("批次内无承包户，跳过单户验收")
    else:
        html2 = contract_template_service.render_household_application(db, batch_id=batch.id, contractor_uid=uid)
        check("单户申请书：含表标题", "第二轮土地承包到期后再延长三十年登记申请表" in html2)
        check("单户申请书：含四级意见栏", all(k in html2 for k in ("村民小组意见", "村民委员会意见", "乡（镇）人民政府意见", "县农业农村局意见")))
        check("单户申请书：含申请内容句式", "特申请第二轮土地承包到期后延长三十年登记" in html2)
        check("单户申请书：无未渲染 Jinja 变量", "{{" not in html2 and "{%" not in html2)
        for var in ("fbf_fzr", "cbfmc", "contract_code", "contract_term_start"):
            check(f"单户申请书：变量 {var} 已填充", f"{{{var}}}" not in html2)
        # docx 转写冒烟（html_docx 对合并单元格/样式的兼容性）——解包看 document.xml 内容
        import io  # noqa: E402
        import zipfile  # noqa: E402

        from app.services import html_docx  # noqa: E402

        def docx_text(payload: bytes) -> str:
            archive = zipfile.ZipFile(io.BytesIO(payload))
            return archive.read("word/document.xml").decode("utf-8")

        docx_bytes = html_docx.build_docx(html2)
        xml = docx_text(docx_bytes)
        check("单户申请书：可转写 docx 且含正文", docx_bytes[:2] == b"PK" and "登记申请表" in xml and "县农业农村局意见" in xml)
        docx_bytes2 = html_docx.build_docx(html)
        xml2 = docx_text(docx_bytes2)
        check("集体申请书：可转写 docx 且含正文", docx_bytes2[:2] == b"PK" and "登记申请书" in xml2 and "人民政府" in xml2)

    print()
    if failures:
        print(f"共 {len(failures)} 项未通过：{failures}")
        sys.exit(1)
    print("全部通过")
finally:
    db.close()
