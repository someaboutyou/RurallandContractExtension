"""验收：业务编号（batch_no / change_no / ...）改用 PostgreSQL 序列。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_business_sequence.py

要证明的问题（用户"测试中发现的问题"）：
  旧实现 ``max(id)+1`` 在"删掉最大 id 的行"之后号段会回退，下一个新建**拿到用过的编号**
  （实测：建批次→删→再建，连续三次都是 ``SUR202609230042``）；并发创建还会撞号。

六组断言：

| 组 | 内容 |
| --- | --- |
| A | 静态：程序初始化链路调用了建序列；三份旧 ``_next_no`` 都已委托；前缀登记齐全 |
| B | 序列已建、``ensure`` 幂等（重复调用不改小游标）、游标 ≥ 库里已有编号 |
| C | 前进/不回退语义（用探针序列验，不动生产序列） |
| D | 5 个前缀都能出号，格式合规且互不重复 |
| E | **回归主断言**：HTTP 真入口连续"建批次→删→再建"3 轮，编号各不相同且递增 |
| F | 并发 8 线程 × 20 号，160 个号零重复（证明 ``nextval`` 原子） |

会真实创建临时批次（挑最小的空闲区域），每轮验完立刻删干净，结束断言残留 0，可重复运行。
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_business_sequence.txt"
BATCH_NAME = "__序列验收批次__"
PROBE_SUFFIX = "__verify"
DROP_TABLES = (
    "survey_cbf_jtcy_base",
    "survey_cbdkxx_base",
    "survey_dk_base",
    "survey_fbf_base",
    "survey_change_diffs",
    "survey_change_records",
    "survey_cbf_base",
)


def load_env() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in (ROOT / "runtime" / ".state" / "runtime.env").read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


for _key, _value in load_env().items():
    os.environ.setdefault(_key, _value)
os.environ.setdefault("SECRET_KEY", "verify-only")

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.security import create_access_token  # noqa: E402
from app.db.sequences import (  # noqa: E402
    BUSINESS_SEQUENCES,
    BusinessSequence,
    _advance_to_existing,
    _existing_floor,
    ensure_business_sequences,
    next_no,
    next_serial,
)
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

BASE = "/api/v1"
OUT: list[str] = []
CHECKS = {"ok": 0, "fail": 0}
FAILED: list[str] = []
TEMP_BATCH_IDS: list[int] = []


class _ProbeSequence(BusinessSequence):
    """同表同列，但用带后缀的独立序列名——验"前进/不回退"时不动生产序列。"""

    @property
    def name(self) -> str:
        return f"{self.table}_{self.column}_seq{PROBE_SUFFIX}"


def log(*parts) -> None:
    OUT.append(" ".join(str(part) for part in parts))


def check(label: str, condition: bool, detail: object = "") -> None:
    if condition:
        CHECKS["ok"] += 1
        log(f"  [OK]   {label}")
    else:
        CHECKS["fail"] += 1
        FAILED.append(label)
        log(f"  [FAIL] {label} | {detail}")


def token(user_id) -> dict:
    return {"Authorization": f"Bearer {create_access_token(str(user_id))}"}


def rows(sql: str, **params):
    with engine.connect() as conn:
        return [tuple(row) for row in conn.execute(text(sql), params).all()]


def scalar(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def show(title: str, resp, limit: int = 200) -> None:
    log(f"--- {title} -> {resp.status_code}")
    log("   ", json.dumps(resp.json(), ensure_ascii=False, default=str)[:limit])


def drop_batch(batch_id: int) -> None:
    with engine.begin() as conn:
        for table in DROP_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE batch_id = :bid"), {"bid": batch_id})
        conn.execute(text("DELETE FROM survey_batches WHERE id = :bid"), {"bid": batch_id})


def residue() -> int:
    return scalar("SELECT count(*) FROM survey_batches WHERE batch_name = :n", n=BATCH_NAME)


def sequence_state(name: str) -> tuple[int, bool] | None:
    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT last_value, is_called FROM {name}")).first()
    return (int(row[0]), bool(row[1])) if row else None


def consumed_floor(name: str) -> int:
    """"已占用"的位置：is_called=False 表示刚建出来还没取过号。"""
    state = sequence_state(name)
    if state is None:
        return -1
    last_value, is_called = state
    return last_value if is_called else last_value - 1


def drop_probe_sequences() -> None:
    with engine.begin() as conn:
        for spec in BUSINESS_SEQUENCES:
            conn.exec_driver_sql(f"DROP SEQUENCE IF EXISTS {spec.table}_{spec.column}_seq{PROBE_SUFFIX}")


client = TestClient(app)

try:
    db = SessionLocal()
    admin = db.get(User, 1)
    log(f"   管理员 = #{admin.id} {admin.real_name}")

    log("")
    log("========== A. 静态核查：初始化建序列 + 旧实现已全部委托 ==========")
    bootstrap_src = (ROOT / "backend" / "app" / "db" / "bootstrap.py").read_text(encoding="utf-8-sig", errors="replace")
    check(
        "程序初始化 create_database_schema() 里调用了 ensure_business_sequences（用户要求的初始化加序列）",
        "ensure_business_sequences(engine)" in bootstrap_src,
        bootstrap_src[:400],
    )
    check(
        "建序列排在 upgrade_schema 之后（表结构补齐后再建）",
        bootstrap_src.index("upgrade_schema(engine)") < bootstrap_src.index("ensure_business_sequences(engine)"),
    )
    legacy_files = (
        ("app/services/survey/base.py", "survey/base.py"),
        ("app/services/contractor_service.py", "contractor_service.py"),
        ("app/services/data_import/helpers.py", "data_import/helpers.py"),
    )
    for rel, label in legacy_files:
        src = (ROOT / "backend" / rel).read_text(encoding="utf-8-sig", errors="replace")
        check(f"{label} 不再用 max(id)+1 拼编号", "func.max(id_column)" not in src)
        check(f"{label} 已委托到 app.db.sequences", "generate_business_no(db, prefix" in src, src[-600:])

    callers = set()
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        if path.name.endswith(".bak"):
            continue
        text_src = path.read_text(encoding="utf-8-sig", errors="replace")
        callers.update(re.findall(r'_next_no\(\s*db\s*,\s*"([A-Z]+)"', text_src))
        callers.update(re.findall(r'\bnext_no\(\s*db\s*,\s*"([A-Z]+)"', text_src))
    registered = {spec.prefix for spec in BUSINESS_SEQUENCES}
    log(f"   代码里用到的前缀 = {sorted(callers)}；已登记序列的前缀 = {sorted(registered)}")
    check("代码里用到的每个编号前缀都已登记序列", callers <= registered, f"缺 {sorted(callers - registered)}")
    check(
        f"序列覆盖 5 类编号（{sorted(registered)}）",
        registered == {"SUR", "CHG", "RST", "AUT", "IMP"},
        registered,
    )

    log("")
    log("========== B. 初始化建序列 / 幂等 / 游标不落后 ==========")
    # 先跑一遍初始化里那一步（正在跑的 8000 还是旧进程，没执行过新 bootstrap，
    # 所以这里等价于"部署新版后第一次启动"的效果）。
    created = ensure_business_sequences()
    log(f"   ensure_business_sequences() -> {created}")
    check("初始化返回了 5 个序列名", len(created) == 5, created)
    present = set(row[0] for row in rows("SELECT sequence_name FROM information_schema.sequences"))
    for spec in BUSINESS_SEQUENCES:
        check(f"初始化后序列 {spec.name} 已建在数据库里", spec.name in present)

    # 再跑两遍，验幂等（每次启动都会跑，不能把游标改小 / 不能报错）。
    before = {spec.prefix: sequence_state(spec.name) for spec in BUSINESS_SEQUENCES}
    ensure_business_sequences()
    ensure_business_sequences()
    after = {spec.prefix: sequence_state(spec.name) for spec in BUSINESS_SEQUENCES}
    no_rewind = all(consumed_floor(spec.name) >= before[spec.prefix][0] - 1 for spec in BUSINESS_SEQUENCES)
    check("重复调用 ensure_business_sequences() 不会把游标改小（幂等）", no_rewind, f"{before} -> {after}")
    check("重复调用后游标状态未变（已建好就是纯 no-op）", before == after, f"{before} -> {after}")

    with engine.connect() as conn:
        for spec in BUSINESS_SEQUENCES:
            floor = _existing_floor(conn, spec)
            consumed = consumed_floor(spec.name)
            db_max_id = conn.execute(text(f"SELECT coalesce(max(id),0) FROM {spec.table}")).scalar()
            log(f"   {spec.prefix}: 库里 max(id)={db_max_id} 已有编号下界={floor} 序列已占用={consumed}")
            check(
                f"{spec.prefix} 序列游标 ≥ 库里已有编号（升级后不会和历史撞号）",
                consumed >= floor,
                f"consumed={consumed} floor={floor}",
            )

    log("")
    log("========== C. 前进 / 不回退语义（探针序列，不碰生产序列） ==========")
    drop_probe_sequences()
    probe = _ProbeSequence("SUR", "survey_batches", "batch_no")
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE SEQUENCE IF NOT EXISTS {probe.name}")
        st = conn.execute(text(f"SELECT last_value, is_called FROM {probe.name}")).first()
        check("探针序列建出来是 last_value=1 / is_called=false", int(st[0]) == 1 and not bool(st[1]), tuple(st))
        floor = _existing_floor(conn, probe)
        _advance_to_existing(conn, probe)
        advanced = conn.execute(text(f"SELECT nextval('{probe.name}')")).scalar()
    log(f"   库里已有编号下界 = {floor}；ensure 之后 nextval = {advanced}")
    check("ensure 把游标顶到了已有编号之后（nextval > floor）", int(advanced) > floor, f"{advanced} vs {floor}")

    with engine.begin() as conn:
        conn.exec_driver_sql(f"SELECT setval('{probe.name}', 1, false)")
        _advance_to_existing(conn, probe)
        refwd = conn.execute(text(f"SELECT nextval('{probe.name}')")).scalar()
    check("游标被人为调小后，ensure 会重新顶上去（前进）", int(refwd) > floor, f"{refwd} vs {floor}")

    with engine.begin() as conn:
        conn.exec_driver_sql(f"SELECT setval('{probe.name}', 999999, true)")
        _advance_to_existing(conn, probe)
        kept = conn.execute(text(f"SELECT nextval('{probe.name}')")).scalar()
    check("游标已在很前面时，ensure 不回退（保持 1000000）", int(kept) == 1000000, kept)
    drop_probe_sequences()
    check(
        "探针序列已删除（不留验收残留）",
        probe.name not in set(row[0] for row in rows("SELECT sequence_name FROM information_schema.sequences")),
    )

    log("")
    log("========== D. 5 个前缀出号：格式合规、互不重复 ==========")
    generated: dict[str, str] = {}
    pattern = re.compile(r"^(?P<prefix>[A-Z]+)(?P<day>\d{8})(?P<serial>\d{4,})$")
    for spec in BUSINESS_SEQUENCES:
        value = next_no(db, spec.prefix)
        generated[spec.prefix] = value
        match = pattern.match(value)
        check(
            f"{spec.prefix} 出号 {value} 格式合规（{spec.prefix}+8 位日期+4 位以上流水）",
            bool(match) and match.group("prefix") == spec.prefix,
            value,
        )
    check("5 个前缀出的号互不相同", len(set(generated.values())) == len(generated), generated)

    log("")
    log("========== E. 回归主断言：HTTP 真入口「建批次 → 删 → 再建」 ==========")
    existing = rows("SELECT id, batch_no FROM survey_batches ORDER BY id")
    log(f"   运行前库里批次 = {existing}")
    existing_nos = {row[1] for row in existing}
    existing_serials = [
        int(re.match(r"^[A-Z]{3}(\d{8})(\d+)$", row[1]).group(2))
        for row in existing
        if re.match(r"^[A-Z]{3}(\d{8})(\d+)$", row[1] or "")
    ]

    free_region = rows(
        """
        SELECT r.group_region_code, r.group_region_name, count(*) AS n
        FROM survey_cbf_result r
        WHERE r.group_region_code IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM survey_batches b
            WHERE b.status = 'active' AND b.region_code LIKE r.group_region_code || '%'
          )
        GROUP BY r.group_region_code, r.group_region_name
        HAVING count(*) BETWEEN 1 AND 200
        ORDER BY n
        LIMIT 1
        """
    )
    check("存在可用于验收的空闲区域", bool(free_region), free_region)
    if not free_region:
        raise RuntimeError("找不到空闲区域，无法做建批次回归")
    code, name, n_households = free_region[0]
    log(f"   选中区域 = {code} {name}（{n_households} 户）")

    baseline = residue()
    log(f"   运行前同名残留批次 = {baseline}")

    seen_nos: list[str] = []
    for round_no in (1, 2, 3):
        resp = client.post(
            f"{BASE}/surveys/batches",
            json={
                "batchName": BATCH_NAME,
                "regionCode": code,
                "regionName": name,
                "assigneeIds": [admin.id],
            },
            headers=token(admin.id),
        )
        batch_id = resp.json().get("data", {}).get("id") if resp.status_code == 200 else None
        show(f"第 {round_no} 轮 POST 新建批次", resp)
        check(f"第 {round_no} 轮创建成功", resp.status_code == 200 and batch_id is not None, resp.text[:300])
        if batch_id is None:
            break
        TEMP_BATCH_IDS.append(batch_id)
        batch_no = scalar("SELECT batch_no FROM survey_batches WHERE id = :b", b=batch_id)
        seen_nos.append(batch_no)
        log(f"   第 {round_no} 轮 batch_no = {batch_no}（批次 #{batch_id}，随后删除以复现「删行回退」）")
        drop_batch(batch_id)
        TEMP_BATCH_IDS.remove(batch_id)
        check(
            f"第 {round_no} 轮删干净（max(id) 已回落）",
            scalar("SELECT count(*) FROM survey_batches WHERE id = :b", b=batch_id) == 0,
        )

    log(f"   三轮编号 = {seen_nos}")
    check(
        "★ 三轮 batch_no 各不相同（旧实现这里三次全是同一个号）",
        len(seen_nos) == 3 and len(set(seen_nos)) == 3,
        seen_nos,
    )
    serials = []
    for value in seen_nos:
        match = re.match(r"^[A-Z]{3}\d{8}(\d+)$", value or "")
        if match:
            serials.append(int(match.group(1)))
    check("三轮流水号严格递增", len(serials) == 3 and serials == sorted(serials) and len(set(serials)) == 3, serials)
    check("新编号不与库里现有批次重复", not (set(seen_nos) & existing_nos), f"{seen_nos} ∩ {existing_nos}")
    check(
        "新编号流水号整体大于历史最大流水号（不回退到已用号段）",
        bool(serials) and bool(existing_serials) and min(serials) > max(existing_serials),
        f"new={serials} existing_max={max(existing_serials) if existing_serials else None}",
    )
    check("验收批次残留 = 0", residue() == baseline, f"residue={residue()} baseline={baseline}")

    log("")
    log("========== F. 并发出号：8 线程 × 20 号，零重复 ==========")
    lock = threading.Lock()
    results: list[int] = []
    errors: list[str] = []

    def worker() -> None:
        session = SessionLocal()
        try:
            local = [next_serial(session, "SUR") for _ in range(20)]
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(repr(exc))
            return
        finally:
            session.close()
        with lock:
            results.extend(local)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    log(f"   取到 {len(results)} 个号，去重后 {len(set(results))} 个；异常 {errors[:3]}")
    check("并发取号没有异常", not errors, errors[:3])
    check("并发取号 160 个全部唯一", len(results) == 160 and len(set(results)) == 160, f"{len(results)}/{len(set(results))}")

    db.close()

except Exception as exc:  # noqa: BLE001
    import traceback

    CHECKS["fail"] += 1
    FAILED.append(f"脚本异常：{exc!r}")
    OUT.append("")
    OUT.append("!!! 脚本异常，堆栈如下 !!!")
    OUT.append(traceback.format_exc())
finally:
    try:
        with engine.connect() as conn:
            for row in conn.execute(text("SELECT id FROM survey_batches WHERE batch_name = :n"), {"n": BATCH_NAME}).all():
                if row[0] not in TEMP_BATCH_IDS:
                    TEMP_BATCH_IDS.append(row[0])
        for _bid in TEMP_BATCH_IDS:
            drop_batch(_bid)
        drop_probe_sequences()
        OUT.append("")
        OUT.append("=== cleanup ===")
        OUT.append("removed batches = " + str(TEMP_BATCH_IDS))
        OUT.append("残留验收批次 = " + str(residue()))
        OUT.append(
            "探针序列残留 = "
            + str(
                sorted(
                    row[0]
                    for row in rows("SELECT sequence_name FROM information_schema.sequences")
                    if row[0].endswith(PROBE_SUFFIX)
                )
            )
        )
    except Exception as exc:  # noqa: BLE001
        OUT.append(f"CLEANUP FAILED: {exc}")

OUT.append("")
OUT.append(f"=== 通过 {CHECKS['ok']} 项，失败 {CHECKS['fail']} 项 ===")
if FAILED:
    OUT.append("失败项：")
    OUT.extend(f"  - {item}" for item in FAILED)

RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
sys.exit(1 if CHECKS["fail"] else 0)
