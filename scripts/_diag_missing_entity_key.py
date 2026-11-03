# -*- coding: utf-8 -*-
"""诊断 data_import_row 里 'Missing entity key' 失败行的原始字段。"""
import json
import os

os.environ["DATABASE_HOST"] = "127.0.0.1"
os.environ["DATABASE_PORT"] = "15432"
os.environ["DATABASE_NAME"] = "erlunyanbao"
os.environ["DATABASE_USER"] = "RurallandContractExtension"
os.environ["DATABASE_PASSWORD"] = "yt2rp9hGgtCVnPCZrCKCYF34"

import psycopg  # noqa: E402

conn = psycopg.connect(
    host="127.0.0.1", port=15432, dbname="erlunyanbao",
    user="RurallandContractExtension", password="yt2rp9hGgtCVnPCZrCKCYF34",
)
cur = conn.cursor()

cur.execute(
    """
    SELECT id, import_batch_id, row_no, entity_key, error_message, raw_data
    FROM data_import_row
    WHERE entity_type = 'cbf_jtcy' AND error_message = 'Missing entity key'
    ORDER BY id
    LIMIT 20
    """
)
rows = cur.fetchall()
print(f"total shown: {len(rows)}")
for r in rows:
    rid, batch_id, row_no, ekey, err, raw = r
    print("=" * 60)
    print(f"row.id={rid} batch={batch_id} row_no={row_no} entity_key={ekey}")
    if raw:
        d = raw if isinstance(raw, dict) else json.loads(raw)
        keys = {k: v for k, v in d.items() if v not in (None, "")}
        print("non-empty fields:", json.dumps(keys, ensure_ascii=False, default=str)[:800])
        print("cbfbm=", repr(d.get("cbfbm") or d.get("CBFBM")), "cyzjhm=", repr(d.get("cyzjhm") or d.get("CYZJHM")))
        print("all field names:", sorted(d.keys())[:60])

# 顺带统计该批次 cbf_jtcy 失败行数
cur.execute(
    """
    SELECT import_batch_id, count(*) FROM data_import_row
    WHERE entity_type='cbf_jtcy' AND status='failed'
    GROUP BY import_batch_id ORDER BY 1 DESC LIMIT 5
    """
)
print("-" * 60)
for bid, cnt in cur.fetchall():
    print(f"batch={bid} failed cbf_jtcy rows={cnt}")
conn.close()
