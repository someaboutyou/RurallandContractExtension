"""临时排查脚本：multi_scope_user 的「数据权限区域」勾选与库内真实记录是否一致。

只读，不改任何数据。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / "runtime" / ".state" / "runtime.env"
for line in env_path.read_text(encoding="utf-8-sig").splitlines():
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        continue
    key, value = text.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())

try:
    import psycopg
    def connect():
        return psycopg.connect(
            host=os.environ["DATABASE_HOST"],
            port=int(os.environ["DATABASE_PORT"]),
            dbname=os.environ["DATABASE_NAME"],
            user=os.environ["DATABASE_USER"],
            password=os.environ["DATABASE_PASSWORD"],
        )
except ImportError:  # pragma: no cover
    import psycopg2
    def connect():
        return psycopg2.connect(
            host=os.environ["DATABASE_HOST"],
            port=int(os.environ["DATABASE_PORT"]),
            dbname=os.environ["DATABASE_NAME"],
            user=os.environ["DATABASE_USER"],
            password=os.environ["DATABASE_PASSWORD"],
        )

out = []


def emit(title, rows, columns=None):
    out.append("=" * 70)
    out.append(title)
    out.append("-" * 70)
    if columns:
        out.append(" | ".join(str(c) for c in columns))
    for row in rows:
        out.append(" | ".join("" if v is None else str(v) for v in row))
    out.append(f"(rows={len(rows)})")
    out.append("")


with connect() as conn, conn.cursor() as cur:
    cur.execute(
        "SELECT id, username, real_name, region_id, tenant_code, role_id, status "
        "FROM users WHERE username = %s",
        ("multi_scope_user",),
    )
    users = cur.fetchall()
    emit("1) users 表里的 multi_scope_user", users,
         ["id", "username", "real_name", "region_id", "tenant_code", "role_id", "status"])

    user_ids = [row[0] for row in users]
    if not user_ids:
        print("\n".join(out))
        sys.exit(0)

    cur.execute(
        "SELECT id, user_id, tenant_code, region_code, level "
        "FROM user_region_permissions WHERE user_id = ANY(%s) ORDER BY region_code",
        (user_ids,),
    )
    perms = cur.fetchall()
    emit("2) user_region_permissions 真实记录", perms,
         ["id", "user_id", "tenant_code", "region_code", "level"])

    codes = [row[3] for row in perms]
    if codes:
        cur.execute(
            "SELECT id, code, name, full_name, level, parent_id, tenant_code "
            "FROM regions WHERE code = ANY(%s) ORDER BY code",
            (codes,),
        )
        emit("3) 这些 code 在 regions 表里对应的行", cur.fetchall(),
             ["id", "code", "name", "full_name", "level", "parent_id", "tenant_code"])

    # 站在每个已授权 code 的父节点上：看它是不是「全部子节点都已被选中」
    if codes:
        cur.execute(
            """
            WITH selected AS (SELECT unnest(%s::text[]) AS code)
            SELECT p.code AS parent_code,
                   p.full_name AS parent_name,
                   count(c.id) AS child_count,
                   count(s.code) AS selected_child_count,
                   bool_and(c.code LIKE p.code || '%%') AS all_prefix_ok
            FROM regions p
            JOIN regions c ON c.parent_id = p.id
            LEFT JOIN selected s ON s.code = c.code
            WHERE p.id IN (SELECT parent_id FROM regions WHERE code = ANY(%s::text[]))
            GROUP BY p.code, p.full_name
            ORDER BY p.code
            """,
            (codes, codes),
        )
        emit("4) 已授权节点各自的父节点：子节点是否已全选（塌缩前提）", cur.fetchall(),
             ["parent_code", "parent_name", "child_count", "selected_child_count", "all_prefix_ok"])

    # 青阳镇：全貌
    cur.execute(
        "SELECT id, code, name, full_name, level, parent_id, tenant_code "
        "FROM regions WHERE full_name LIKE %s ORDER BY code",
        ("%青阳镇%",),
    )
    rows = cur.fetchall()
    emit("5) regions 里所有全名含「青阳镇」的行", rows,
         ["id", "code", "name", "full_name", "level", "parent_id", "tenant_code"])

    qy_ids = [row[0] for row in rows]
    if qy_ids:
        cur.execute(
            "SELECT id, code, name, full_name, level, parent_id FROM regions "
            "WHERE parent_id = ANY(%s) ORDER BY code",
            (qy_ids,),
        )
        emit("6) 青阳镇的直接子节点（父级授权判定用）", cur.fetchall(),
             ["id", "code", "name", "full_name", "level", "parent_id"])

    # code 是否唯一（前端 el-tree 以 code 作 key）
    cur.execute(
        "SELECT code, count(*) AS n FROM regions GROUP BY code HAVING count(*) > 1 ORDER BY n DESC LIMIT 20"
    )
    emit("7) regions 表里 code 重复的行（>1 次）", cur.fetchall(), ["code", "n"])

    # 该用户 region_id 指向哪一行
    cur.execute(
        "SELECT r.id, r.code, r.full_name, r.level, r.tenant_code FROM regions r "
        "WHERE r.id = ANY(%s)",
        ([row[3] for row in users],),
    )
    emit("8) 用户所属区域（users.region_id 指向）", cur.fetchall(),
         ["id", "code", "full_name", "level", "tenant_code"])

print("\n".join(out))
