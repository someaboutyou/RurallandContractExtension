# -*- coding: utf-8 -*-
"""实测（零残留）：两个并发事务写同一个 dkbm 时，唯一约束到底怎么表现。

要证明三件事：
  A) 已提交的 dkbm 再插一次 —— 立即 unique_violation（不是静默通过）。
  B) 前一个事务**未提交**时，后一个插同一个 dkbm —— 会被**阻塞**，
     而不是"两边都以为没重复、双双写进去"。
  C) 前一个事务回滚后，后一个才能插进去。

全程用 tenant_code='__PROBE__' 的探测行，结束时 DELETE 干净并复核。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATABASE_PORT", "15432")
os.environ.setdefault("DATABASE_PASSWORD", "dK9venBRbBRewDFAWYHRGdCM")
os.environ.setdefault("SECRET_KEY", "probe-only")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

import psycopg  # noqa: E402

from app.core.config import settings  # noqa: E402

DSN = (
    f"host={settings.database_host} port={settings.database_port} "
    f"dbname={settings.database_name} user={settings.database_user} "
    f"password={settings.database_password}"
)

PROBE_TENANT = "__PROBE__"
PROBE_DKBM = "9999999999999900001"

INSERT_SQL = """
INSERT INTO survey_dk_result
    (tenant_code, region_code, parcel_uid, ysdm, dkbm, dkmc,
     dklb, dldj, tdyt, sfjbnt, scmj,
     survey_status, result_status, is_changed, change_type, initialized_at)
VALUES
    (%s, %s, %s, %s, %s, %s,
     %s, %s, %s, %s, %s,
     %s, %s, %s, %s, now())
"""


def clean(cur) -> None:
    cur.execute("DELETE FROM survey_dk_result WHERE tenant_code = %s", (PROBE_TENANT,))


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    params = (
        PROBE_TENANT, "99999999999999", "probe-uid-0001", "999999", PROBE_DKBM, "探针地块",
        "01", "01", "1", "1", 1.23,
        "surveyed", "added", True, "add_parcel",
    )

    # ---- 每节前都先清干净，避免上一节的探测行干扰下一节 ----
    def reset() -> None:
        with psycopg.connect(DSN, autocommit=True) as conn:
            clean(conn.cursor())

    reset()
    try:
        run_sections(params, reset)
    finally:
        reset()
        with psycopg.connect(DSN, autocommit=True) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT count(*) FROM survey_dk_result WHERE tenant_code = %s", (PROBE_TENANT,)
            )
            print(f"\n[收尾] 探测行残留 = {cur.fetchone()[0]}（应为 0）")


def run_sections(params, reset) -> None:
    section("A) 已提交的 dkbm 再插一次")
    with psycopg.connect(DSN) as conn_a:
        conn_a.execute(INSERT_SQL, params)
        conn_a.commit()
        print(f"  连接A: 插入 {PROBE_DKBM} 并 commit  -> 成功")
        try:
            with psycopg.connect(DSN) as conn_b:
                conn_b.execute("SET statement_timeout = '5s'")
                conn_b.execute(INSERT_SQL, params)
                conn_b.commit()
            print("  连接B: 插入同一 dkbm -> 竟然成功了！（说明约束没生效）")
        except psycopg.errors.UniqueViolation as exc:
            print(f"  连接B: 插入同一 dkbm -> UniqueViolation ✓（被数据库拦住）")
            print(f"         约束名: {getattr(exc.diag, 'constraint_name', None)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  连接B: 其他异常 {type(exc).__name__}: {exc}")

    section("B) 前一个事务【未提交】时，后一个插同一个 dkbm")
    reset()
    with psycopg.connect(DSN) as conn_a:
        conn_a.execute(INSERT_SQL, params)
        print(f"  连接A: 插入 {PROBE_DKBM} ，**故意不 commit**（模拟并发窗口）")
        try:
            with psycopg.connect(DSN) as conn_b:
                conn_b.execute("SET statement_timeout = '4s'")
                conn_b.execute(INSERT_SQL, params)
                conn_b.commit()
            print("  连接B: 插入成功 —— 说明 A 的未提交行对 B 不可见/未拦截 ✗")
        except psycopg.errors.UniqueViolation as exc:
            print("  连接B: UniqueViolation（A 已提交后才可能）")
            print(f"         约束名: {getattr(exc.diag, 'constraint_name', None)}")
        except psycopg.errors.QueryCanceled:
            print("  连接B: 被**阻塞**直到 statement_timeout ✓")
            print("         → 唯一索引在 A 未提交阶段就让 B 排队等待，")
            print("           不存在『两个事务同时认为不重复、双双写入』的窗口。")
        except Exception as exc:  # noqa: BLE001
            print(f"  连接B: 其他异常 {type(exc).__name__}: {exc}")
        conn_a.rollback()
        print("  连接A: rollback（模拟并发失败方放弃）")

    section("C) A 回滚后，B 应能插入")
    reset()
    with psycopg.connect(DSN) as conn_b:
        conn_b.execute(INSERT_SQL, params)
        conn_b.commit()
        print(f"  连接B: 插入 {PROBE_DKBM} -> 成功（A 已回滚，号可以用）")

    section("D) 复核：探测行是否真实存在，然后清理")
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT count(*) FROM survey_dk_result WHERE tenant_code = %s", (PROBE_TENANT,)
        )
        print(f"  清理前探测行数: {cur.fetchone()[0]}")
        clean(cur)
        cur.execute(
            "SELECT count(*) FROM survey_dk_result WHERE tenant_code = %s", (PROBE_TENANT,)
        )
        print(f"  清理后探测行数: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM survey_dk_result")
        print(f"  全表总行数: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
