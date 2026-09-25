"""离线核实：批次创建人对「未分配给自己的户」的录入写权判定链路。
只读，不落库（ensure_task_write_permission 只抛异常）。
"""
import os
import sys
from pathlib import Path

ROOT = Path(".").resolve()
for _line in (ROOT / "runtime/.state/runtime.env").read_text(encoding="utf-8-sig").splitlines():
    _t = _line.strip()
    if _t and not _t.startswith("#") and "=" in _t:
        _k, _v = _t.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal
from app.models.user import User
from app.services.survey import survey_service as svc

TARGET_UID = "db73a668-fdf9-5d4d-a6b2-07619c180553"  # 321324100001020012 陈福才（未分配）

db = SessionLocal()
try:
    batch = svc._ensure_batch(db, 41)
    print(f"批次41: region={batch.region_code} created_by={batch.created_by} status={batch.status}")
    print()

    for uid in (7, 22, 1):
        user = db.get(User, uid)
        if user is None:
            continue
        priv = svc.is_batch_privileged(batch, user)  # 分配 / 改派权（含创建人豁免）
        priv_w = svc.is_task_write_privileged(user)  # 录入写权（只认管理员）
        print(f"--- user_id={uid} {user.username}（角色 {user.role.name}, data_scope={user.role.data_scope}）---")
        print(f"    is_batch_privileged（**分配**权）      = {priv}"
              f"   [理由: {'data_scope=all' if user.role.data_scope == 'all' else ('批次创建人' if batch.created_by == uid else '无')}]")
        print(f"    is_task_write_privileged（**写**权）   = {priv_w}"
              f"   [只认 data_scope=all，创建人不再豁免]")
        print(f"    can_write_task(该未分配户)      = {svc.can_write_task(db, batch, TARGET_UID, user)}")
        result = svc._get_result(db, 41, TARGET_UID)
        try:
            svc.ensure_task_write_permission(db, batch, result, user)
            print("    ensure_task_write_permission   = 放行（保存接口不会 403）")
        except Exception as exc:  # noqa: BLE001
            detail = getattr(exc, "detail", str(exc))
            print(f"    ensure_task_write_permission   = 拒绝 {detail}")
        print()
finally:
    db.close()
