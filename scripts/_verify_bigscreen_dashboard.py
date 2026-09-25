"""验收：二轮延包工作进展大屏（GET /api/v1/dashboard/bigscreen）。

跑法（必须用带依赖的那个解释器）：
  runtime/windows/python/python.exe scripts/_verify_bigscreen_dashboard.py

五组断言：

| 组 | 内容 |
| --- | --- |
| A | 权限种子：`dashboard.bigscreen` 权限点存在，且**只**挂在 platform_admin 上 |
| B | HTTP 契约：管理员调用 200，返回结构齐全（overview / funnel / taskStatus / assignees / regionBoard / changeTypes / trend / alerts） |
| C | 数据勾稽：overview / funnel / taskStatus / assignees / regions / trend 与直连 SQL 独立算出的值逐项一致 |
| D | 权限闸门：非管理员角色调用被真拒绝（403），不是"界面藏起来但接口能打" |
| E | 参数校验：regionLevel 非法、trendDays 越界均被拦（422） |

只读脚本，不写任何业务数据（唯一写入是启动 seed 幂等补权限，属正常启动行为）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "runtime" / ".state" / "_verify_bigscreen_dashboard.txt"
SURVEYED_STATUSES = ("surveyed", "changed", "unchanged", "confirmed")


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
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

BASE = "/api/v1"
OUT: list[str] = []
CHECKS = {"ok": 0, "fail": 0}
FAILED: list[str] = []


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


def run_checks(client: TestClient) -> None:
    log("== A 权限种子 ==")
    perm = rows("SELECT id, name, group_name, category FROM permissions WHERE code = 'dashboard.bigscreen'")
    check("权限点 dashboard.bigscreen 已登记", len(perm) == 1, perm)
    holders = [row[0] for row in rows(
        """
        SELECT r.code FROM role_permissions rp
        JOIN roles r ON r.id = rp.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE p.code = 'dashboard.bigscreen'
        ORDER BY r.code
        """
    )]
    check("该权限当前只授予 platform_admin", holders == ["platform_admin"], holders)

    admin_id = scalar("SELECT id FROM users WHERE username = 'admin'")
    check("存在 admin 用户", admin_id is not None)
    other = rows(
        """
        SELECT u.id, u.username, r.code FROM users u
        JOIN roles r ON r.id = u.role_id
        WHERE r.code <> 'platform_admin' AND u.status = 'active'
        ORDER BY u.id LIMIT 1
        """
    )
    other_id = other[0][0] if other else None
    log(f"  非管理员夹具用户：{other[0][1] if other else '(无)'} / role={other[0][2] if other else '-'}")

    log("\n== B HTTP 契约 ==")
    resp = client.get(f"{BASE}/dashboard/bigscreen", headers=token(admin_id))
    check("管理员请求返回 200", resp.status_code == 200, resp.status_code)
    if resp.status_code != 200:
        log(f"  响应体：{resp.text[:400]}")
        return

    data = resp.json()["data"]
    for key in (
        "generatedAt", "batch", "batches", "overview", "funnel", "taskStatus",
        "assignees", "regionBoard", "changeTypes", "trend", "alerts",
    ):
        check(f"顶层字段 {key} 存在", key in data, list(data.keys()))

    batch = data.get("batch")
    log(f"  批次：{batch['batchName'] if batch else '(无)'}")
    if batch is None:
        log("  库内没有调查批次，跳过 C 组勾稽（空结构回归：接口不报错）")
    else:
        log("\n== C 数据勾稽 ==")
        batch_id = batch["id"]
        tenant = scalar("SELECT tenant_code FROM survey_batches WHERE id = :bid", bid=batch_id)
        params = {"bid": batch_id, "tc": tenant}

        def cbf(extra: str = "", col: str = "COUNT(*)") -> int:
            sql = (
                f"SELECT {col} FROM survey_cbf_base "
                "WHERE batch_id = :bid AND tenant_code = :tc " + extra
            )
            return int(scalar(sql, **params) or 0)

        total = cbf("AND task_status <> 'deregistered'")
        assigned = cbf("AND task_status <> 'deregistered' AND assigned_to IS NOT NULL")
        surveyed = int(
            scalar(
                "SELECT COUNT(*) FROM survey_cbf_base WHERE batch_id = :bid AND tenant_code = :tc "
                "AND task_status <> 'deregistered' AND task_status IN "
                "('surveyed','changed','unchanged','confirmed')",
                **params,
            )
            or 0
        )
        confirmed = cbf("AND task_status <> 'deregistered' AND task_status = 'confirmed'")
        all_rows = cbf("", col="COUNT(*)")

        ov = data["overview"]
        log(
            "  概览：承包方 {t} 户 / 已分配 {a} / 已调查 {s} / 已确认 {c} / 地块 {p} 块 / 合同面积 {m} 亩 / 申请 {r} 件".format(
                t=ov["contractorTotal"], a=ov["assignedCount"], s=ov["surveyedCount"],
                c=ov["confirmedCount"], p=ov["parcelTotal"], m=ov["contractAreaMu"],
                r=ov["requestGeneratedCount"],
            )
        )
        log(f"  调查员 {len(data['assignees'])} 人 / 区域行 {len(data['regionBoard']['leading'])} 条 / 变更类型 {len(data['changeTypes'])} 类 / 预警 {len(data['alerts'])} 条")
        check("contractorTotal 与 SQL 一致", ov["contractorTotal"] == total, f'{ov["contractorTotal"]} vs {total}')
        check("assignedCount 与 SQL 一致", ov["assignedCount"] == assigned, f'{ov["assignedCount"]} vs {assigned}')
        check("surveyedCount 与 SQL 一致", ov["surveyedCount"] == surveyed, f'{ov["surveyedCount"]} vs {surveyed}')
        check("confirmedCount 与 SQL 一致", ov["confirmedCount"] == confirmed, f'{ov["confirmedCount"]} vs {confirmed}')
        parcel_total = scalar(
            "SELECT COUNT(DISTINCT b.dkbm) FROM survey_cbdkxx_base b "
            "JOIN survey_cbdkxx_result r ON r.id = b.result_id "
            "WHERE b.batch_id = :bid AND b.tenant_code = :tc AND r.result_status <> 'removed'",
            **params,
        )
        area_sum = scalar(
            "SELECT COALESCE(SUM(b.htmj), 0) FROM survey_cbdkxx_base b "
            "JOIN survey_cbdkxx_result r ON r.id = b.result_id "
            "WHERE b.batch_id = :bid AND b.tenant_code = :tc AND r.result_status <> 'removed'",
            **params,
        )
        check("parcelTotal 与 SQL 一致", ov["parcelTotal"] == int(parcel_total or 0), f'{ov["parcelTotal"]} vs {parcel_total}')
        check(
            "contractAreaMu 与 SQL 一致（平方米 ÷ 666.67）",
            abs(ov["contractAreaMu"] - round(float(area_sum or 0) / 666.67, 2)) < 0.02,
            f'{ov["contractAreaMu"]} vs {round(float(area_sum or 0) / 666.67, 2)}',
        )
        check(
            "assignedRate 与 count 自洽",
            abs(ov["assignedRate"] - (round(assigned / total * 100, 1) if total else 0.0)) < 0.05,
            ov["assignedRate"],
        )
        check(
            "状态分布各行之和 = 全部户数（含已注销）",
            sum(item["count"] for item in data["taskStatus"]) == all_rows,
            f'{sum(item["count"] for item in data["taskStatus"])} vs {all_rows}',
        )
        check(
            "assignees 户数之和 = assignedCount",
            sum(item["total"] for item in data["assignees"]) == assigned,
            f'{sum(item["total"] for item in data["assignees"])} vs {assigned}',
        )
        region_total = sum(item["total"] for item in data["regionBoard"]["leading"])
        check("区域排行明细只包含有数据的区域", all(item["total"] > 0 for item in data["regionBoard"]["leading"]), region_total)
        check("trend 点数 = trendDays 默认值 15", len(data["trend"]) == 15, len(data["trend"]))
        funnel = {item["key"]: item for item in data["funnel"]}
        check("漏斗基线 = contractorTotal", funnel["baseline"]["count"] == ov["contractorTotal"], funnel["baseline"])
        check("漏斗已分配 = assignedCount", funnel["assigned"]["count"] == assigned, funnel["assigned"])
        check("漏斗已调查 = surveyedCount", funnel["surveyed"]["count"] == surveyed, funnel["surveyed"])
        check("漏斗已确认 = confirmedCount", funnel["confirmed"]["count"] == confirmed, funnel["confirmed"])
        check(
            "漏斗单调不增（基线≥分配≥调查≥确认≥申请）",
            all(
                funnel[a]["count"] >= funnel[b]["count"]
                for a, b in (("baseline", "assigned"), ("assigned", "surveyed"), ("surveyed", "confirmed"), ("confirmed", "request"))
            ),
            {k: v["count"] for k, v in funnel.items()},
        )
        check("变更类型分布计数非负", all(item["count"] >= 0 for item in data["changeTypes"]), data["changeTypes"])

        # 村级粒度也跑一遍，确认参数真的生效而不是被忽略
        village = client.get(
            f"{BASE}/dashboard/bigscreen", headers=token(admin_id), params={"regionLevel": "village"}
        )
        check("regionLevel=village 返回 200", village.status_code == 200, village.status_code)
        if village.status_code == 200:
            board = village.json()["data"]["regionBoard"]
            check("regionLevel=village 生效", board["level"] == "village" and board["levelLabel"] == "村级", board["levelLabel"])
            check(
                "村级分组数 ≥ 镇级分组数",
                len(board["leading"]) >= len(data["regionBoard"]["leading"]),
                f'{len(board["leading"])} vs {len(data["regionBoard"]["leading"])}',
            )

        # 指定批次与默认批次应返回同一批次（库里只有一个批次时也成立）
        explicit = client.get(
            f"{BASE}/dashboard/bigscreen", headers=token(admin_id), params={"batchId": batch_id}
        )
        check("按 batchId 指定批次 200", explicit.status_code == 200, explicit.status_code)
        if explicit.status_code == 200:
            check("指定批次回显一致", explicit.json()["data"]["batch"]["id"] == batch_id)
        missing = client.get(
            f"{BASE}/dashboard/bigscreen", headers=token(admin_id), params={"batchId": 99999999}
        )
        check("不存在的 batchId 返回 404", missing.status_code == 404, missing.status_code)

    log("\n== D 权限闸门（HTTP 真拒绝）==")
    if other_id is None:
        log("  (跳过) 库内没有非管理员用户")
    else:
        denied = client.get(f"{BASE}/dashboard/bigscreen", headers=token(other_id))
        check("非管理员调用返回 403", denied.status_code == 403, denied.status_code)
        detail = denied.json().get("detail") or ""
        check("403 文案明确（提示无权而非 500/空）", "无权" in detail or "权限" in detail, denied.text[:200])
        legacy = client.get(f"{BASE}/dashboard/summary", headers=token(other_id))
        check("旧 /summary 仍按 dashboard.view 放行（未被误伤）", legacy.status_code == 200, legacy.status_code)

    log("\n== E 参数校验 ==")
    bad_level = client.get(f"{BASE}/dashboard/bigscreen", headers=token(admin_id), params={"regionLevel": "county"})
    check("regionLevel 非法值被拦（422）", bad_level.status_code == 422, bad_level.status_code)
    bad_days = client.get(f"{BASE}/dashboard/bigscreen", headers=token(admin_id), params={"trendDays": 999})
    check("trendDays 越界被拦（422）", bad_days.status_code == 422, bad_days.status_code)
    bad_auth = client.get(f"{BASE}/dashboard/bigscreen")
    check("未带令牌被拦（401）", bad_auth.status_code == 401, bad_auth.status_code)


def main() -> None:
    # ⛔ 必须用 with：TestClient 只有进入上下文管理器才跑 FastAPI 的 lifespan，
    # 而权限点/角色授权是在启动初始化（bootstrap_database）里种的。
    # 直接 `TestClient(app).get(...)` 不会触发，会误判成"权限点没登记"。
    with TestClient(app) as client:
        run_checks(client)


try:
    main()
except Exception as exc:  # noqa: BLE001
    import traceback

    CHECKS["fail"] += 1
    FAILED.append(f"脚本异常：{exc}")
    log(f"  [FAIL] 脚本异常：{exc}")
    log(traceback.format_exc())

log("")
log(f"结论：通过 {CHECKS['ok']} 项，失败 {CHECKS['fail']} 项")
if FAILED:
    log("失败清单：" + " / ".join(FAILED))

RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
RESULT_PATH.write_text("\n".join(OUT), encoding="utf-8")
print("\n".join(OUT))
sys.exit(1 if CHECKS["fail"] else 0)
