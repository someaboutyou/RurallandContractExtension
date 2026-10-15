import csv
import io
import logging
import os
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_export import DataExport
from app.models.survey import SurveyCbfJtcyResult, SurveyCbfResult
from app.schemas.data_export import DataExportRead, serialize_export
from app.schemas.pagination import PageResponse
from app.services import nyt2539_export_service
from app.services.data_access_service import data_access_service
from app.services.export_progress import (
    STALE_HEARTBEAT_SECONDS,
    ExportProgressReporter,
    pid_alive,
)

logger = logging.getLogger(__name__)

# 导出产物落地目录：backend/storage/data_exports/<export_id>/<file>.zip
_STORAGE_ROOT = Path(__file__).resolve().parents[2] / "storage" / "data_exports"

# 承包方类型 / 证件类型 / 调查状态 / 结果状态 的中文标签（仅做展示，不臆造业务含义）
_CBF_LX_LABEL = {"1": "农户", "2": "其他"}
_ZJ_LX_LABEL = {"1": "身份证"}
_SURVEY_STATUS_LABEL = {
    "not_surveyed": "未调查",
    "surveyed": "已调查",
    "changed": "已变更",
    "unchanged": "未变更",
    "confirmed": "已确认",
    "skipped": "已跳过",
}
_RESULT_STATUS_LABEL = {"normal": "正常", "added": "新增", "cancelled": "注销"}

# ⚠️ 列式查询 + 流式写 CSV：县级可达十几万户，绝不能 db.scalars() 把
# 十几万个 ORM 实体拽进内存，也不能用 in_(十几万个编码) 撞 Postgres
# 32767 参数上限——成员表必须走「区域子查询」在库内关联。
_CONTRACTOR_COLS = [
    SurveyCbfResult.cbfbm,
    SurveyCbfResult.cbflx,
    SurveyCbfResult.cbfmc,
    SurveyCbfResult.cbfzjlx,
    SurveyCbfResult.cbfzjhm,
    SurveyCbfResult.cbfdz,
    SurveyCbfResult.yzbm,
    SurveyCbfResult.lxdh,
    SurveyCbfResult.cbfcysl,
    SurveyCbfResult.group_region_code,
    SurveyCbfResult.group_region_name,
    SurveyCbfResult.survey_status,
    SurveyCbfResult.result_status,
    SurveyCbfResult.is_changed,
    SurveyCbfResult.change_type,
    SurveyCbfResult.change_reason,
    SurveyCbfResult.created_at,
]
_CONTRACTOR_HEADER = [
    "承包方编码", "承包方类型", "承包方名称", "证件类型", "证件号码", "承包方住址",
    "邮政编码", "联系电话", "家庭成员数", "组区域代码", "组区域名称",
    "调查状态", "结果状态", "是否变更", "变更类型", "变更原因", "创建时间",
]
_MEMBER_COLS = [
    SurveyCbfJtcyResult.cbfbm,
    SurveyCbfJtcyResult.cyxm,
    SurveyCbfJtcyResult.cyzjlx,
    SurveyCbfJtcyResult.cyzjhm,
    SurveyCbfJtcyResult.cyxb,
    SurveyCbfJtcyResult.yhzgx,
    SurveyCbfJtcyResult.sfgyr,
    SurveyCbfJtcyResult.phone,
    SurveyCbfJtcyResult.is_household_head,
    SurveyCbfJtcyResult.is_deceased,
]
_MEMBER_HEADER = [
    "承包方编码", "成员姓名", "证件类型", "证件号码", "性别",
    "与户主关系", "是否共有人", "联系电话", "是否户主", "是否已故",
]


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _contractor_csv_row(row) -> list[str]:
    return [
        _cell(row[0]),
        _CBF_LX_LABEL.get(row[1], row[1]),
        _cell(row[2]),
        _ZJ_LX_LABEL.get(row[3], row[3]),
        _cell(row[4]),
        _cell(row[5]),
        _cell(row[6]),
        _cell(row[7]),
        _cell(row[8]),
        _cell(row[9]),
        _cell(row[10]),
        _SURVEY_STATUS_LABEL.get(row[11], row[11]),
        _RESULT_STATUS_LABEL.get(row[12], row[12]),
        _cell(row[13]),
        _cell(row[14]),
        _cell(row[15]),
        _cell(row[16]),
    ]


def _member_csv_row(row) -> list[str]:
    return [
        _cell(row[0]),
        _cell(row[1]),
        _ZJ_LX_LABEL.get(row[2], row[2]),
        _cell(row[3]),
        _cell(row[4]),
        _cell(row[5]),
        _cell(row[6]),
        _cell(row[7]),
        _cell(row[8]),
        _cell(row[9]),
    ]


def _stream_csv(zf: ZipFile, arcname: str, header: list[str], row_iter, on_progress=None) -> int:
    """把行迭代器流式写进 ZIP 内的一个 CSV（UTF-8 BOM），返回行数。

    on_progress(count_so_far)：每写 2000 行与写完时回调一次，用于汇报进度。
    """
    count = 0
    with zf.open(arcname, "w") as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            writer = csv.writer(text)
            writer.writerow(header)
            for row in row_iter:
                writer.writerow(row)
                count += 1
                if on_progress and count % 2000 == 0:
                    on_progress(count)
    if on_progress:
        on_progress(count)
    return count


class DataExportService:
    def create_export(self, db: Session, payload: dict, current_user) -> DataExportRead:
        # 先把历史遗留的假死 processing 记录清成 failed（进程已不在 / 心跳超时）
        self.sweep_stale_processing(db)

        region_code = (payload.get("regionCode") or "").strip()
        if not region_code:
            raise ValueError("区域代码不能为空")

        export_type = payload.get("exportType") or "contractor_roster"
        if export_type != "contractor_roster" and export_type not in nyt2539_export_service.SUPPORTED_EXPORT_TYPES:
            raise ValueError(f"不支持的导出格式：{export_type}")

        # 只读区域筛选值校验：容许「比授权更粗」的区域码（详见 data_access_service 注释）
        data_access_service.ensure_region_filter_in_scope(
            current_user, region_code, detail="当前区域不在可导出范围内"
        )

        export_no = f"EXP{datetime.now():%Y%m%d%H%M%S}{random.randint(100, 999)}"
        export = DataExport(
            export_no=export_no,
            region_code=region_code,
            region_name=payload.get("regionName"),
            region_level=payload.get("regionLevel"),
            export_type=export_type,
            status="processing",
            progress=1,
            progress_message="排队生成…",
            worker_pid=os.getpid(),  # 供 stale 清扫判活：进程没了 ⇒ 记录置 failed
            operator_id=getattr(current_user, "id", None),
            operator_name=getattr(current_user, "display_name", None)
            or getattr(current_user, "username", None),
        )
        # ⛔ 先落库再生成：生成过程可能几十秒（县级十万级），若生成失败时记录
        # 还没 commit，rollback 会让整条记录消失，界面只剩一句 500。
        db.add(export)
        db.commit()
        db.refresh(export)

        reporter = ExportProgressReporter(export.id)
        try:
            if export_type == "contractor_roster":
                file_path, file_name, record_count, file_size = self._build_export_zip(
                    db, export, region_code, current_user, reporter
                )
            else:
                file_path, file_name, record_count, file_size = nyt2539_export_service.build_standard_export(
                    db, export, region_code, current_user, export_type, reporter=reporter
                )
            export.status = "success"
            export.progress = 100
            export.progress_message = "完成"
            export.file_path = file_path
            export.file_name = file_name
            export.file_size = file_size
            export.record_count = record_count
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("数据导出生成失败 export_no=%s region=%s", export_no, region_code)
            export = db.get(DataExport, export.id) or export
            export.status = "failed"
            export.error_message = str(exc)[:500]
            db.commit()
            return DataExportRead(**serialize_export(export))

        db.commit()
        db.refresh(export)
        return DataExportRead(**serialize_export(export))

    @staticmethod
    def sweep_stale_processing(db: Session) -> int:
        """把「生成中」但进程已死 / 心跳超时的记录清成 failed，返回清理条数。

        判据（满足其一即判死）：
        - worker_pid 与当前进程不同且该 PID 已不存在（服务重启 / 生成线程崩溃）；
        - updated_at 距今超过 STALE_HEARTBEAT_SECONDS（兜底：旧版本记录无 PID、
          或 PID 被操作系统复用导致判活误报）。
        """
        rows = db.scalars(select(DataExport).where(DataExport.status == "processing")).all()
        if not rows:
            return 0
        now = datetime.now(timezone.utc)
        swept = 0
        for row in rows:
            reason = None
            if row.worker_pid:
                if row.worker_pid != os.getpid() and not pid_alive(row.worker_pid):
                    reason = f"导出进程(PID {row.worker_pid})已不存在（服务重启或异常终止），已置为失败"
            if reason is None and row.updated_at is not None:
                updated = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=timezone.utc)
                if (now - updated).total_seconds() > STALE_HEARTBEAT_SECONDS:
                    reason = "生成超过 30 分钟无进度心跳，判定为失败"
            if reason:
                row.status = "failed"
                row.progress_message = None
                row.error_message = reason
                swept += 1
                logger.warning("清扫假死导出记录 id=%s export_no=%s：%s", row.id, row.export_no, reason)
        if swept:
            db.commit()
        return swept

    def _region_contractor_filters(self, region_code: str, current_user) -> list:
        filters = [SurveyCbfResult.region_code.like(f"{region_code}%")]
        tf = data_access_service.build_tenant_filter(SurveyCbfResult, current_user)
        if tf is not None:
            filters.append(tf)
        filters.extend(
            data_access_service.build_code_scope_filters(SurveyCbfResult.cbfbm, current_user)
        )
        return filters

    def _build_export_zip(
        self, db: Session, export: DataExport, region_code: str, current_user, reporter=None
    ) -> tuple[str, str, int, int]:
        contractor_filters = self._region_contractor_filters(region_code, current_user)
        # 成员表靠「区域内承包方编码」子查询在库内关联——参数只传区域码一个
        member_filters = [
            SurveyCbfJtcyResult.cbfbm.in_(select(SurveyCbfResult.cbfbm).where(*contractor_filters))
        ]
        mtf = data_access_service.build_tenant_filter(SurveyCbfJtcyResult, current_user)
        if mtf is not None:
            member_filters.append(mtf)

        if reporter:
            reporter.report(3, "统计待导出数据…", force=True)
        contractor_total = db.scalar(
            select(func.count()).select_from(SurveyCbfResult).where(*contractor_filters)
        ) or 0
        member_total = db.scalar(
            select(func.count()).select_from(SurveyCbfJtcyResult).where(*member_filters)
        ) or 0

        target_dir = _STORAGE_ROOT / str(export.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = (export.region_name or region_code or "region").replace("/", "_").replace("\\", "_")
        file_name = f"数据导出_{safe_name}_{export.export_no}.zip"
        zip_path = target_dir / file_name

        contractor_count = 0
        member_count = 0
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
            contractor_stmt = (
                select(*_CONTRACTOR_COLS)
                .where(*contractor_filters)
                .execution_options(yield_per=2000)  # 流式取行，不攒 ORM 实体
            )
            contractor_count = _stream_csv(
                zf, "承包方清册.csv", _CONTRACTOR_HEADER,
                (_contractor_csv_row(row) for row in db.execute(contractor_stmt)),
                on_progress=(
                    lambda n: reporter.report(
                        5 + int(50 * n / max(contractor_total, 1)), f"写承包方清册 {n}/{contractor_total}"
                    )
                    if reporter
                    else None
                ),
            )

            member_stmt = (
                select(*_MEMBER_COLS)
                .where(*member_filters)
                .execution_options(yield_per=2000)
            )
            member_count = _stream_csv(
                zf, "承包方家庭成员.csv", _MEMBER_HEADER,
                (_member_csv_row(row) for row in db.execute(member_stmt)),
                on_progress=(
                    lambda n: reporter.report(
                        60 + int(30 * n / max(member_total, 1)), f"写家庭成员 {n}/{member_total}"
                    )
                    if reporter
                    else None
                ),
            )

        if reporter:
            reporter.report(95, "打包压缩完成", force=True)
        file_size = zip_path.stat().st_size
        # 存相对 storage/ 的路径，下载时再拼绝对路径
        rel_path = f"data_exports/{export.id}/{file_name}"
        return rel_path, file_name, contractor_count, file_size

    def list_exports(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        current_user=None,
    ) -> PageResponse[DataExportRead]:
        # 列表入口顺带清扫假死记录：进程没了的 processing 立刻变 failed
        self.sweep_stale_processing(db)

        filters = []
        tf = data_access_service.build_tenant_filter(DataExport, current_user)
        if tf is not None:
            filters.append(tf)
        if keyword:
            like = f"%{keyword.strip()}%"
            filters.append(
                (DataExport.region_name.like(like))
                | (DataExport.region_code.like(like))
                | (DataExport.export_no.like(like))
            )

        stmt = select(DataExport)
        if filters:
            stmt = stmt.where(*filters)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        items = (
            db.scalars(
                stmt.order_by(DataExport.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            ).all()
        )
        return PageResponse[DataExportRead](
            items=[DataExportRead(**serialize_export(item)) for item in items],
            total=total,
            page=page,
            pageSize=page_size,
        )

    def _tenant_check(self, db: Session, export_id: int, current_user) -> None:
        """数据权限校验：与 delete_export 同口径，越权时抛 PermissionError。"""
        tf = data_access_service.build_tenant_filter(DataExport, current_user)
        if tf is not None and not db.scalar(select(DataExport).where(DataExport.id == export_id, tf)):
            raise PermissionError("无权操作该导出记录")

    def clear_export(self, db: Session, export_id: int, current_user) -> DataExport:
        """清除导出：删除产物文件与 data_exports/<id>/ 目录，记录保留并置为历史。

        与 delete_export 的区别：不删库行——导出编号 / 区域 / 记录数 / 操作人
        留作台账可追溯，只是服务器上不再保留产物（is_historical=True 后不可再下载）。
        """
        export = db.get(DataExport, export_id)
        if export is None:
            raise KeyError("导出记录不存在")
        self._tenant_check(db, export_id, current_user)

        cleared_paths: list[str] = []
        # 1) 以 id 命名的产物目录（所有导出类型的产物都落在 data_exports/<id>/ 下）
        target_dir = _STORAGE_ROOT / str(export_id)
        # ⛔ 防御：只允许删纯数字目录名，且必须位于 data_exports 根之下
        if target_dir.parent == _STORAGE_ROOT and target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
            cleared_paths.append(str(target_dir))
        # 2) file_path 指向的单个文件（兜底：目录已删或路径在目录外）
        if export.file_path:
            abs_path = (_STORAGE_ROOT.parent / export.file_path).resolve()
            if abs_path.exists() and _STORAGE_ROOT.parent.resolve() in abs_path.parents:
                try:
                    abs_path.unlink()
                    cleared_paths.append(str(abs_path))
                except OSError:
                    logger.warning("清除导出产物失败 id=%s path=%s", export_id, abs_path)

        export.is_historical = True
        export.file_path = None  # 产物已删，置空防止误下载；file_name 保留作台账
        db.commit()
        db.refresh(export)
        logger.info(
            "导出记录已清除 id=%s export_no=%s 删除路径=%s",
            export_id, export.export_no, cleared_paths or "无（产物本就不存在）",
        )
        return export

    def delete_export(self, db: Session, export_id: int, current_user) -> None:
        export = db.get(DataExport, export_id)
        if export is None:
            raise KeyError("导出记录不存在")
        self._tenant_check(db, export_id, current_user)
        # 删除产物文件
        if export.file_path:
            abs_path = _STORAGE_ROOT.parent / export.file_path
            try:
                if abs_path.exists():
                    abs_path.unlink()
            except OSError:
                logger.warning("删除导出产物失败 %s", abs_path)
        db.delete(export)
        db.commit()


data_export_service = DataExportService()
