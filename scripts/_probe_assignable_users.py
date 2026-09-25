"""探针：定位「分配调查任务」弹窗里调查员下拉为空的原因。

只读。分别以 admin / multi_scope_user 身份调 /surveys/batches/{id}/assignable-users，
并打印候选名单在库里被哪些条件滤掉。
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for line in (ROOT / "runtime/.state/runtime.env").read_text(encoding="utf-8-sig").splitlines():
    t = line.strip()
    if t and not t.startswith("#") and "=" in t:
        k, v = t.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(ROOT / "backend"))

import psycopg  # noqa: E402

from app.core.security import create_access_token  # noqa: E402

BASE = "http://127.0.0.1:8000"


def call(token: str, path: str):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


conn = psycopg.connect(
    host=os.environ["DATABASE_HOST"],
    port=int(os.environ["DATABASE_PORT"]),
    dbname=os.environ["DATABASE_NAME"],
    user=os.environ["DATABASE_USER"],
    password=os.environ["DATABASE_PASSWORD"],
)
cur = conn.cursor()

print("=" * 78)
print("1) 批次表：region_code / tenant_code / created_by")
print("=" * 78)
cur.execute(
    "SELECT b.id, b.batch_no, b.region_code, b.tenant_code, b.created_by, b.status,"
    " (SELECT username FROM users WHERE id=b.created_by) AS creator"
    " FROM survey_batches b ORDER BY b.id"
)
for r in cur.fetchall():
    print("   ", r)

print()
print("=" * 78)
print("2) 全库 active 用户：tenant_code / region / role / data_scope")
print("=" * 78)
cur.execute(
    """
    SELECT u.id, u.username, u.real_name, u.status, u.tenant_code,
           r.code AS region_code, r.full_name, ro.name AS role_name, ro.data_scope
    FROM users u
    JOIN regions r ON r.id = u.region_id
    JOIN roles ro ON ro.id = u.role_id
    ORDER BY u.id
    """
)
for r in cur.fetchall():
    print("   ", r)

print()
print("=" * 78)
print("3) 用户的数据权限区域（user_region_permissions）")
print("=" * 78)
cur.execute(
    "SELECT user_id, region_code, level FROM user_region_permissions ORDER BY user_id, region_code"
)
for r in cur.fetchall():
    print("   ", r)

print()
print("=" * 78)
print("4) 实调接口 /surveys/batches/{id}/assignable-users")
print("=" * 78)
for uid, name in [("1", "admin"), ("6", "multi_scope_user")]:
    tk = create_access_token(uid)
    st, body = call(tk, "/api/v1/surveys/batches")
    batch_ids = []
    if isinstance(body, dict) and isinstance(body.get("data"), dict):
        batch_ids = [(i.get("id"), i.get("batchNo"), i.get("regionCode")) for i in body["data"].get("items", [])]
    print(f"\n[{name}] 可见批次 = {batch_ids}")
    for bid, bno, rc in batch_ids:
        st, body = call(tk, f"/api/v1/surveys/batches/{bid}/assignable-users")
        if isinstance(body, dict):
            items = body.get("data")
            print(f"   batch={bid} {bno} region={rc} -> {st} 候选={len(items) if items else 0}")
            if items:
                for it in items:
                    print("       ", json.dumps(it, ensure_ascii=False))
        else:
            print(f"   batch={bid} {bno} region={rc} -> {st} {body}")

print()
print("=" * 78)
print("5) /auth/me（前端拿它渲染）")
print("=" * 78)
tk = create_access_token("6")
st, body = call(tk, "/api/v1/auth/me")
print("   ", json.dumps(body, ensure_ascii=False)[:900])

conn.close()
