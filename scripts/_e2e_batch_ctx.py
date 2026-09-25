# -*- coding: utf-8 -*-
"""生成 /surveys 新建批次区域树的 E2E 上下文（供 e2e_batch_region.mjs 读取）。"""
import json
import os
import sys

ENV = r"E:\Work\RurallandContractExtension\runtime\.state\runtime.env"
for line in open(ENV, encoding="utf-8-sig"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, r"E:\Work\RurallandContractExtension\backend")

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402

url = (
    f"postgresql+psycopg://{os.environ['DATABASE_USER']}:{os.environ['DATABASE_PASSWORD']}"
    f"@{os.environ['DATABASE_HOST']}:{os.environ['DATABASE_PORT']}/{os.environ['DATABASE_NAME']}"
)
eng = create_engine(url)

with eng.connect() as c:
    # code, name, level, full_name, parent_id, id
    rows = {r[0]: r for r in c.execute(text("select code,name,level,full_name,parent_id,id from regions"))}
    by_id = {r[5]: r for r in rows.values()}

    def walk(code: str) -> list[str]:
        """从根到该区域的 full_name 链路。"""
        chain = []
        row = rows.get(code)
        while row is not None:
            chain.append(row[3])
            row = by_id.get(row[4])
        return list(reversed(chain))

    groups = sorted(
        (r for r in rows.values() if r[2] == "group" and r[0].startswith("321324100001")),
        key=lambda r: r[0],
    )
    batches = list(c.execute(text(
        "select batch_no, region_code, status, created_by, region_name from survey_batches "
        "where status='active' and survey_type='household_survey' order by id"
    )))
    perms = list(c.execute(text("select region_code from user_region_permissions where user_id=7 order by region_code")))

ctx = {
    "app": "http://127.0.0.1:8010",
    "adminToken": create_access_token("1"),
    "groupToken": create_access_token("7"),
    "villageCode": "321324100001",
    "villageFullName": rows["321324100001"][3],
    "ancestorChain": walk("321324100001"),
    "groups": [{"code": r[0], "name": r[1], "fullName": r[3]} for r in groups],
    "activeBatches": [
        {"batchNo": r[0], "regionCode": r[1], "createdBy": r[3], "regionName": r[4]} for r in batches
    ],
    "groupUserPermissionCodes": [r[0] for r in perms],
}

open(r"E:\Work\RurallandContractExtension\runtime\.state\_e2e_batch_ctx.json", "w", encoding="utf-8").write(
    json.dumps(ctx, ensure_ascii=False, indent=2)
)
print(json.dumps(ctx, ensure_ascii=False, indent=2)[:2000])
