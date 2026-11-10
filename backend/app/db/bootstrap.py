import logging
import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.base import Base
from app.db.init_db import seed_initial_data
from app.db.migrations import upgrade_schema
from app.db.sequences import ensure_business_sequences
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)

#: 启动时 PostgreSQL 可能尚未完全就绪（刚启动 / 刚重启 / 清空数据后重建），
#: 单次连接失败就让 uvicorn 整个启动退出，控制中心表现为「后端启动失败」。
#: 这里做有限重试；正常启动时首次就成功，不增加可感知延迟。
BOOTSTRAP_MAX_ATTEMPTS = 10
BOOTSTRAP_RETRY_DELAY_SECONDS = 2.0


def create_database_schema() -> None:
    Base.metadata.create_all(bind=engine)
    upgrade_schema(engine)
    # 业务编号序列（batch_no / change_no / ...）：建在 schema 之后、seed 之前。
    # 幂等，且会把游标顶到已有编号之后，所以老库升级也不会和历史编号撞。
    ensure_business_sequences(engine)


def seed_database() -> None:
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()


def warn_if_no_platform_admin() -> None:
    """检查平台管理员是否存在。

    「清空数据」后如果 backend/.env 没配 REGION_SEED_COUNTIES，regions 为空，
    默认 admin 不会被创建；系统能启动但任何登录都失败（表现为「用户名或密码
    错误」，极易误判成密码问题）。这里显式打一条错误日志，便于直接定位。
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT 1 FROM users u JOIN roles r ON r.id = u.role_id "
                "WHERE r.code = 'platform_admin' AND u.status = 'active' LIMIT 1"
            )
        ).first()
    except Exception:  # 表结构异常时交给上面的 bootstrap 报错，这里不额外干扰
        return
    finally:
        db.close()
    if row is None:
        message = (
            "未找到可用的平台管理员账号。常见原因是清空数据后 regions 为空，"
            "默认账号未创建：请在 backend/.env 配置 REGION_SEED_COUNTIES"
            "（6 位行政区划码，如 321324）后重启后端。"
        )
        print(f"[bootstrap] 严重警告：{message}")
        logger.error(message)


def bootstrap_database(
    max_attempts: int = BOOTSTRAP_MAX_ATTEMPTS,
    retry_delay_seconds: float = BOOTSTRAP_RETRY_DELAY_SECONDS,
) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            create_database_schema()
            seed_database()
            warn_if_no_platform_admin()
            return
        except OperationalError as exc:
            if attempt >= max_attempts:
                raise
            logger.warning(
                "数据库尚未就绪（第 %s/%s 次）：%s；%.1f 秒后重试",
                attempt,
                max_attempts,
                exc,
                retry_delay_seconds,
            )
            time.sleep(retry_delay_seconds)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Database bootstrap utility")
    parser.add_argument("--schema", action="store_true", help="create/upgrade database schema only")
    parser.add_argument("--seed", action="store_true", help="seed framework data only")
    args = parser.parse_args()

    if args.schema:
        create_database_schema()
    elif args.seed:
        seed_database()
        warn_if_no_platform_admin()
    else:
        bootstrap_database()
