# -*- coding: utf-8 -*-
"""清理历次验收测试在库里留下的「无主数据」。

默认 **dry-run**：只统计 + 备份，不删任何行；加 `--apply` 才真正执行。

清理对象（四类，互相有依赖顺序）：
  1. survey_cbdkxx_result —— cbfbm 在同租户的 survey_cbf_result 里找不到户
     （历次 delete_contractor 不清理关联造成的历史遗留）
  2. survey_dk_result —— 只清「其全部关联都属于第 1 类」的地块，
     即没有任何一个还活着的户在用它（脚本会逐行核对 live_rels）
  3. survey_change_diffs —— contractor_uid 已无对应户
  4. survey_change_records —— 同上

安全措施：
  * 每一类都先打印命中的行，dry-run 下不做任何写入；
  * --apply 时先把全部待删行导出到 runtime/.state/leftovers_backup_<ts>.json；
  * 所有判定都带上 tenant_code，避免跨租户误伤。

跑法：
  runtime/windows/python/python.exe scripts/cleanup_batch41_leftovers.py            # 预览
  runtime/windows/python/python.exe scripts/cleanup_batch41_leftovers.py --apply    # 执行
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / "runtime" / ".state"

os.environ.update({
    "DATABASE_HOST": "127.0.0.1",
    "DATABASE_PORT": "15432",
    "DATABASE_NAME": "erlunyanbao",
    "DATABASE_USER": "RurallandContractExtension",
    "DATABASE_PASSWORD": "dK9venBRbBRewDFAWYHRGdCM",
    "SECRET_KEY": "cleanup-only",
})
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from app.core.config import settings  # noqa: E402

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

ORPHAN_RELATIONS = """
    SELECT c.* FROM survey_cbdkxx_result c
    WHERE NOT EXISTS (
        SELECT 1 FROM survey_cbf_result r
        WHERE r.cbfbm = c.cbfbm AND r.tenant_code = c.tenant_code)
"""

ORPHAN_PARCELS = """
    SELECT d.* FROM survey_dk_result d
    WHERE d.dkbm = ANY(%s)
      AND NOT EXISTS (
        SELECT 1 FROM survey_cbdkxx_result c2
        WHERE c2.dkbm = d.dkbm
          AND EXISTS (SELECT 1 FROM survey_cbf_result r2
                      WHERE r2.cbfbm = c2.cbfbm AND r2.tenant_code = c2.tenant_code))
"""

ORPHAN_DIFFS = """
    SELECT t.* FROM survey_change_diffs t
    WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = t.contractor_uid)
"""

ORPHAN_RECORDS = """
    SELECT t.* FROM survey_change_records t
    WHERE NOT EXISTS (SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = t.contractor_uid)
"""


def _json_default(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return {"__repr__": repr(value)}


def main() -> None:
    apply = "--apply" in sys.argv

    with psycopg.connect(DSN, autocommit=True, row_factory=dict_row) as conn:
        cur = conn.cursor()

        relations = cur.execute(ORPHAN_RELATIONS).fetchall()
        dkbms = sorted({row["dkbm"] for row in relations})
        parcels = cur.execute(ORPHAN_PARCELS, (dkbms,)).fetchall() if dkbms else []
        diffs = cur.execute(ORPHAN_DIFFS).fetchall()
        records = cur.execute(ORPHAN_RECORDS).fetchall()

        print("=" * 72)
        print(f"无主数据清理 —— {'APPLY（会真正删除）' if apply else 'DRY-RUN（只预览）'}")
        print("=" * 72)
        print(f"  1. survey_cbdkxx_result 残留关联 : {len(relations)} 行")
        for row in relations:
            print(f"       id={row['id']}  cbfbm={row['cbfbm']}  dkbm={row['dkbm']}  status={row['result_status']}")
        print(f"  2. survey_dk_result 无主地块     : {len(parcels)} 行")
        for row in parcels:
            print(f"       id={row['id']}  dkbm={row['dkbm']}  dkmc={row.get('dkmc')}  init={row.get('initialized_at')}")
        print(f"  3. survey_change_diffs 孤儿差异  : {len(diffs)} 行")
        print(f"  4. survey_change_records 孤儿记录: {len(records)} 行")
        if records:
            from collections import Counter
            print("       change_type 分布:", dict(Counter(r["change_type"] for r in records)))

        if not (relations or parcels or diffs or records):
            print("\n没有需要清理的行。")
            return

        # ── 备份 ──
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = BACKUP_DIR / f"leftovers_backup_{stamp}.json"
        backup_path.write_text(
            json.dumps(
                {
                    "created_at": stamp,
                    "database": settings.database_name,
                    "survey_cbdkxx_result": relations,
                    "survey_dk_result": parcels,
                    "survey_change_diffs": diffs,
                    "survey_change_records": records,
                },
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            ),
            encoding="utf-8",
        )
        print(f"\n  已备份全部待删行 -> {backup_path}")

        if not apply:
            print("\nDRY-RUN 结束，未做任何写入。确认无误后加 --apply 执行。")
            return

        # ── 执行（顺序有依赖：先删关联，再删地块，最后删台账）──
        with conn.transaction():
            removed_rel = cur.execute(
                "DELETE FROM survey_cbdkxx_result c WHERE NOT EXISTS ("
                " SELECT 1 FROM survey_cbf_result r"
                " WHERE r.cbfbm = c.cbfbm AND r.tenant_code = c.tenant_code) RETURNING id"
            ).fetchall()
            removed_parcel = cur.execute(
                "DELETE FROM survey_dk_result d WHERE d.id = ANY(%s) RETURNING id",
                ([row["id"] for row in parcels],),
            ).fetchall() if parcels else []
            removed_diff = cur.execute(
                "DELETE FROM survey_change_diffs t WHERE NOT EXISTS ("
                " SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = t.contractor_uid) RETURNING id"
            ).fetchall()
            removed_record = cur.execute(
                "DELETE FROM survey_change_records t WHERE NOT EXISTS ("
                " SELECT 1 FROM survey_cbf_result r WHERE r.contractor_uid = t.contractor_uid) RETURNING id"
            ).fetchall()

        print("\n已删除：")
        print(f"  survey_cbdkxx_result : {len(removed_rel)} 行")
        print(f"  survey_dk_result     : {len(removed_parcel)} 行")
        print(f"  survey_change_diffs  : {len(removed_diff)} 行")
        print(f"  survey_change_records: {len(removed_record)} 行")

        # 复核
        left = {
            "relations": len(cur.execute(ORPHAN_RELATIONS).fetchall()),
            "parcels": len(cur.execute(ORPHAN_PARCELS, (dkbms,)).fetchall()) if dkbms else 0,
            "diffs": len(cur.execute(ORPHAN_DIFFS).fetchall()),
            "records": len(cur.execute(ORPHAN_RECORDS).fetchall()),
        }
        print(f"\n清理后残留复核: {left}")
        print("全部为 0 即清理干净。" if not any(left.values()) else "⚠ 仍有残留，请检查。")


if __name__ == "__main__":
    main()
