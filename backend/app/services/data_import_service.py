import csv
import hashlib
import io
import json
import logging
import tempfile
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, inspect as sa_inspect, or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import Date as SADate, DateTime as SADateTime, Integer as SAInteger, Numeric as SANumeric

from app.db.session import SessionLocal, set_current_user
from app.models.data_import import DataImportBatch, DataImportFile, DataImportOperation, DataImportRow
from app.models.fbf import Fbf
from app.models.region import Region
from app.models.survey import (
    SurveyBatch,
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyContractorTask,
    SurveyDkBase,
    SurveyDkResult,
    SurveyFbfBase,
    SurveyFbfResult,
)
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.data_import_progress import data_import_progress
from app.services.geoserver_service import geoserver_service


logger = logging.getLogger(__name__)


class ImportCanceled(Exception):
    pass


class DataImportService:
    chunk_size = 5000
    progress_update_interval = 100
    cbf_field_map = {
        "cbfbm": ["cbfbm", "承包方代码", "code"],
        "region_code": ["region_code", "鍖哄煙浠ｇ爜", "regionCode"],
        "region_name": ["region_name", "鍖哄煙鍚嶇О", "regionName"],
        "cbflx": ["cbflx", "承包方类型", "typeCode"],
        "cbfmc": ["cbfmc", "承包方名称", "承包方(代表)名称", "name"],
        "cbfzjlx": ["cbfzjlx", "证件类型", "承包方(代表)证件类型", "idType"],
        "cbfzjhm": ["cbfzjhm", "证件号码", "承包方(代表)证件号码", "idNo"],
        "cbfdz": ["cbfdz", "鎵垮寘鏂瑰湴鍧€", "address"],
        "yzbm": ["yzbm", "閭斂缂栫爜", "postcode"],
        "lxdh": ["lxdh", "鑱旂郴鐢佃瘽", "mobile"],
        "cbfcysl": ["cbfcysl", "承包方成员数量", "家庭成员数", "memberCount"],
        "cbfdcrq": ["cbfdcrq", "承包方调查日期", "surveyDate"],
        "cbfdcy": ["cbfdcy", "鎵垮寘鏂硅皟鏌ュ憳", "surveyorName"],
        "cbfdcjs": ["cbfdcjs", "承包方调查记事", "surveyNote"],
        "gsjs": ["gsjs", "鍏ず璁颁簨", "publicNoticeNote"],
        "gsjsr": ["gsjsr", "公示记事人", "publicNoticeRecorder"],
        "gsshrq": ["gsshrq", "鍏ず瀹℃牳鏃ユ湡", "publicNoticeReviewDate"],
        "gsshr": ["gsshr", "公示审核人", "publicNoticeReviewer"],
        "group_region_code": ["group_region_code", "鎵€灞炵粍浠ｇ爜", "groupRegionCode"],
        "group_region_name": ["group_region_name", "鎵€灞炵粍鍚嶇О", "groupRegionName"],
    }
    member_field_map = {
        "cbfbm": ["cbfbm", "承包方代码", "contractorCode"],
        "cyxm": ["cyxm", "鎴愬憳濮撳悕", "濮撳悕", "name"],
        "cyzjlx": ["cyzjlx", "璇佷欢绫诲瀷", "idType"],
        "cyzjhm": ["cyzjhm", "璇佷欢鍙风爜", "韬唤璇佸彿", "idNo"],
        "cyxb": ["cyxb", "鎬у埆", "gender"],
        "yhzgx": ["yhzgx", "与户主关系", "relationToHead"],
        "cybz": ["cybz", "鎴愬憳澶囨敞浠ｇ爜", "澶囨敞浠ｇ爜", "noteCode"],
        "sfgyr": ["sfgyr", "是否共有人", "isCoOwner"],
        "cybzsm": ["cybzsm", "鎴愬憳澶囨敞璇存槑", "澶囨敞璇存槑", "note"],
    }
    fbf_field_map = {
        "fbfbm": ["fbfbm", "FBFBM", "code"],
        "fbfmc": ["fbfmc", "FBFMC", "name"],
        "fbffzrxm": ["fbffzrxm", "FBFFZRXM", "ownerName"],
        "fzrzjlx": ["fzrzjlx", "FZRZJLX", "ownerIdType"],
        "fzrzjhm": ["fzrzjhm", "FZRZJHM", "ownerIdNo"],
        "lxdh": ["lxdh", "LXDH", "mobile"],
        "fbfdz": ["fbfdz", "FBFDZ", "address"],
        "yzbm": ["yzbm", "YZBM", "postcode"],
        "fbfdcy": ["fbfdcy", "FBFDCY", "surveyorName"],
        "fbfdcrq": ["fbfdcrq", "FBFDCRQ", "surveyDate"],
        "fbfdcjs": ["fbfdcjs", "FBFDCJS", "notes"],
        "region_code": ["region_code", "REGION_CODE", "regionCode"],
        "region_name": ["region_name", "REGION_NAME", "regionName"],
    }
    cbdkxx_field_map = {
        "dkbm": ["dkbm", "DKBM"],
        "fbfbm": ["fbfbm", "FBFBM"],
        "cbfbm": ["cbfbm", "CBFBM"],
        "cbjyqqdfs": ["cbjyqqdfs", "CBJYQQDFS"],
        "htmj": ["htmj", "HTMJ"],
        "cbhtbm": ["cbhtbm", "CBHTBM"],
        "lzhtbm": ["lzhtbm", "LZHTBM"],
        "cbjyqzbm": ["cbjyqzbm", "CBJYQZBM"],
        "yhtmj": ["yhtmj", "YHTMJ"],
        "htmjm": ["htmjm", "HTMJM"],
        "yhtmjm": ["yhtmjm", "YHTMJM"],
        "sfqqqg": ["sfqqqg", "SFQQQG"],
        "region_code": ["region_code", "REGION_CODE", "regionCode"],
    }
    dk_field_map = {
        "bsm": ["bsm", "BSM"],
        "ysdm": ["ysdm", "YSDM"],
        "dkbm": ["dkbm", "DKBM"],
        "dkmc": ["dkmc", "DKMC"],
        "syqxz": ["syqxz", "SYQXZ"],
        "dklb": ["dklb", "DKLB"],
        "tdlylx": ["tdlylx", "TDLYLX"],
        "dldj": ["dldj", "DLDJ"],
        "tdyt": ["tdyt", "TDYT"],
        "sfjbnt": ["sfjbnt", "SFJBNT"],
        "scmj": ["scmj", "SCMJ"],
        "dkdz": ["dkdz", "DKDZ"],
        "dkxz": ["dkxz", "DKXZ"],
        "dknz": ["dknz", "DKNZ"],
        "dkbz": ["dkbz", "DKBZ"],
        "dkbzxx": ["dkbzxx", "DKBZXX"],
        "zjrxm": ["zjrxm", "ZJRXM"],
        "region_code": ["region_code", "REGION_CODE", "regionCode"],
    }
    gdb_layer_order = ("fbf", "cbf", "cbf_jtcy", "cbdkxx", "dk")
    gdb_layer_aliases = {
        "fbf": {"fbf"},
        "cbf": {"cbf"},
        "cbf_jtcy": {"cbfjtcy", "cbf_jtcy", "jtcy"},
        "cbdkxx": {"cbdkxx"},
        "dk": {"dk"},
    }
    template_headers = {
        "cbf": [
            "承包方代码", "区域代码", "区域名称", "承包方类型", "承包方名称",
            "证件类型", "证件号码", "承包方地址", "邮政编码", "联系电话",
            "家庭成员数", "承包方调查日期", "承包方调查员", "承包方调查记事",
            "公示记事", "公示记事人", "公示审核日期", "公示审核人",
            "所属组代码", "所属组名称",
        ],
        "cbf_jtcy": [
            "承包方代码", "成员姓名", "证件类型", "证件号码", "性别",
            "与户主关系", "成员备注代码", "是否共有人", "成员备注说明",
        ],
    }
    template_field_notes = {
        "cbf": [
            ("承包方代码", "必填，18位承包方代码"),
            ("区域代码", "必填，填写实际所属村/组等区域代码"),
            ("区域名称", "选填，留空时可按区域代码补全"),
            ("承包方类型", "必填，1=农户，2=个人，3=单位"),
            ("承包方名称", "必填，农户填写户主或代表名称"),
            ("证件类型", "必填，1=居民身份证，4=户口簿，9=其他"),
            ("证件号码", "必填"),
            ("承包方地址", "必填"),
            ("邮政编码", "必填，6位"),
            ("联系电话", "选填"),
            ("家庭成员数", "选填，导入成员后会自动回填"),
            ("承包方调查日期", "选填，格式 YYYY-MM-DD"),
            ("承包方调查员", "必填"),
            ("承包方调查记事", "选填"),
            ("公示记事", "选填"),
            ("公示记事人", "选填"),
            ("公示审核日期", "选填，格式 YYYY-MM-DD"),
            ("公示审核人", "选填"),
            ("所属组代码", "选填，必须在当前调查员可操作的数据权限范围内"),
            ("所属组名称", "选填，留空时按所属组代码自动取区域全称"),
        ],
        "cbf_jtcy": [
            ("承包方代码", "必填，必须已先导入同批次承包方数据"),
            ("成员姓名", "必填"),
            ("证件类型", "必填，1=居民身份证，4=户口簿，9=其他"),
            ("证件号码", "必填，同一户内不可重复"),
            ("性别", "必填，1=男，2=女"),
            ("与户主关系", "必填，01=户主"),
            ("成员备注代码", "选填"),
            ("是否共有人", "选填，1=是，2=否"),
            ("成员备注说明", "选填"),
        ],
    }

    def list_batches(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        keyword: str | None,
        current_user: User,
    ) -> dict:
        stmt = select(DataImportBatch).order_by(DataImportBatch.id.desc()).offset((page - 1) * page_size).limit(page_size)
        total_stmt = select(func.count(DataImportBatch.id))
        if keyword:
            pattern = f"%{keyword.strip()}%"
            condition = or_(DataImportBatch.import_no.ilike(pattern), DataImportBatch.import_name.ilike(pattern))
            stmt = stmt.where(condition)
            total_stmt = total_stmt.where(condition)
        return {
            "items": [self._serialize_batch(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def create_batch(self, db: Session, payload: dict, current_user: User) -> dict:
        now = datetime.now(timezone.utc)
        batch = DataImportBatch(
            import_no=self._next_no(db, "IMP", DataImportBatch.id),
            import_name=payload["importName"],
            import_type=payload.get("importType") or "initial_build",
            source_type=payload.get("sourceType") or "csv",
            source_org=payload.get("sourceOrg"),
            region_code=payload.get("regionCode"),
            region_name=payload.get("regionName"),
            status="uploaded",
            imported_by=current_user.id,
            imported_by_name=current_user.real_name,
            imported_at=now,
            remark=payload.get("remark"),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return self._serialize_batch(batch)

    async def upload_csv(self, db: Session, batch_id: int, file_type: str, upload_file: UploadFile, current_user: User) -> dict:
        if file_type not in {"cbf", "cbf_jtcy"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="浠呮敮鎸?cbf 鎴?cbf_jtcy 鏁版嵁绫诲瀷")
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="涓婁紶鏂囦欢涓虹┖")

        now = datetime.now(timezone.utc)
        stats = self._process_csv_content(
            db,
            batch,
            file_type=file_type,
            original_name=upload_file.filename or "import.csv",
            content_type=upload_file.content_type,
            content=content,
            current_user=current_user,
            now=now,
        )
        self._finish_batch_import(
            db,
            batch,
            stats_list=[stats],
            source_name=stats["original_name"],
            file_hash=stats["file_hash"],
            current_user=current_user,
            now=now,
        )
        return self._serialize_batch(batch)

    async def upload_archive(self, db: Session, batch_id: int, upload_file: UploadFile, current_user: User) -> dict:
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import batch not found")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty")

        filename = upload_file.filename or "import.zip"
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="please upload a ZIP archive")

        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to read ZIP archive") from exc

        csv_files: dict[str, tuple[str, bytes]] = {}
        for item in archive.infolist():
            if item.is_dir():
                continue
            inner_name = PurePosixPath(item.filename).name
            if not inner_name.lower().endswith(".csv"):
                continue
            inferred_type = self._infer_archive_csv_type(inner_name)
            if inferred_type is None:
                continue
            if inferred_type in csv_files:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"duplicate {inferred_type} CSV file in archive")
            csv_files[inferred_type] = (inner_name, archive.read(item))

        missing = [label for key, label in (("cbf", "contractor"), ("cbf_jtcy", "member")) if key not in csv_files]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"archive missing {",".join(missing)} CSV file")

        now = datetime.now(timezone.utc)
        batch.source_type = "zip"
        archive_file = DataImportFile(
            import_batch_id=batch.id,
            file_type="archive",
            original_name=filename,
            content_type=upload_file.content_type,
            file_size=len(content),
            file_hash=hashlib.sha256(content).hexdigest(),
            parse_status="success",
            row_count=0,
            uploaded_by=current_user.id,
            uploaded_at=now,
            remark="contractor and member archive upload",
        )
        db.add(archive_file)
        db.flush()

        stats_list = []
        for file_type in ("cbf", "cbf_jtcy"):
            inner_name, inner_content = csv_files[file_type]
            stats = self._process_csv_content(
                db,
                batch,
                file_type=file_type,
                original_name=inner_name,
                content_type="text/csv",
                content=inner_content,
                current_user=current_user,
                now=now,
                remark=f"鏉ヨ嚜鍘嬬缉鍖咃細{filename}",
            )
            stats_list.append(stats)

        archive_file.row_count = sum(item["row_count"] for item in stats_list)
        archive_file.error_count = sum(item["failed_count"] for item in stats_list)
        archive_file.parse_status = "success" if archive_file.error_count == 0 else "partial_success"
        self._finish_batch_import(
            db,
            batch,
            stats_list=stats_list,
            source_name=filename,
            file_hash=archive_file.file_hash,
            current_user=current_user,
            now=now,
        )
        return self._serialize_batch(batch)

    async def upload_gdb_archive(self, db: Session, batch_id: int, upload_file: UploadFile, current_user: User) -> dict:
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")
        if not batch.region_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="瀵煎叆 GDB 鍓嶈鍏堥€夋嫨瀵煎叆鍖哄煙")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="涓婁紶鏂囦欢涓虹┖")

        filename = upload_file.filename or "import_gdb.zip"
        return self._process_gdb_archive_content(db, batch, filename, content, upload_file.content_type, current_user)

    async def start_gdb_import_job(self, db: Session, batch_id: int, upload_file: UploadFile, current_user: User, background_tasks) -> dict:
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")
        if not batch.region_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="瀵煎叆 GDB 鍓嶈鍏堥€夋嫨瀵煎叆鍖哄煙")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="涓婁紶鏂囦欢涓虹┖")

        filename = upload_file.filename or "import_gdb.zip"
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="please upload a ZIP archive containing a .gdb directory")

        storage_dir = Path(__file__).resolve().parents[1] / "storage" / "data_imports" / str(batch.id)
        storage_dir.mkdir(parents=True, exist_ok=True)
        stored_path = storage_dir / f"{datetime.now():%Y%m%d%H%M%S}_{Path(filename).name}"
        stored_path.write_bytes(content)

        job_id = f"gdb:{batch.id}:{datetime.now(timezone.utc).timestamp()}"
        batch.status = "processing"
        batch.source_type = "gdb"
        batch.source_name = filename
        batch.imported_by = current_user.id
        batch.imported_by_name = current_user.real_name
        batch.imported_at = datetime.now(timezone.utc)
        db.commit()
        data_import_progress.init(
            batch.id,
            job_id,
            {
                "status": "queued",
                "message": "鏂囦欢宸蹭笂浼狅紝绛夊緟鍚庡彴瀵煎叆",
                "filename": filename,
                "fileSize": len(content),
            },
        )
        background_tasks.add_task(self.run_gdb_import_job, batch.id, str(stored_path), filename, upload_file.content_type, current_user.id, job_id)
        return {"batchId": batch.id, "jobId": job_id, "status": "queued"}

    def run_gdb_import_job(self, batch_id: int, stored_path: str, filename: str, content_type: str | None, user_id: int, job_id: str) -> None:
        db = SessionLocal()
        try:
            current_user = db.get(User, user_id)
            batch = db.get(DataImportBatch, batch_id)
            if current_user is None or batch is None:
                data_import_progress.update(batch_id, status="failed", message="import context not found")
                return
            set_current_user(db, current_user)
            data_import_progress.update(batch_id, status="running", message="background import started")
            content = Path(stored_path).read_bytes()
            self._process_gdb_archive_content(db, batch, filename, content, content_type, current_user, job_id=job_id)
        except ImportCanceled:
            db.rollback()
            batch = db.get(DataImportBatch, batch_id)
            if batch is not None:
                batch.status = "canceled"
                db.commit()
            data_import_progress.update(batch_id, status="canceled", message="import canceled")
            logger.info("GDB import canceled: batch_id=%s", batch_id)
        except Exception:
            db.rollback()
            batch = db.get(DataImportBatch, batch_id)
            if batch is not None:
                batch.status = "failed"
                db.commit()
            data_import_progress.update(batch_id, status="failed", message="import failed; see backend logs")
            logger.exception("GDB import job failed: batch_id=%s filename=%s", batch_id, filename)
        finally:
            db.close()

    def _process_gdb_archive_content(
        self,
        db: Session,
        batch: DataImportBatch,
        filename: str,
        content: bytes,
        content_type: str | None,
        current_user: User,
        job_id: str | None = None,
    ) -> dict:
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="please upload a ZIP archive containing a .gdb directory")

        try:
            logger.info(
                "GDB import started: batch_id=%s import_no=%s filename=%s size=%s user_id=%s region_code=%s",
                batch.id,
                batch.import_no,
                filename,
                len(content),
                current_user.id,
                batch.region_code,
            )
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            logger.warning("GDB import rejected: invalid zip batch_id=%s filename=%s", batch.id, filename)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="failed to read ZIP archive") from exc

        now = datetime.now(timezone.utc)
        batch.source_type = "gdb"
        archive_file = DataImportFile(
            import_batch_id=batch.id,
            file_type="gdb_archive",
            original_name=filename,
            content_type=content_type,
            file_size=len(content),
            file_hash=hashlib.sha256(content).hexdigest(),
            parse_status="success",
            row_count=0,
            uploaded_by=current_user.id,
            uploaded_at=now,
            remark="GDB archive import",
        )
        db.add(archive_file)
        db.flush()

        with tempfile.TemporaryDirectory(prefix="rural_gdb_") as temp_dir:
            self._extract_zip_safely(archive, temp_dir)
            gdb_path = self._find_gdb_path(temp_dir)
            logger.info("GDB extracted: batch_id=%s gdb_path=%s", batch.id, gdb_path)
            stats_list = self._process_gdb_layers(db, batch, gdb_path, current_user, now)

        archive_file.row_count = sum(item["row_count"] for item in stats_list)
        archive_file.error_count = sum(item["failed_count"] for item in stats_list)
        archive_file.parse_status = "success" if archive_file.error_count == 0 else ("partial_success" if archive_file.row_count else "failed")
        self._finish_batch_import(
            db,
            batch,
            stats_list=stats_list,
            source_name=filename,
            file_hash=archive_file.file_hash,
            current_user=current_user,
            now=now,
        )
        geoserver_service.recalculate_default_bounds()
        logger.info(
            "GDB import finished: batch_id=%s total=%s success=%s failed=%s",
            batch.id,
            batch.total_count,
            batch.success_count,
            batch.failed_count,
        )
        data_import_progress.update(batch.id, status=batch.status, message="瀵煎叆瀹屾垚")
        return self._serialize_batch(batch)

    def _extract_zip_safely(self, archive: zipfile.ZipFile, target_dir: str) -> None:
        for item in archive.infolist():
            if "\\" in item.filename:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP archive contains an unsafe path")
            item_path = PurePosixPath(item.filename)
            if item_path.is_absolute() or ".." in item_path.parts:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP archive contains an unsafe path")
        archive.extractall(target_dir)

    def _find_gdb_path(self, root_dir: str) -> str:
        from pathlib import Path

        for path in Path(root_dir).rglob("*.gdb"):
            if path.is_dir():
                return str(path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP 鍘嬬缉鍖呬腑鏈壘鍒?.gdb 鐩綍")

    def _process_gdb_layers(
        self,
        db: Session,
        batch: DataImportBatch,
        gdb_path: str,
        current_user: User,
        now: datetime,
    ) -> list[dict]:
        try:
            import fiona
        except ImportError as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="鍚庣缂哄皯 Fiona/GDAL锛屾棤娉曡鍙?GDB") from exc

        try:
            available_layers = list(fiona.listlayers(gdb_path))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"failed to read GDB layer: {exc}") from exc

        logger.info("GDB layers discovered: gdb_path=%s layers=%s", gdb_path, available_layers)
        layer_map: dict[str, str] = {}
        for layer_name in available_layers:
            file_type = self._infer_gdb_layer_type(layer_name)
            if file_type and file_type not in layer_map:
                layer_map[file_type] = layer_name

        total_rows = 0
        for layer_name in layer_map.values():
            try:
                with fiona.open(gdb_path, layer=layer_name) as source:
                    total_rows += len(source)
            except Exception:
                logger.exception("Failed to count GDB layer rows: gdb_path=%s layer=%s", gdb_path, layer_name)
        data_import_progress.update(batch.id, totalRows=total_rows, processedRows=0, successRows=0, failedRows=0, status="running", message="寮€濮嬭鍙?GDB 鍥惧眰")

        stats_list = []
        for file_type in self.gdb_layer_order:
            layer_name = layer_map.get(file_type)
            if not layer_name:
                continue
            stats_list.append(self._process_gdb_layer(db, batch, gdb_path, layer_name, file_type, current_user, now, fiona))

        if not stats_list:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GDB 涓湭璇嗗埆鍒?FBF銆丆BF銆丆BF_JTCY銆丆BDKXX 鎴?DK 鍥惧眰")
        return stats_list

    def _process_gdb_layer(
        self,
        db: Session,
        batch: DataImportBatch,
        gdb_path: str,
        layer_name: str,
        file_type: str,
        current_user: User,
        now: datetime,
        fiona_module,
    ) -> dict:
        field_map = self._field_map_for(file_type)
        import_file = DataImportFile(
            import_batch_id=batch.id,
            file_type=file_type,
            original_name=layer_name,
            content_type="application/x-filegdb-layer",
            file_size=0,
            parse_status="success",
            row_count=0,
            uploaded_by=current_user.id,
            uploaded_at=now,
            remark=f"from GDB layer: {layer_name}",
        )
        db.add(import_file)
        db.flush()

        success_count = 0
        failed_count = 0
        warning_count = 0
        seen_keys: set[str] = set()
        affected_contractors: set[str] = set()
        survey_batch = self._ensure_import_survey_batch(db, batch, current_user, now)
        progress = data_import_progress.get(batch.id) or {}
        progress_state = {
            "processedRows": int(progress.get("processedRows") or 0),
            "successRows": int(progress.get("successRows") or 0),
            "failedRows": int(progress.get("failedRows") or 0),
        }

        def update_progress(current_layer: str, *, force: bool = False) -> None:
            if not force and progress_state["processedRows"] % self.progress_update_interval != 0:
                return
            data_import_progress.update(
                batch.id,
                currentLayer=current_layer,
                processedRows=progress_state["processedRows"],
                successRows=progress_state["successRows"],
                failedRows=progress_state["failedRows"],
                message=f"姝ｅ湪瀵煎叆 {current_layer}",
            )

        def process_items(items: list[dict]) -> None:
            nonlocal success_count, failed_count
            if not items:
                return
            context = {"survey_batch": survey_batch, "gdb_result_only": True}
            for item in items:
                row_record = DataImportRow(
                    import_batch_id=batch.id,
                    import_file_id=import_file.id,
                    row_no=item["row_no"],
                    entity_type=file_type,
                    entity_key=item["entity_key"],
                    operation_type="insert",
                    status="pending",
                    target_table=f"survey_{file_type}_result",
                    raw_data=item["raw"],
                    normalized_data=item["normalized"],
                )
                row_status = "pending"
                try:
                    with db.begin_nested():
                        if not item["entity_key"]:
                            raise ValueError("鏃犳硶璇嗗埆涓氬姟涓婚敭")
                        if item["entity_key"] in seen_keys:
                            raise ValueError(f"鍚屼竴鍥惧眰鍐呬笟鍔′富閿噸澶嶏細{item['entity_key']}")
                        operation, target_id = self._import_row(
                            db,
                            batch,
                            import_file,
                            row_record,
                            file_type,
                            item["normalized"],
                            current_user,
                            now,
                            item.get("geometry"),
                            context,
                        )
                    seen_keys.add(item["entity_key"])
                    row_record.operation_type = operation
                    row_status = "success"
                    row_record.target_id = target_id
                    if item["normalized"].get("cbfbm"):
                        affected_contractors.add(item["normalized"]["cbfbm"])
                    success_count += 1
                except Exception as exc:
                    row_status = "failed"
                    row_record.status = "failed"
                    row_record.operation_type = "error"
                    row_record.error_message = str(exc)
                    db.add(row_record)
                    failed_count += 1
                    logger.exception(
                        "GDB row import failed: batch_id=%s file_type=%s layer=%s row_no=%s entity_key=%s normalized=%s raw=%s",
                        batch.id,
                        file_type,
                        layer_name,
                        item["row_no"],
                        item["entity_key"],
                        item["normalized"],
                        item["raw"],
                    )
                finally:
                    progress_state["processedRows"] += 1
                    progress_state["successRows"] += 1 if row_status == "success" else 0
                    progress_state["failedRows"] += 1 if row_status == "failed" else 0
                    update_progress(layer_name)
            db.commit()
            update_progress(layer_name, force=True)

        with fiona_module.open(gdb_path, layer=layer_name) as source:
            row_count = len(source)
            logger.info(
                "GDB layer import started: batch_id=%s file_type=%s layer=%s rows=%s",
                batch.id,
                file_type,
                layer_name,
                row_count,
            )
            pending_items: list[dict] = []
            for index, feature in enumerate(source, start=1):
                if data_import_progress.is_cancel_requested(batch.id):
                    raise ImportCanceled()
                raw = self._json_safe(dict(feature.get("properties") or {}))
                normalized = self._normalize_row(raw, field_map)
                self._apply_gdb_region_defaults(batch, normalized)
                pending_items.append(
                    {
                        "row_no": index,
                        "raw": raw,
                        "normalized": normalized,
                        "entity_key": self._entity_key(file_type, normalized),
                        "geometry": self._json_safe(feature.get("geometry")),
                    }
                )
                if len(pending_items) >= self.chunk_size:
                    process_items(pending_items)
                    pending_items = []
            process_items(pending_items)
            update_progress(layer_name, force=True)

        if file_type == "cbf_jtcy":
            self._recount_result_member_counts(db, affected_contractors, survey_batch.id)
        import_file.row_count = row_count
        import_file.error_count = failed_count
        import_file.parse_status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
        logger.info(
            "GDB layer import finished: batch_id=%s file_type=%s layer=%s rows=%s success=%s failed=%s",
            batch.id,
            file_type,
            layer_name,
            row_count,
            success_count,
            failed_count,
        )
        return {
            "file_type": file_type,
            "import_file_id": import_file.id,
            "original_name": layer_name,
            "file_hash": None,
            "row_count": row_count,
            "success_count": success_count,
            "failed_count": failed_count,
            "warning_count": warning_count,
            "affected_contractors": affected_contractors,
        }

    def _process_csv_content(
        self,
        db: Session,
        batch: DataImportBatch,
        *,
        file_type: str,
        original_name: str,
        content_type: str | None,
        content: bytes,
        current_user: User,
        now: datetime,
        remark: str | None = None,
    ) -> dict:
        file_hash = hashlib.sha256(content).hexdigest()
        text = self._decode_csv(content)
        rows = list(csv.DictReader(io.StringIO(text)))
        import_file = DataImportFile(
            import_batch_id=batch.id,
            file_type=file_type,
            original_name=original_name,
            content_type=content_type,
            file_size=len(content),
            file_hash=file_hash,
            parse_status="success",
            row_count=len(rows),
            uploaded_by=current_user.id,
            uploaded_at=now,
            remark=remark,
        )
        db.add(import_file)
        db.flush()

        success_count = 0
        failed_count = 0
        warning_count = 0
        seen_keys: set[str] = set()
        affected_contractors: set[str] = set()
        survey_batch = self._ensure_import_survey_batch(db, batch, current_user, now)
        context = {"survey_batch": survey_batch}
        for index, raw in enumerate(rows, start=2):
            normalized = self._normalize_row(raw, self._field_map_for(file_type))
            entity_key = self._entity_key(file_type, normalized)
            row_record = DataImportRow(
                import_batch_id=batch.id,
                import_file_id=import_file.id,
                row_no=index,
                entity_type=file_type,
                entity_key=entity_key,
                operation_type="insert",
                status="pending",
                target_table=file_type,
                raw_data=raw,
                normalized_data=normalized,
            )
            try:
                if not entity_key:
                    raise ValueError("鏃犳硶璇嗗埆涓氬姟涓婚敭")
                if entity_key in seen_keys:
                    raise ValueError(f"鍚屼竴鏂囦欢鍐呬笟鍔′富閿噸澶嶏細{entity_key}")
                seen_keys.add(entity_key)
                operation, target_id = self._import_row(db, batch, import_file, row_record, file_type, normalized, current_user, now, context=context)
                row_record.operation_type = operation
                row_record.status = "success"
                row_record.target_id = target_id
                if normalized.get("cbfbm"):
                    affected_contractors.add(normalized["cbfbm"])
                success_count += 1
            except Exception as exc:
                row_record.status = "failed"
                row_record.operation_type = "error"
                row_record.error_message = str(exc)
                db.add(row_record)
                failed_count += 1
        if file_type == "cbf_jtcy":
            self._recount_member_counts(db, affected_contractors)
        import_file.error_count = failed_count
        import_file.parse_status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
        return {
            "file_type": file_type,
            "import_file_id": import_file.id,
            "original_name": original_name,
            "file_hash": file_hash,
            "row_count": len(rows),
            "success_count": success_count,
            "failed_count": failed_count,
            "warning_count": warning_count,
            "affected_contractors": affected_contractors,
        }

    def _chunks(self, items: list, size: int):
        for start in range(0, len(items), size):
            yield items[start : start + size]

    def _has_any(self, db: Session, model, *conditions) -> bool:
        primary_key = sa_inspect(model).primary_key[0]
        stmt = select(primary_key).limit(1)
        if conditions:
            stmt = stmt.where(*conditions)
        return db.scalar(stmt) is not None

    def _build_import_existing_state(self, db: Session, survey_batch: SurveyBatch, file_type: str) -> dict[str, bool]:
        if file_type == "cbf":
            return {
                "cbf_base": self._has_any(db, SurveyCbfBase, SurveyCbfBase.batch_id == survey_batch.id),
                "cbf_result": self._has_any(db, SurveyCbfResult, SurveyCbfResult.base_id.in_(select(SurveyCbfBase.id).where(SurveyCbfBase.batch_id == survey_batch.id))),
                "contractor_task": self._has_any(db, SurveyContractorTask, SurveyContractorTask.batch_id == survey_batch.id),
            }
        if file_type == "cbf_jtcy":
            return {
                "contractor_base": self._has_any(db, SurveyCbfBase, SurveyCbfBase.batch_id == survey_batch.id),
                "member_base": self._has_any(db, SurveyCbfJtcyBase, SurveyCbfJtcyBase.batch_id == survey_batch.id),
                "member_result": self._has_any(db, SurveyCbfJtcyResult, SurveyCbfJtcyResult.base_id.in_(select(SurveyCbfJtcyBase.id).where(SurveyCbfJtcyBase.batch_id == survey_batch.id))),
            }
        if file_type == "fbf":
            return {
                "fbf_base": self._has_any(db, SurveyFbfBase, SurveyFbfBase.batch_id == survey_batch.id),
                "fbf_result": self._has_any(db, SurveyFbfResult, SurveyFbfResult.base_id.in_(select(SurveyFbfBase.id).where(SurveyFbfBase.batch_id == survey_batch.id))),
                "legacy_fbf": self._has_any(db, Fbf),
            }
        if file_type == "cbdkxx":
            return {
                "cbdkxx_base": self._has_any(db, SurveyCbdkxxBase, SurveyCbdkxxBase.batch_id == survey_batch.id),
                "cbdkxx_result": self._has_any(db, SurveyCbdkxxResult, SurveyCbdkxxResult.base_id.in_(select(SurveyCbdkxxBase.id).where(SurveyCbdkxxBase.batch_id == survey_batch.id))),
            }
        if file_type == "dk":
            return {
                "dk_base": self._has_any(db, SurveyDkBase, SurveyDkBase.batch_id == survey_batch.id),
                "dk_result": self._has_any(db, SurveyDkResult, SurveyDkResult.base_id.in_(select(SurveyDkBase.id).where(SurveyDkBase.batch_id == survey_batch.id))),
            }
        return {}

    def _can_bulk_insert_new_items(self, file_type: str, existing_state: dict[str, bool]) -> bool:
        if file_type == "cbf_jtcy" and not existing_state.get("contractor_base", False):
            return False
        required_empty_tables = {
            "cbf": ("cbf_base", "cbf_result", "contractor_task"),
            "cbf_jtcy": ("member_base", "member_result"),
            "fbf": ("fbf_base", "fbf_result", "legacy_fbf"),
            "cbdkxx": ("cbdkxx_base", "cbdkxx_result"),
            "dk": ("dk_base", "dk_result"),
        }.get(file_type)
        if not required_empty_tables:
            return False
        return not any(existing_state.get(key, True) for key in required_empty_tables)

    def _validate_bulk_item_key(self, item: dict, seen_keys: set[str], local_seen: set[str]) -> str:
        entity_key = item["entity_key"]
        if not entity_key:
            raise ValueError("鏃犳硶璇嗗埆涓氬姟涓婚敭")
        if entity_key in seen_keys or entity_key in local_seen:
            raise ValueError(f"鍚屼竴鍥惧眰鍐呬笟鍔′富閿噸澶嶏細{entity_key}")
        return entity_key

    def _add_failed_import_row(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        file_type: str,
        item: dict,
        exc: Exception,
    ) -> None:
        db.add(
            DataImportRow(
                import_batch_id=batch.id,
                import_file_id=import_file.id,
                row_no=item["row_no"],
                entity_type=file_type,
                entity_key=item["entity_key"],
                operation_type="error",
                status="failed",
                target_table=f"survey_{file_type}_base" if file_type not in {"cbf", "cbf_jtcy"} else file_type,
                raw_data=item["raw"],
                normalized_data=item["normalized"],
                error_message=str(exc),
            )
        )

    def _bulk_insert_new_items(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        survey_batch: SurveyBatch,
        file_type: str,
        items: list[dict],
        current_user: User,
        now: datetime,
        seen_keys: set[str],
    ) -> tuple[int, int, set[str]]:
        if file_type == "cbf":
            return self._bulk_insert_new_cbf(db, batch, import_file, survey_batch, items, current_user, now, seen_keys)
        if file_type == "cbf_jtcy":
            return self._bulk_insert_new_members(db, batch, import_file, survey_batch, items, current_user, now, seen_keys)
        if file_type == "fbf":
            return self._bulk_insert_new_fbf(db, batch, import_file, survey_batch, items, current_user, now, seen_keys)
        if file_type == "cbdkxx":
            return self._bulk_insert_new_cbdkxx(db, batch, import_file, survey_batch, items, current_user, now, seen_keys)
        if file_type == "dk":
            return self._bulk_insert_new_dk(db, batch, import_file, survey_batch, items, current_user, now, seen_keys)
            raise ValueError(f"unsupported data type: {file_type}")

    def _bulk_insert_new_cbf(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        survey_batch: SurveyBatch,
        items: list[dict],
        current_user: User,
        now: datetime,
        seen_keys: set[str],
    ) -> tuple[int, int, set[str]]:
        bases: list[SurveyCbfBase] = []
        tasks: list[SurveyContractorTask] = []
        local_seen: set[str] = set()
        failed_count = 0
        for item in items:
            data = item["normalized"]
            try:
                entity_key = self._validate_bulk_item_key(item, seen_keys, local_seen)
                required = ["cbfbm", "region_code", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "cbfdcy"]
                self._ensure_required(data, required)
                data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="鎵垮寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
                region_code, _region_name = self._resolve_import_region(db, data, current_user)
                tenant_code = data_access_service.derive_tenant_code(region_code)
                group_region_code, group_region_name = self._resolve_group_region(db, data, current_user)
                contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:cbf:{data['cbfbm']}"))
                bases.append(
                    SurveyCbfBase(
                        tenant_code=tenant_code,
                        region_code=region_code,
                        batch_id=survey_batch.id,
                        contractor_uid=contractor_uid,
                        source_cbfbm=data["cbfbm"],
                        cbfbm=data["cbfbm"],
                        cbflx=data["cbflx"],
                        cbfmc=data["cbfmc"],
                        cbfzjlx=data["cbfzjlx"],
                        cbfzjhm=data["cbfzjhm"],
                        cbfdz=data["cbfdz"],
                        yzbm=data["yzbm"],
                        lxdh=data.get("lxdh"),
                        cbfcysl=self._parse_int(data.get("cbfcysl"), default=0),
                        cbfdcrq=self._parse_datetime(data.get("cbfdcrq")) or datetime.now(),
                        cbfdcy=data.get("cbfdcy") or current_user.real_name,
                        cbfdcjs=data.get("cbfdcjs"),
                        gsjs=data.get("gsjs"),
                        gsjsr=data.get("gsjsr"),
                        gsshrq=self._parse_datetime(data.get("gsshrq")),
                        gsshr=data.get("gsshr"),
                        group_region_code=group_region_code,
                        group_region_name=group_region_name,
                        source_import_batch_id=batch.id,
                        last_import_batch_id=batch.id,
                        initialized_from_table="import",
                        initialized_from_key=data["cbfbm"],
                        initialized_at=now,
                        snapshot_at=now,
                    )
                )
                tasks.append(
                    SurveyContractorTask(
                        tenant_code=tenant_code,
                        region_code=region_code,
                        batch_id=survey_batch.id,
                        contractor_uid=contractor_uid,
                        cbfbm=data["cbfbm"],
                        cbfmc=data["cbfmc"],
                        task_status="not_started",
                    )
                )
                local_seen.add(entity_key)
            except Exception as exc:
                failed_count += 1
                self._add_failed_import_row(db, batch, import_file, "cbf", item, exc)
        if bases:
            db.add_all(bases)
            db.flush()
            results = []
            for base in bases:
                result = SurveyCbfResult(
                    contractor_uid=base.contractor_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                self._copy_base_to_contractor_result(result, base)
                results.append(result)
            db.add_all(results)
            db.add_all(tasks)
            db.flush()
        seen_keys.update(local_seen)
        return len(bases), failed_count, {base.cbfbm for base in bases}

    def _bulk_insert_new_members(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        survey_batch: SurveyBatch,
        items: list[dict],
        current_user: User,
        now: datetime,
        seen_keys: set[str],
    ) -> tuple[int, int, set[str]]:
        cbfbms = {item["normalized"].get("cbfbm") for item in items if item["normalized"].get("cbfbm")}
        contractor_bases = db.scalars(
            select(SurveyCbfBase).where(SurveyCbfBase.batch_id == survey_batch.id, SurveyCbfBase.source_cbfbm.in_(cbfbms))
        ).all() if cbfbms else []
        contractor_by_code = {item.source_cbfbm: item for item in contractor_bases}
        bases: list[SurveyCbfJtcyBase] = []
        local_seen: set[str] = set()
        failed_count = 0
        for item in items:
            data = item["normalized"]
            try:
                entity_key = self._validate_bulk_item_key(item, seen_keys, local_seen)
                required = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx"]
                self._ensure_required(data, required)
                data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
                contractor_base = contractor_by_code.get(data["cbfbm"])
                if contractor_base is None:
                    raise ValueError(f"member contractor not found: {data['cbfbm']}")
                member_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:member:{data['cbfbm']}:{data['cyzjhm']}"))
                bases.append(
                    SurveyCbfJtcyBase(
                        tenant_code=contractor_base.tenant_code,
                        region_code=contractor_base.region_code,
                        batch_id=survey_batch.id,
                        contractor_uid=contractor_base.contractor_uid,
                        member_uid=member_uid,
                        base_contractor_code=data["cbfbm"],
                        base_member_id_no=data["cyzjhm"],
                        cbfbm=data["cbfbm"],
                        cyxm=data["cyxm"],
                        cyzjlx=data["cyzjlx"],
                        cyzjhm=data["cyzjhm"],
                        cyxb=data["cyxb"],
                        yhzgx=data["yhzgx"],
                        cybz=data.get("cybz"),
                        sfgyr=data.get("sfgyr"),
                        cybzsm=data.get("cybzsm"),
                        source_import_batch_id=batch.id,
                        last_import_batch_id=batch.id,
                        initialized_from_table="import",
                        initialized_from_key=f"{data['cbfbm']}:{data['cyzjhm']}",
                        initialized_at=now,
                        snapshot_at=now,
                    )
                )
                local_seen.add(entity_key)
            except Exception as exc:
                failed_count += 1
                self._add_failed_import_row(db, batch, import_file, "cbf_jtcy", item, exc)
        if bases:
            db.add_all(bases)
            db.flush()
            results = []
            for base in bases:
                result = SurveyCbfJtcyResult(
                    contractor_uid=base.contractor_uid,
                    member_uid=base.member_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                self._copy_base_to_member_result(result, base)
                results.append(result)
            db.add_all(results)
            db.flush()
        seen_keys.update(local_seen)
        return len(bases), failed_count, {base.cbfbm for base in bases}

    def _bulk_insert_new_fbf(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        survey_batch: SurveyBatch,
        items: list[dict],
        current_user: User,
        now: datetime,
        seen_keys: set[str],
    ) -> tuple[int, int, set[str]]:
        bases: list[SurveyFbfBase] = []
        legacy_rows: list[Fbf] = []
        local_seen: set[str] = set()
        failed_count = 0
        for item in items:
            data = item["normalized"]
            try:
                entity_key = self._validate_bulk_item_key(item, seen_keys, local_seen)
                required = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq"]
                self._ensure_required(data, required)
                data_access_service.ensure_code_in_scope(current_user, data["fbfbm"], detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
                region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["fbfbm"], current_user)
                tenant_code = data_access_service.derive_tenant_code(region_code)
                issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:fbf:{data['fbfbm']}"))
                survey_date = self._parse_datetime(data.get("fbfdcrq")) or datetime.now()
                bases.append(
                    SurveyFbfBase(
                        tenant_code=tenant_code,
                        region_code=region_code,
                        batch_id=survey_batch.id,
                        issuer_uid=issuer_uid,
                        source_fbfbm=data["fbfbm"],
                        fbfbm=data["fbfbm"],
                        fbfmc=data["fbfmc"],
                        fbffzrxm=data["fbffzrxm"],
                        fzrzjlx=data["fzrzjlx"],
                        fzrzjhm=data["fzrzjhm"],
                        lxdh=data.get("lxdh"),
                        fbfdz=data["fbfdz"],
                        yzbm=data["yzbm"],
                        fbfdcy=data["fbfdcy"],
                        fbfdcrq=survey_date,
                        fbfdcjs=data.get("fbfdcjs"),
                        source_import_batch_id=batch.id,
                        last_import_batch_id=batch.id,
                        initialized_from_table="import",
                        initialized_from_key=data["fbfbm"],
                        initialized_at=now,
                        snapshot_at=now,
                    )
                )
                legacy_rows.append(
                    Fbf(
                        tenant_code=tenant_code,
                        region_code=region_code,
                        fbfbm=data["fbfbm"],
                        fbfmc=data["fbfmc"],
                        fbffzrxm=data["fbffzrxm"],
                        fzrzjlx=data["fzrzjlx"],
                        fzrzjhm=data["fzrzjhm"],
                        lxdh=data.get("lxdh"),
                        fbfdz=data["fbfdz"],
                        yzbm=data["yzbm"],
                        fbfdcy=data["fbfdcy"],
                        fbfdcrq=survey_date,
                        fbfdcjs=data.get("fbfdcjs"),
                    )
                )
                local_seen.add(entity_key)
            except Exception as exc:
                failed_count += 1
                self._add_failed_import_row(db, batch, import_file, "fbf", item, exc)
        if bases:
            db.add_all(bases)
            db.flush()
            results = []
            for base in bases:
                result = SurveyFbfResult(
                    issuer_uid=base.issuer_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                self._copy_base_to_fbf_result(result, base)
                results.append(result)
            db.add_all(results)
            db.add_all(legacy_rows)
            db.flush()
        seen_keys.update(local_seen)
        return len(bases), failed_count, set()

    def _bulk_insert_new_cbdkxx(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        survey_batch: SurveyBatch,
        items: list[dict],
        current_user: User,
        now: datetime,
        seen_keys: set[str],
    ) -> tuple[int, int, set[str]]:
        bases: list[SurveyCbdkxxBase] = []
        local_seen: set[str] = set()
        failed_count = 0
        for item in items:
            data = item["normalized"]
            try:
                entity_key = self._validate_bulk_item_key(item, seen_keys, local_seen)
                required = ["dkbm", "fbfbm", "cbfbm", "cbjyqqdfs", "htmj", "cbhtbm", "cbjyqzbm"]
                self._ensure_required(data, required)
                data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
                region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["cbfbm"], current_user)
                tenant_code = data_access_service.derive_tenant_code(region_code)
                parcel_info_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:cbdkxx:{data['dkbm']}:{data['cbfbm']}"))
                bases.append(
                    SurveyCbdkxxBase(
                        tenant_code=tenant_code,
                        region_code=region_code,
                        batch_id=survey_batch.id,
                        parcel_info_uid=parcel_info_uid,
                        source_dkbm=data["dkbm"],
                        dkbm=data["dkbm"],
                        fbfbm=data["fbfbm"],
                        cbfbm=data["cbfbm"],
                        cbjyqqdfs=data["cbjyqqdfs"],
                        htmj=self._parse_decimal(data.get("htmj"), required=True),
                        cbhtbm=data["cbhtbm"],
                        lzhtbm=data.get("lzhtbm"),
                        cbjyqzbm=data["cbjyqzbm"],
                        yhtmj=self._parse_decimal(data.get("yhtmj")),
                        htmjm=self._parse_decimal(data.get("htmjm")),
                        yhtmjm=self._parse_decimal(data.get("yhtmjm")),
                        sfqqqg=data.get("sfqqqg"),
                        source_import_batch_id=batch.id,
                        last_import_batch_id=batch.id,
                        initialized_from_table="import",
                        initialized_from_key=f"{data['dkbm']}:{data['cbfbm']}",
                        initialized_at=now,
                        snapshot_at=now,
                    )
                )
                local_seen.add(entity_key)
            except Exception as exc:
                failed_count += 1
                self._add_failed_import_row(db, batch, import_file, "cbdkxx", item, exc)
        if bases:
            db.add_all(bases)
            db.flush()
            results = []
            for base in bases:
                result = SurveyCbdkxxResult(
                    parcel_info_uid=base.parcel_info_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                self._copy_base_to_cbdkxx_result(result, base)
                results.append(result)
            db.add_all(results)
            db.flush()
        seen_keys.update(local_seen)
        return len(bases), failed_count, {base.cbfbm for base in bases}

    def _bulk_insert_new_dk(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        survey_batch: SurveyBatch,
        items: list[dict],
        current_user: User,
        now: datetime,
        seen_keys: set[str],
    ) -> tuple[int, int, set[str]]:
        bases: list[SurveyDkBase] = []
        base_geometries: list[dict | None] = []
        local_seen: set[str] = set()
        failed_count = 0
        for item in items:
            data = item["normalized"]
            try:
                entity_key = self._validate_bulk_item_key(item, seen_keys, local_seen)
                required = ["ysdm", "dkbm", "dkmc", "dklb", "dldj", "tdyt", "sfjbnt", "scmj"]
                self._ensure_required(data, required)
                data_access_service.ensure_code_in_scope(current_user, data["dkbm"], detail="out of scope")
                region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["dkbm"], current_user)
                tenant_code = data_access_service.derive_tenant_code(region_code)
                parcel_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:dk:{data['dkbm']}"))
                bases.append(
                    SurveyDkBase(
                        tenant_code=tenant_code,
                        region_code=region_code,
                        batch_id=survey_batch.id,
                        parcel_uid=parcel_uid,
                        source_dkbm=data["dkbm"],
                        bsm=self._parse_int(data.get("bsm"), default=0) if data.get("bsm") else None,
                        ysdm=data["ysdm"],
                        dkbm=data["dkbm"],
                        dkmc=data["dkmc"],
                        syqxz=data.get("syqxz"),
                        dklb=data["dklb"],
                        tdlylx=data.get("tdlylx"),
                        dldj=data["dldj"],
                        tdyt=data["tdyt"],
                        sfjbnt=data["sfjbnt"],
                        scmj=self._parse_decimal(data.get("scmj"), required=True),
                        dkdz=data.get("dkdz"),
                        dkxz=data.get("dkxz"),
                        dknz=data.get("dknz"),
                        dkbz=data.get("dkbz"),
                        dkbzxx=data.get("dkbzxx"),
                        zjrxm=data.get("zjrxm"),
                        source_import_batch_id=batch.id,
                        last_import_batch_id=batch.id,
                        initialized_from_table="import",
                        initialized_from_key=data["dkbm"],
                        initialized_at=now,
                        snapshot_at=now,
                    )
                )
                base_geometries.append(item.get("geometry"))
                local_seen.add(entity_key)
            except Exception as exc:
                failed_count += 1
                self._add_failed_import_row(db, batch, import_file, "dk", item, exc)
        if bases:
            db.add_all(bases)
            db.flush()
            self._write_dk_geometries(db, "survey_dk_base", {base.id: geometry for base, geometry in zip(bases, base_geometries)})
            results = []
            for base in bases:
                result = SurveyDkResult(
                    parcel_uid=base.parcel_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                self._copy_base_to_dk_result(result, base)
                results.append(result)
            db.add_all(results)
            db.flush()
            self._copy_dk_result_geometries(db, [base.id for base in bases])
        seen_keys.update(local_seen)
        return len(bases), failed_count, set()

    def _build_import_context(
        self,
        db: Session,
        batch: DataImportBatch,
        survey_batch: SurveyBatch,
        file_type: str,
        items: list[dict],
        existing_state: dict[str, bool] | None = None,
    ) -> dict:
        context = {"survey_batch": survey_batch}
        existing_state = existing_state or {}
        values = [item["normalized"] for item in items]

        if file_type == "cbf":
            cbfbms = {item.get("cbfbm") for item in values if item.get("cbfbm")}
            bases = (
                db.scalars(
                    select(SurveyCbfBase).where(SurveyCbfBase.batch_id == survey_batch.id, SurveyCbfBase.source_cbfbm.in_(cbfbms))
                ).all()
                if cbfbms and existing_state.get("cbf_base", True)
                else []
            )
            base_by_key = {item.source_cbfbm: item for item in bases}
            base_ids = [item.id for item in bases]
            results = (
                db.scalars(
                    select(SurveyCbfResult).where(SurveyCbfResult.base_id.in_(base_ids))
                ).all()
                if base_ids and existing_state.get("cbf_result", True)
                else []
            )
            tasks = (
                db.scalars(
                    select(SurveyContractorTask).where(SurveyContractorTask.batch_id == survey_batch.id, SurveyContractorTask.cbfbm.in_(cbfbms))
                ).all()
                if cbfbms and existing_state.get("contractor_task", True)
                else []
            )
            context.update(
                {
                    "cbf_base_by_source": base_by_key,
                    "cbf_result_by_base_id": {item.base_id: item for item in results},
                    "contractor_task_by_cbfbm": {item.cbfbm: item for item in tasks},
                }
            )
            return context

        if file_type == "cbf_jtcy":
            cbfbms = {item.get("cbfbm") for item in values if item.get("cbfbm")}
            member_ids = {item.get("cyzjhm") for item in values if item.get("cyzjhm")}
            contractor_bases = (
                db.scalars(
                    select(SurveyCbfBase).where(SurveyCbfBase.batch_id == survey_batch.id, SurveyCbfBase.source_cbfbm.in_(cbfbms))
                ).all()
                if cbfbms and existing_state.get("contractor_base", True)
                else []
            )
            member_bases = (
                db.scalars(
                    select(SurveyCbfJtcyBase).where(
                        SurveyCbfJtcyBase.batch_id == survey_batch.id,
                        SurveyCbfJtcyBase.base_contractor_code.in_(cbfbms),
                        SurveyCbfJtcyBase.base_member_id_no.in_(member_ids),
                    )
                ).all()
                if cbfbms and member_ids and existing_state.get("member_base", True)
                else []
            )
            member_base_ids = [item.id for item in member_bases]
            member_results = (
                db.scalars(
                    select(SurveyCbfJtcyResult).where(SurveyCbfJtcyResult.base_id.in_(member_base_ids))
                ).all()
                if member_base_ids and existing_state.get("member_result", True)
                else []
            )
            missing_cbfbms = cbfbms - {item.source_cbfbm for item in contractor_bases}
            source_results = (
                db.scalars(
                    select(SurveyCbfResult)
                    .where(SurveyCbfResult.cbfbm.in_(missing_cbfbms))
                    .order_by(SurveyCbfResult.id.desc())
                )
                .all()
                if missing_cbfbms
                else []
            )
            latest_source_results = {}
            for item in source_results:
                latest_source_results.setdefault(item.cbfbm, item)
            context.update(
                {
                    "contractor_base_by_cbfbm": {item.source_cbfbm: item for item in contractor_bases},
                    "member_base_by_key": {(item.base_contractor_code, item.base_member_id_no): item for item in member_bases},
                    "member_result_by_base_id": {item.base_id: item for item in member_results},
                    "source_result_by_cbfbm": latest_source_results,
                }
            )
            return context

        if file_type == "fbf":
            fbfbms = {item.get("fbfbm") for item in values if item.get("fbfbm")}
            bases = (
                db.scalars(
                    select(SurveyFbfBase).where(SurveyFbfBase.batch_id == survey_batch.id, SurveyFbfBase.source_fbfbm.in_(fbfbms))
                ).all()
                if fbfbms and existing_state.get("fbf_base", True)
                else []
            )
            base_ids = [item.id for item in bases]
            results = (
                db.scalars(
                    select(SurveyFbfResult).where(SurveyFbfResult.base_id.in_(base_ids))
                ).all()
                if base_ids and existing_state.get("fbf_result", True)
                else []
            )
            legacy_rows = (
                db.scalars(select(Fbf).where(Fbf.fbfbm.in_(fbfbms))).all()
                if fbfbms and existing_state.get("legacy_fbf", True)
                else []
            )
            context.update(
                {
                    "fbf_base_by_source": {item.source_fbfbm: item for item in bases},
                    "fbf_result_by_base_id": {item.base_id: item for item in results},
                    "legacy_fbf_by_code": {item.fbfbm: item for item in legacy_rows},
                }
            )
            return context

        if file_type == "cbdkxx":
            parcel_keys = {(item.get("dkbm"), item.get("cbfbm")) for item in values if item.get("dkbm") and item.get("cbfbm")}
            dkbms = {key[0] for key in parcel_keys}
            cbfbms = {key[1] for key in parcel_keys}
            bases = (
                db.scalars(
                    select(SurveyCbdkxxBase).where(
                        SurveyCbdkxxBase.batch_id == survey_batch.id,
                        SurveyCbdkxxBase.source_dkbm.in_(dkbms),
                        SurveyCbdkxxBase.cbfbm.in_(cbfbms),
                    )
                )
                .all()
                if dkbms and cbfbms and existing_state.get("cbdkxx_base", True)
                else []
            )
            base_ids = [item.id for item in bases]
            results = (
                db.scalars(
                    select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.base_id.in_(base_ids))
                ).all()
                if base_ids and existing_state.get("cbdkxx_result", True)
                else []
            )
            context.update(
                {
                    "cbdkxx_base_by_key": {(item.source_dkbm, item.cbfbm): item for item in bases},
                    "cbdkxx_result_by_base_id": {item.base_id: item for item in results},
                }
            )
            return context

        if file_type == "dk":
            dkbms = {item.get("dkbm") for item in values if item.get("dkbm")}
            bases = (
                db.scalars(
                    select(SurveyDkBase).where(SurveyDkBase.batch_id == survey_batch.id, SurveyDkBase.source_dkbm.in_(dkbms))
                ).all()
                if dkbms and existing_state.get("dk_base", True)
                else []
            )
            base_ids = [item.id for item in bases]
            results = (
                db.scalars(
                    select(SurveyDkResult).where(SurveyDkResult.base_id.in_(base_ids))
                ).all()
                if base_ids and existing_state.get("dk_result", True)
                else []
            )
            context.update(
                {
                    "dk_base_by_source": {item.source_dkbm: item for item in bases},
                    "dk_result_by_base_id": {item.base_id: item for item in results},
                }
            )
        return context

    def _finish_batch_import(
        self,
        db: Session,
        batch: DataImportBatch,
        *,
        stats_list: list[dict],
        source_name: str,
        file_hash: str | None,
        current_user: User,
        now: datetime,
    ) -> None:
        total_count = sum(item["row_count"] for item in stats_list)
        success_count = sum(item["success_count"] for item in stats_list)
        failed_count = sum(item["failed_count"] for item in stats_list)
        warning_count = sum(item["warning_count"] for item in stats_list)
        affected_contractors: set[str] = set()
        for item in stats_list:
            affected_contractors.update(item["affected_contractors"])

        batch.total_count += total_count
        batch.success_count += success_count
        batch.failed_count += failed_count
        batch.warning_count += warning_count
        batch.source_name = source_name
        batch.file_hash = file_hash
        batch.status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
        batch.validation_summary = {
            "lastFiles": [
                {"fileType": item["file_type"], "fileName": item["original_name"], "rows": item["row_count"]}
                for item in stats_list
            ]
        }
        batch.error_summary = {"lastFailedCount": failed_count}
        batch.imported_at = now
        db.commit()
        db.refresh(batch)

    def build_template_csv(self, file_type: str) -> tuple[str, bytes]:
        if file_type not in self.template_headers:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="浠呮敮鎸?cbf 鎴?cbf_jtcy 妯℃澘")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.template_headers[file_type])
        if file_type == "cbf":
            writer.writerow(
                [
                    "320623100200000001",
                    "320623100200",
                    "鏌愰晣鏌愭潙",
                    "1",
                    "field",
                    "1",
                    "320623199001010011",
                    "field",
                    "226400",
                    "13900000000",
                    "3",
                    "2026-05-01",
                    "璋冩煡鍛楢",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "32062310020001",
                    "field",
                ]
            )
        else:
            writer.writerow(["320623100200000001", "寮犱笁", "1", "320623199001010011", "1", "01", "", "1", "鎴蜂富"])
        return f"{file_type}_template.csv", output.getvalue().encode("utf-8-sig")

    def build_template_notes_csv(self, file_type: str) -> tuple[str, bytes]:
        if file_type not in self.template_field_notes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="浠呮敮鎸?cbf 鎴?cbf_jtcy 瀛楁璇存槑")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["瀛楁鍚嶇О", "濉啓璇存槑"])
        writer.writerows(self.template_field_notes[file_type])
        return f"{file_type}_field_notes.csv", output.getvalue().encode("utf-8-sig")

    def build_failed_rows_csv(self, db: Session, batch_id: int) -> tuple[str, bytes]:
        rows = db.scalars(
            select(DataImportRow)
            .where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
            .order_by(DataImportRow.row_no.asc(), DataImportRow.id.asc())
        ).all()
        output = io.StringIO()
        writer = csv.writer(output)
        # repaired invalid string literal
        for row in rows:
            writer.writerow([row.row_no, row.entity_type, row.entity_key, row.error_message, json.dumps(row.raw_data, ensure_ascii=False)])
        return f"import_{batch_id}_failed_rows.csv", output.getvalue().encode("utf-8-sig")

    def list_rows(self, db: Session, batch_id: int, page: int, page_size: int, status_filter: str | None) -> dict:
        if status_filter and status_filter != "failed":
            return {
                "items": [],
                "total": 0,
                "page": page,
                "pageSize": page_size,
            }
        stmt = (
            select(DataImportRow)
            .where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
            .order_by(DataImportRow.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total_stmt = select(func.count(DataImportRow.id)).where(DataImportRow.import_batch_id == batch_id, DataImportRow.status == "failed")
        return {
            "items": [self._serialize_row(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

    def rollback_batch(self, db: Session, batch_id: int, current_user: User) -> dict:
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request failed")
        operations = db.scalars(
            select(DataImportOperation)
            .where(DataImportOperation.import_batch_id == batch_id)
            .order_by(DataImportOperation.id.desc())
        ).all()
        if not operations:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request failed")

        model_map = self._rollback_model_map()
        restored = 0
        deleted = 0
        skipped = 0
        for operation in operations:
            model = model_map.get(operation.table_name)
            if model is None:
                skipped += 1
                continue
            instance = self._get_by_primary_key(db, model, operation.primary_key or {})
            if operation.operation_type == "insert":
                if instance is not None:
                    db.delete(instance)
                    deleted += 1
                else:
                    skipped += 1
                continue
            if operation.operation_type == "update" and operation.before_snapshot:
                if instance is None:
                    skipped += 1
                    continue
                self._restore_snapshot(instance, operation.before_snapshot)
                restored += 1
                continue
            skipped += 1

        batch.status = "rolled_back"
        batch.error_summary = {
            **(batch.error_summary or {}),
            "rollback": {"restored": restored, "deleted": deleted, "skipped": skipped, "by": current_user.id},
        }
        db.commit()
        db.refresh(batch)
        # repaired invalid string literal
        return self._serialize_batch(batch)

    def _import_row(
        self,
        db: Session,
        batch: DataImportBatch,
        import_file: DataImportFile,
        row_record: DataImportRow,
        file_type: str,
        data: dict,
        current_user: User,
        now: datetime,
        geometry: dict | None = None,
        context: dict | None = None,
    ) -> tuple[str, str]:
        survey_batch = context["survey_batch"] if context and context.get("survey_batch") else self._ensure_import_survey_batch(db, batch, current_user, now)
        if context and context.get("gdb_result_only"):
            return self._import_gdb_result_row(db, batch, survey_batch, row_record, file_type, data, current_user, now, geometry, context)
        if file_type == "cbf":
            required = ["cbfbm", "region_code", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "cbfdcy"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="鎵垮寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
            region_code, _region_name = self._resolve_import_region(db, data, current_user)
            tenant_code = data_access_service.derive_tenant_code(region_code)
            group_region_code, group_region_name = self._resolve_group_region(db, data, current_user)
            if context and "cbf_base_by_source" in context:
                base = context["cbf_base_by_source"].get(data["cbfbm"])
            else:
                base = db.scalar(
                    select(SurveyCbfBase).where(
                        SurveyCbfBase.batch_id == survey_batch.id,
                        SurveyCbfBase.source_cbfbm == data["cbfbm"],
                    )
                )
            operation = "update" if base else "insert"
            base_before = self._snapshot_model(base) if base else None
            chunk_no = max(1, (row_record.row_no - 1) // self.chunk_size + 1)
            contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:cbf:{data['cbfbm']}"))
            if base is None:
                base = SurveyCbfBase(
                    batch_id=survey_batch.id,
                    contractor_uid=contractor_uid,
                    source_cbfbm=data["cbfbm"],
                    initialized_from_key=data["cbfbm"],
                    initialized_at=now,
                    snapshot_at=now,
                )
                db.add(base)
            base.region_code = region_code
            base.tenant_code = tenant_code
            base.contractor_uid = contractor_uid
            base.source_cbfbm = data["cbfbm"]
            base.cbfbm = data["cbfbm"]
            base.cbflx = data["cbflx"]
            base.cbfmc = data["cbfmc"]
            base.cbfzjlx = data["cbfzjlx"]
            base.cbfzjhm = data["cbfzjhm"]
            base.cbfdz = data["cbfdz"]
            base.yzbm = data["yzbm"]
            base.lxdh = data.get("lxdh")
            base.cbfcysl = self._parse_int(data.get("cbfcysl"), default=0)
            base.cbfdcrq = self._parse_datetime(data.get("cbfdcrq")) or datetime.now()
            base.cbfdcy = data.get("cbfdcy") or current_user.real_name
            base.cbfdcjs = data.get("cbfdcjs")
            base.gsjs = data.get("gsjs")
            base.gsjsr = data.get("gsjsr")
            base.gsshrq = self._parse_datetime(data.get("gsshrq"))
            base.gsshr = data.get("gsshr")
            base.group_region_code = group_region_code
            base.group_region_name = group_region_name
            base.source_import_batch_id = base.source_import_batch_id or batch.id
            base.source_import_row_id = base.source_import_row_id or row_record.id
            base.last_import_batch_id = batch.id
            base.last_import_row_id = row_record.id
            base.initialized_from_table = "import"
            base.initialized_from_key = data["cbfbm"]
            base.snapshot_at = now
            db.flush()
            self._record_operation(db, batch, row_record, base, operation, base_before, chunk_no)

            if context and "cbf_result_by_base_id" in context:
                result = context["cbf_result_by_base_id"].get(base.id)
            else:
                result = db.scalar(
                    select(SurveyCbfResult).where(
                        SurveyCbfResult.base_id == base.id,
                    )
                )
            result_before = self._snapshot_model(result) if result else None
            if result is None:
                result = SurveyCbfResult(
                    contractor_uid=base.contractor_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                db.add(result)
                self._copy_base_to_contractor_result(result, base)
            elif not result.is_changed and result.survey_status == "not_surveyed":
                self._copy_base_to_contractor_result(result, base)
            db.flush()
            self._record_operation(db, batch, row_record, result, "update" if result_before else "insert", result_before, chunk_no)

            if context and "contractor_task_by_cbfbm" in context:
                task = context["contractor_task_by_cbfbm"].get(data["cbfbm"])
            else:
                task = db.scalar(
                    select(SurveyContractorTask).where(
                        SurveyContractorTask.batch_id == survey_batch.id,
                        SurveyContractorTask.cbfbm == data["cbfbm"],
                    )
                )
            if task is None:
                db.add(
                    SurveyContractorTask(
                        batch_id=survey_batch.id,
                        contractor_uid=contractor_uid,
                        cbfbm=data["cbfbm"],
                        cbfmc=data["cbfmc"],
                        region_code=region_code,
                        tenant_code=tenant_code,
                        task_status="not_started",
                    )
                )
            else:
                task.contractor_uid = contractor_uid
                task.cbfmc = data["cbfmc"]
                task.region_code = region_code
                task.tenant_code = tenant_code
            return operation, base.cbfbm

        if file_type == "fbf":
            return self._import_fbf_row(db, batch, survey_batch, row_record, data, current_user, now, context)
        if file_type == "cbdkxx":
            return self._import_cbdkxx_row(db, batch, survey_batch, row_record, data, current_user, now, context)
        if file_type == "dk":
            return self._import_dk_row(db, batch, survey_batch, row_record, data, current_user, now, geometry, context)
        if file_type != "cbf_jtcy":
            raise ValueError(f"unsupported data type: {file_type}")

        required = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx"]
        self._ensure_required(data, required)
        chunk_no = max(1, (row_record.row_no - 1) // self.chunk_size + 1)
        data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
        if context and "contractor_base_by_cbfbm" in context and data["cbfbm"] in context["contractor_base_by_cbfbm"]:
            contractor_base = context["contractor_base_by_cbfbm"].get(data["cbfbm"])
        else:
            contractor_base = db.scalar(
                select(SurveyCbfBase).where(
                    SurveyCbfBase.batch_id == survey_batch.id,
                    SurveyCbfBase.source_cbfbm == data["cbfbm"],
                )
            )
        if contractor_base is None:
            if context and "source_result_by_cbfbm" in context:
                source_result = context["source_result_by_cbfbm"].get(data["cbfbm"])
            else:
                source_result = db.scalars(
                    select(SurveyCbfResult)
                    .where(SurveyCbfResult.cbfbm == data["cbfbm"])
                    .order_by(SurveyCbfResult.id.desc())
                ).first()
            if source_result is None:
                raise ValueError(f"contractor not found: {data['cbfbm']}")
            contractor_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:cbf:{source_result.cbfbm}"))
            contractor_base = SurveyCbfBase(
                tenant_code=source_result.tenant_code,
                region_code=source_result.region_code,
                batch_id=survey_batch.id,
                contractor_uid=contractor_uid,
                source_cbfbm=source_result.cbfbm,
                cbfbm=source_result.cbfbm,
                cbflx=source_result.cbflx,
                cbfmc=source_result.cbfmc,
                cbfzjlx=source_result.cbfzjlx,
                cbfzjhm=source_result.cbfzjhm,
                cbfdz=source_result.cbfdz,
                yzbm=source_result.yzbm,
                lxdh=source_result.lxdh,
                cbfcysl=source_result.cbfcysl,
                cbfdcrq=source_result.cbfdcrq,
                cbfdcy=source_result.cbfdcy,
                cbfdcjs=source_result.cbfdcjs,
                gsjs=source_result.gsjs,
                gsjsr=source_result.gsjsr,
                gsshrq=source_result.gsshrq,
                gsshr=source_result.gsshr,
                group_region_code=source_result.group_region_code,
                group_region_name=source_result.group_region_name,
                source_import_batch_id=source_result.source_import_batch_id,
                source_import_row_id=source_result.source_import_row_id,
                last_import_batch_id=source_result.last_import_batch_id,
                last_import_row_id=source_result.last_import_row_id,
                initialized_from_table="survey_cbf_result",
                initialized_from_key=source_result.cbfbm,
                initialized_at=now,
                snapshot_at=now,
            )
            db.add(contractor_base)
            db.flush()
            self._record_operation(db, batch, row_record, contractor_base, "insert", None, chunk_no)
            cloned_result = SurveyCbfResult(
                tenant_code=contractor_base.tenant_code,
                region_code=contractor_base.region_code,
                contractor_uid=contractor_base.contractor_uid,
                base_id=contractor_base.id,
                initialized_from_base_id=contractor_base.id,
                initialized_at=now,
            )
            db.add(cloned_result)
            self._copy_base_to_contractor_result(cloned_result, contractor_base)
            db.flush()
            self._record_operation(db, batch, row_record, cloned_result, "insert", None, chunk_no)
            task = SurveyContractorTask(
                tenant_code=contractor_base.tenant_code,
                region_code=contractor_base.region_code,
                batch_id=survey_batch.id,
                contractor_uid=contractor_base.contractor_uid,
                cbfbm=contractor_base.cbfbm,
                cbfmc=contractor_base.cbfmc,
                task_status="not_started",
            )
            db.add(task)
            db.flush()
            self._record_operation(db, batch, row_record, task, "insert", None, chunk_no)
        member_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:member:{data['cbfbm']}:{data['cyzjhm']}"))
        member_key = (data["cbfbm"], data["cyzjhm"])
        if context and "member_base_by_key" in context:
            base = context["member_base_by_key"].get(member_key)
        else:
            base = db.scalar(
                select(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == survey_batch.id,
                    SurveyCbfJtcyBase.base_contractor_code == data["cbfbm"],
                    SurveyCbfJtcyBase.base_member_id_no == data["cyzjhm"],
                )
            )
        operation = "update" if base else "insert"
        base_before = self._snapshot_model(base) if base else None
        if base is None:
            base = SurveyCbfJtcyBase(
                batch_id=survey_batch.id,
                contractor_uid=contractor_base.contractor_uid,
                member_uid=member_uid,
                base_contractor_code=data["cbfbm"],
                base_member_id_no=data["cyzjhm"],
                initialized_from_key=f"{data['cbfbm']}:{data['cyzjhm']}",
                initialized_at=now,
                snapshot_at=now,
            )
            db.add(base)
        base.region_code = contractor_base.region_code
        base.tenant_code = contractor_base.tenant_code
        base.contractor_uid = contractor_base.contractor_uid
        base.member_uid = member_uid
        base.base_contractor_code = data["cbfbm"]
        base.base_member_id_no = data["cyzjhm"]
        base.cbfbm = data["cbfbm"]
        base.cyxm = data["cyxm"]
        base.cyzjlx = data["cyzjlx"]
        base.cyzjhm = data["cyzjhm"]
        base.cyxb = data["cyxb"]
        base.yhzgx = data["yhzgx"]
        base.cybz = data.get("cybz")
        base.sfgyr = data.get("sfgyr")
        base.cybzsm = data.get("cybzsm")
        base.source_import_batch_id = base.source_import_batch_id or batch.id
        base.source_import_row_id = base.source_import_row_id or row_record.id
        base.last_import_batch_id = batch.id
        base.last_import_row_id = row_record.id
        base.initialized_from_table = "import"
        base.initialized_from_key = f"{data['cbfbm']}:{data['cyzjhm']}"
        base.snapshot_at = now
        db.flush()
        self._record_operation(db, batch, row_record, base, operation, base_before, chunk_no)

        if context and "member_result_by_base_id" in context:
            result = context["member_result_by_base_id"].get(base.id)
        else:
            result = db.scalar(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.base_id == base.id,
                )
            )
        result_before = self._snapshot_model(result) if result else None
        if result is None:
            result = SurveyCbfJtcyResult(
                contractor_uid=contractor_base.contractor_uid,
                member_uid=member_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_member_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_member_result(result, base)
        db.flush()
        self._record_operation(db, batch, row_record, result, "update" if result_before else "insert", result_before, chunk_no)
        return operation, f"{base.cbfbm}:{base.cyzjhm}"

    def _import_fbf_row(
        self,
        db: Session,
        batch: DataImportBatch,
        survey_batch: SurveyBatch,
        row_record: DataImportRow,
        data: dict,
        current_user: User,
        now: datetime,
        context: dict | None = None,
    ) -> tuple[str, str]:
        required = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["fbfbm"], detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
        region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["fbfbm"], current_user)
        tenant_code = data_access_service.derive_tenant_code(region_code)
        issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:fbf:{data['fbfbm']}"))
        if context and "fbf_base_by_source" in context:
            base = context["fbf_base_by_source"].get(data["fbfbm"])
        else:
            base = db.scalar(
                select(SurveyFbfBase).where(
                    SurveyFbfBase.batch_id == survey_batch.id,
                    SurveyFbfBase.source_fbfbm == data["fbfbm"],
                )
            )
        operation = "update" if base else "insert"
        base_before = self._snapshot_model(base) if base else None
        if base is None:
            base = SurveyFbfBase(
                batch_id=survey_batch.id,
                issuer_uid=issuer_uid,
                source_fbfbm=data["fbfbm"],
                initialized_from_key=data["fbfbm"],
                initialized_at=now,
                snapshot_at=now,
            )
            db.add(base)
        base.tenant_code = tenant_code
        base.region_code = region_code
        base.issuer_uid = issuer_uid
        base.source_fbfbm = data["fbfbm"]
        base.fbfbm = data["fbfbm"]
        base.fbfmc = data["fbfmc"]
        base.fbffzrxm = data["fbffzrxm"]
        base.fzrzjlx = data["fzrzjlx"]
        base.fzrzjhm = data["fzrzjhm"]
        base.lxdh = data.get("lxdh")
        base.fbfdz = data["fbfdz"]
        base.yzbm = data["yzbm"]
        base.fbfdcy = data["fbfdcy"]
        base.fbfdcrq = self._parse_datetime(data.get("fbfdcrq")) or datetime.now()
        base.fbfdcjs = data.get("fbfdcjs")
        base.source_import_batch_id = base.source_import_batch_id or batch.id
        base.source_import_row_id = base.source_import_row_id or row_record.id
        base.last_import_batch_id = batch.id
        base.last_import_row_id = row_record.id
        base.initialized_from_table = "import"
        base.initialized_from_key = data["fbfbm"]
        base.snapshot_at = now
        db.flush()
        chunk_no = max(1, (row_record.row_no - 1) // self.chunk_size + 1)
        self._record_operation(db, batch, row_record, base, operation, base_before, chunk_no)

        if context and "fbf_result_by_base_id" in context:
            result = context["fbf_result_by_base_id"].get(base.id)
        else:
            result = db.scalar(select(SurveyFbfResult).where(SurveyFbfResult.base_id == base.id))
        result_before = self._snapshot_model(result) if result else None
        if result is None:
            result = SurveyFbfResult(
                issuer_uid=issuer_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_fbf_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_fbf_result(result, base)
        db.flush()
        self._record_operation(db, batch, row_record, result, "update" if result_before else "insert", result_before, chunk_no)

        if context and "legacy_fbf_by_code" in context:
            legacy = context["legacy_fbf_by_code"].get(data["fbfbm"])
        else:
            legacy = db.get(Fbf, data["fbfbm"])
        legacy_before = self._snapshot_model(legacy) if legacy else None
        if legacy is None:
            legacy = Fbf(fbfbm=data["fbfbm"])
            db.add(legacy)
        legacy.tenant_code = tenant_code
        legacy.region_code = region_code
        legacy.fbfmc = data["fbfmc"]
        legacy.fbffzrxm = data["fbffzrxm"]
        legacy.fzrzjlx = data["fzrzjlx"]
        legacy.fzrzjhm = data["fzrzjhm"]
        legacy.lxdh = data.get("lxdh")
        legacy.fbfdz = data["fbfdz"]
        legacy.yzbm = data["yzbm"]
        legacy.fbfdcy = data["fbfdcy"]
        legacy.fbfdcrq = base.fbfdcrq
        legacy.fbfdcjs = data.get("fbfdcjs")
        db.flush()
        self._record_operation(db, batch, row_record, legacy, "update" if legacy_before else "insert", legacy_before, chunk_no)
        return operation, base.fbfbm

    def _import_cbdkxx_row(
        self,
        db: Session,
        batch: DataImportBatch,
        survey_batch: SurveyBatch,
        row_record: DataImportRow,
        data: dict,
        current_user: User,
        now: datetime,
        context: dict | None = None,
    ) -> tuple[str, str]:
        required = ["dkbm", "fbfbm", "cbfbm", "cbjyqqdfs", "htmj", "cbhtbm", "cbjyqzbm"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
        region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["cbfbm"], current_user)
        tenant_code = data_access_service.derive_tenant_code(region_code)
        parcel_info_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:cbdkxx:{data['dkbm']}:{data['cbfbm']}"))
        parcel_key = (data["dkbm"], data["cbfbm"])
        if context and "cbdkxx_base_by_key" in context:
            base = context["cbdkxx_base_by_key"].get(parcel_key)
        else:
            base = db.scalar(
                select(SurveyCbdkxxBase).where(
                    SurveyCbdkxxBase.batch_id == survey_batch.id,
                    SurveyCbdkxxBase.source_dkbm == data["dkbm"],
                    SurveyCbdkxxBase.cbfbm == data["cbfbm"],
                )
            )
        operation = "update" if base else "insert"
        base_before = self._snapshot_model(base) if base else None
        chunk_no = max(1, (row_record.row_no - 1) // self.chunk_size + 1)
        if base is None:
            base = SurveyCbdkxxBase(
                batch_id=survey_batch.id,
                parcel_info_uid=parcel_info_uid,
                source_dkbm=data["dkbm"],
                initialized_from_key=f"{data['dkbm']}:{data['cbfbm']}",
                initialized_at=now,
                snapshot_at=now,
            )
            db.add(base)
        base.tenant_code = tenant_code
        base.region_code = region_code
        base.parcel_info_uid = parcel_info_uid
        base.source_dkbm = data["dkbm"]
        base.dkbm = data["dkbm"]
        base.fbfbm = data["fbfbm"]
        base.cbfbm = data["cbfbm"]
        base.cbjyqqdfs = data["cbjyqqdfs"]
        base.htmj = self._parse_decimal(data.get("htmj"), required=True)
        base.cbhtbm = data["cbhtbm"]
        base.lzhtbm = data.get("lzhtbm")
        base.cbjyqzbm = data["cbjyqzbm"]
        base.yhtmj = self._parse_decimal(data.get("yhtmj"))
        base.htmjm = self._parse_decimal(data.get("htmjm"))
        base.yhtmjm = self._parse_decimal(data.get("yhtmjm"))
        base.sfqqqg = data.get("sfqqqg")
        base.source_import_batch_id = base.source_import_batch_id or batch.id
        base.source_import_row_id = base.source_import_row_id or row_record.id
        base.last_import_batch_id = batch.id
        base.last_import_row_id = row_record.id
        base.initialized_from_table = "import"
        base.initialized_from_key = f"{data['dkbm']}:{data['cbfbm']}"
        base.snapshot_at = now
        db.flush()
        self._record_operation(db, batch, row_record, base, operation, base_before, chunk_no)

        if context and "cbdkxx_result_by_base_id" in context:
            result = context["cbdkxx_result_by_base_id"].get(base.id)
        else:
            result = db.scalar(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.base_id == base.id))
        result_before = self._snapshot_model(result) if result else None
        if result is None:
            result = SurveyCbdkxxResult(
                parcel_info_uid=parcel_info_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_cbdkxx_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_cbdkxx_result(result, base)
        db.flush()
        self._record_operation(db, batch, row_record, result, "update" if result_before else "insert", result_before, chunk_no)
        return operation, f"{base.dkbm}:{base.cbfbm}"

    def _import_dk_row(
        self,
        db: Session,
        batch: DataImportBatch,
        survey_batch: SurveyBatch,
        row_record: DataImportRow,
        data: dict,
        current_user: User,
        now: datetime,
        geometry: dict | None,
        context: dict | None = None,
    ) -> tuple[str, str]:
        required = ["ysdm", "dkbm", "dkmc", "dklb", "dldj", "tdyt", "sfjbnt", "scmj"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["dkbm"], detail="out of scope")
        region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["dkbm"], current_user)
        tenant_code = data_access_service.derive_tenant_code(region_code)
        parcel_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:dk:{data['dkbm']}"))
        if context and "dk_base_by_source" in context:
            base = context["dk_base_by_source"].get(data["dkbm"])
        else:
            base = db.scalar(
                select(SurveyDkBase).where(
                    SurveyDkBase.batch_id == survey_batch.id,
                    SurveyDkBase.source_dkbm == data["dkbm"],
                )
            )
        operation = "update" if base else "insert"
        base_before = self._snapshot_model(base) if base else None
        chunk_no = max(1, (row_record.row_no - 1) // self.chunk_size + 1)
        if base is None:
            base = SurveyDkBase(
                batch_id=survey_batch.id,
                parcel_uid=parcel_uid,
                source_dkbm=data["dkbm"],
                initialized_from_key=data["dkbm"],
                initialized_at=now,
                snapshot_at=now,
            )
            db.add(base)
        base.tenant_code = tenant_code
        base.region_code = region_code
        base.parcel_uid = parcel_uid
        base.source_dkbm = data["dkbm"]
        base.bsm = self._parse_int(data.get("bsm"), default=0) if data.get("bsm") else None
        base.ysdm = data["ysdm"]
        base.dkbm = data["dkbm"]
        base.dkmc = data["dkmc"]
        base.syqxz = data.get("syqxz")
        base.dklb = data["dklb"]
        base.tdlylx = data.get("tdlylx")
        base.dldj = data["dldj"]
        base.tdyt = data["tdyt"]
        base.sfjbnt = data["sfjbnt"]
        base.scmj = self._parse_decimal(data.get("scmj"), required=True)
        base.dkdz = data.get("dkdz")
        base.dkxz = data.get("dkxz")
        base.dknz = data.get("dknz")
        base.dkbz = data.get("dkbz")
        base.dkbzxx = data.get("dkbzxx")
        base.zjrxm = data.get("zjrxm")
        base.source_import_batch_id = base.source_import_batch_id or batch.id
        base.source_import_row_id = base.source_import_row_id or row_record.id
        base.last_import_batch_id = batch.id
        base.last_import_row_id = row_record.id
        base.initialized_from_table = "import"
        base.initialized_from_key = data["dkbm"]
        base.snapshot_at = now
        db.flush()
        self._write_dk_geometries(db, "survey_dk_base", {base.id: geometry})
        self._record_operation(db, batch, row_record, base, operation, base_before, chunk_no)

        if context and "dk_result_by_base_id" in context:
            result = context["dk_result_by_base_id"].get(base.id)
        else:
            result = db.scalar(select(SurveyDkResult).where(SurveyDkResult.base_id == base.id))
        result_before = self._snapshot_model(result) if result else None
        if result is None:
            result = SurveyDkResult(
                parcel_uid=parcel_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_dk_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_dk_result(result, base)
        db.flush()
        self._copy_dk_result_geometries(db, [base.id])
        self._record_operation(db, batch, row_record, result, "update" if result_before else "insert", result_before, chunk_no)
        return operation, base.dkbm

    def _import_gdb_result_row(
        self,
        db: Session,
        batch: DataImportBatch,
        survey_batch: SurveyBatch,
        row_record: DataImportRow,
        file_type: str,
        data: dict,
        current_user: User,
        now: datetime,
        geometry: dict | None,
        context: dict | None = None,
    ) -> tuple[str, str]:
        chunk_no = max(1, (row_record.row_no - 1) // self.chunk_size + 1)
        if file_type == "cbf":
            required = ["cbfbm", "region_code", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "cbfdcy"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="鎵垮寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
            region_code, _region_name = self._resolve_import_region(db, data, current_user)
            tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
            group_region_code, group_region_name = self._resolve_group_region(db, data, current_user)
            contractor_uid = str(uuid5(NAMESPACE_URL, f"import:{survey_batch.id}:cbf:{data['cbfbm']}"))
            result = db.scalar(
                select(SurveyCbfResult).where(
                    SurveyCbfResult.tenant_code == tenant_code,
                    SurveyCbfResult.cbfbm == data["cbfbm"],
                ).order_by(SurveyCbfResult.id.desc())
            )
            operation = "update" if result else "insert"
            before = self._snapshot_model(result) if result else None
            if result is None:
                result = SurveyCbfResult(
                    tenant_code=tenant_code,
                    region_code=group_region_code or region_code,
                    contractor_uid=contractor_uid,
                    base_id=0,
                    initialized_from_base_id=0,
                    initialized_at=now,
                )
                db.add(result)
            result.tenant_code = tenant_code
            result.region_code = group_region_code or region_code
            result.contractor_uid = contractor_uid
            result.cbfbm = data["cbfbm"]
            result.cbflx = data["cbflx"]
            result.cbfmc = data["cbfmc"]
            result.cbfzjlx = data["cbfzjlx"]
            result.cbfzjhm = data["cbfzjhm"]
            result.cbfdz = data["cbfdz"]
            result.yzbm = data["yzbm"]
            result.lxdh = data.get("lxdh")
            result.cbfcysl = self._parse_int(data.get("cbfcysl"), default=0)
            result.cbfdcrq = self._parse_datetime(data.get("cbfdcrq")) or datetime.now()
            result.cbfdcy = data.get("cbfdcy") or current_user.real_name
            result.cbfdcjs = data.get("cbfdcjs")
            result.gsjs = data.get("gsjs")
            result.gsjsr = data.get("gsjsr")
            result.gsshrq = self._parse_datetime(data.get("gsshrq"))
            result.gsshr = data.get("gsshr")
            result.group_region_code = group_region_code
            result.group_region_name = group_region_name
            result.source_import_batch_id = result.source_import_batch_id or batch.id
            result.source_import_row_id = result.source_import_row_id or row_record.id
            result.last_import_batch_id = batch.id
            result.last_import_row_id = row_record.id
            result.initialized_from_base_id = result.initialized_from_base_id or 0
            db.flush()
            self._record_operation(db, batch, row_record, result, operation, before, chunk_no)
            task = db.scalar(
                select(SurveyContractorTask).where(
                    SurveyContractorTask.tenant_code == tenant_code,
                    SurveyContractorTask.batch_id == survey_batch.id,
                    SurveyContractorTask.cbfbm == data["cbfbm"],
                )
            )
            task_before = self._snapshot_model(task) if task else None
            if task is None:
                task = SurveyContractorTask(
                    tenant_code=tenant_code,
                    region_code=group_region_code or region_code,
                    batch_id=survey_batch.id,
                    contractor_uid=contractor_uid,
                    cbfbm=data["cbfbm"],
                    cbfmc=data["cbfmc"],
                    task_status="not_started",
                )
                db.add(task)
            else:
                task.region_code = group_region_code or region_code
                task.contractor_uid = contractor_uid
                task.cbfmc = data["cbfmc"]
            db.flush()
            self._record_operation(db, batch, row_record, task, "update" if task_before else "insert", task_before, chunk_no)
            return operation, result.cbfbm

        if file_type == "cbf_jtcy":
            required = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
            contractor = db.scalar(
                select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == data["cbfbm"]).order_by(SurveyCbfResult.id.desc())
            )
            if contractor is None:
                raise ValueError(f"contractor not found: {data['cbfbm']}")
            member_uid = str(uuid5(NAMESPACE_URL, f"import:{survey_batch.id}:member:{data['cbfbm']}:{data['cyzjhm']}"))
            result = db.scalar(
                select(SurveyCbfJtcyResult).where(
                    SurveyCbfJtcyResult.tenant_code == contractor.tenant_code,
                    SurveyCbfJtcyResult.cbfbm == data["cbfbm"],
                    SurveyCbfJtcyResult.cyzjhm == data["cyzjhm"],
                )
            )
            operation = "update" if result else "insert"
            before = self._snapshot_model(result) if result else None
            if result is None:
                result = SurveyCbfJtcyResult(
                    tenant_code=contractor.tenant_code,
                    region_code=contractor.region_code,
                    contractor_uid=contractor.contractor_uid,
                    member_uid=member_uid,
                    base_id=None,
                    initialized_from_base_id=None,
                    initialized_at=now,
                )
                db.add(result)
            result.tenant_code = contractor.tenant_code
            result.region_code = contractor.region_code
            result.contractor_uid = contractor.contractor_uid
            result.member_uid = member_uid
            result.cbfbm = data["cbfbm"]
            result.cyxm = data["cyxm"]
            result.cyzjlx = data["cyzjlx"]
            result.cyzjhm = data["cyzjhm"]
            result.cyxb = data["cyxb"]
            result.yhzgx = data["yhzgx"]
            result.cybz = data.get("cybz")
            result.sfgyr = data.get("sfgyr")
            result.cybzsm = data.get("cybzsm")
            result.is_household_head = data["yhzgx"] == "01"
            result.source_import_batch_id = result.source_import_batch_id or batch.id
            result.source_import_row_id = result.source_import_row_id or row_record.id
            result.last_import_batch_id = batch.id
            result.last_import_row_id = row_record.id
            db.flush()
            self._record_operation(db, batch, row_record, result, operation, before, chunk_no)
            return operation, f"{result.cbfbm}:{result.cyzjhm}"

        if file_type == "fbf":
            required = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["fbfbm"], detail="鍙戝寘鏂逛笉鍦ㄥ綋鍓嶆暟鎹潈闄愯寖鍥村唴")
            region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["fbfbm"], current_user)
            tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
            issuer_uid = str(uuid5(NAMESPACE_URL, f"import:{survey_batch.id}:fbf:{data['fbfbm']}"))
            result = db.scalar(
                select(SurveyFbfResult).where(
                    SurveyFbfResult.tenant_code == tenant_code,
                    SurveyFbfResult.fbfbm == data["fbfbm"],
                ).order_by(SurveyFbfResult.id.desc())
            )
            operation = "update" if result else "insert"
            before = self._snapshot_model(result) if result else None
            if result is None:
                result = SurveyFbfResult(
                    tenant_code=tenant_code,
                    region_code=region_code,
                    issuer_uid=issuer_uid,
                    base_id=0,
                    initialized_from_base_id=0,
                    initialized_at=now,
                )
                db.add(result)
            result.tenant_code = tenant_code
            result.region_code = region_code
            result.issuer_uid = issuer_uid
            result.fbfbm = data["fbfbm"]
            result.fbfmc = data["fbfmc"]
            result.fbffzrxm = data["fbffzrxm"]
            result.fzrzjlx = data["fzrzjlx"]
            result.fzrzjhm = data["fzrzjhm"]
            result.lxdh = data.get("lxdh")
            result.fbfdz = data["fbfdz"]
            result.yzbm = data["yzbm"]
            result.fbfdcy = data["fbfdcy"]
            result.fbfdcrq = self._parse_datetime(data.get("fbfdcrq")) or datetime.now()
            result.fbfdcjs = data.get("fbfdcjs")
            result.source_import_batch_id = result.source_import_batch_id or batch.id
            result.source_import_row_id = result.source_import_row_id or row_record.id
            result.last_import_batch_id = batch.id
            result.last_import_row_id = row_record.id
            result.initialized_from_base_id = result.initialized_from_base_id or 0
            db.flush()
            self._record_operation(db, batch, row_record, result, operation, before, chunk_no)
            legacy = db.get(Fbf, data["fbfbm"])
            legacy_before = self._snapshot_model(legacy) if legacy else None
            if legacy is None:
                legacy = Fbf(fbfbm=data["fbfbm"])
                db.add(legacy)
            legacy.tenant_code = tenant_code
            legacy.region_code = region_code
            legacy.fbfmc = data["fbfmc"]
            legacy.fbffzrxm = data["fbffzrxm"]
            legacy.fzrzjlx = data["fzrzjlx"]
            legacy.fzrzjhm = data["fzrzjhm"]
            legacy.lxdh = data.get("lxdh")
            legacy.fbfdz = data["fbfdz"]
            legacy.yzbm = data["yzbm"]
            legacy.fbfdcy = data["fbfdcy"]
            legacy.fbfdcrq = result.fbfdcrq
            legacy.fbfdcjs = data.get("fbfdcjs")
            db.flush()
            self._record_operation(db, batch, row_record, legacy, "update" if legacy_before else "insert", legacy_before, chunk_no)
            return operation, result.fbfbm

        if file_type == "cbdkxx":
            required = ["dkbm", "fbfbm", "cbfbm", "cbjyqqdfs", "htmj", "cbhtbm", "cbjyqzbm"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="out of scope")
            region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["cbfbm"], current_user)
            tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
            parcel_info_uid = str(uuid5(NAMESPACE_URL, f"import:{survey_batch.id}:cbdkxx:{data['dkbm']}:{data['cbfbm']}"))
            result = db.scalar(
                select(SurveyCbdkxxResult).where(
                    SurveyCbdkxxResult.tenant_code == tenant_code,
                    SurveyCbdkxxResult.dkbm == data["dkbm"],
                    SurveyCbdkxxResult.cbfbm == data["cbfbm"],
                ).order_by(SurveyCbdkxxResult.id.desc())
            )
            operation = "update" if result else "insert"
            before = self._snapshot_model(result) if result else None
            if result is None:
                result = SurveyCbdkxxResult(
                    tenant_code=tenant_code,
                    region_code=region_code,
                    parcel_info_uid=parcel_info_uid,
                    base_id=0,
                    initialized_from_base_id=0,
                    initialized_at=now,
                )
                db.add(result)
            result.tenant_code = tenant_code
            result.region_code = region_code
            result.parcel_info_uid = parcel_info_uid
            result.dkbm = data["dkbm"]
            result.fbfbm = data["fbfbm"]
            result.cbfbm = data["cbfbm"]
            result.cbjyqqdfs = data["cbjyqqdfs"]
            result.htmj = self._parse_decimal(data.get("htmj"), required=True)
            result.cbhtbm = data["cbhtbm"]
            result.lzhtbm = data.get("lzhtbm")
            result.cbjyqzbm = data["cbjyqzbm"]
            result.yhtmj = self._parse_decimal(data.get("yhtmj"))
            result.htmjm = self._parse_decimal(data.get("htmjm"))
            result.yhtmjm = self._parse_decimal(data.get("yhtmjm"))
            result.sfqqqg = data.get("sfqqqg")
            result.source_import_batch_id = result.source_import_batch_id or batch.id
            result.source_import_row_id = result.source_import_row_id or row_record.id
            result.last_import_batch_id = batch.id
            result.last_import_row_id = row_record.id
            result.initialized_from_base_id = result.initialized_from_base_id or 0
            db.flush()
            self._record_operation(db, batch, row_record, result, operation, before, chunk_no)
            return operation, f"{result.dkbm}:{result.cbfbm}"

        if file_type == "dk":
            required = ["ysdm", "dkbm", "dkmc", "dklb", "dldj", "tdyt", "sfjbnt", "scmj"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["dkbm"], detail="out of scope")
            region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["dkbm"], current_user)
            tenant_code = data_access_service.get_tenant_code(current_user) or data_access_service.derive_tenant_code(region_code)
            parcel_uid = str(uuid5(NAMESPACE_URL, f"import:{survey_batch.id}:dk:{data['dkbm']}"))
            result = db.scalar(
                select(SurveyDkResult).where(
                    SurveyDkResult.tenant_code == tenant_code,
                    SurveyDkResult.dkbm == data["dkbm"],
                ).order_by(SurveyDkResult.id.desc())
            )
            operation = "update" if result else "insert"
            before = self._snapshot_model(result) if result else None
            if result is None:
                result = SurveyDkResult(
                    tenant_code=tenant_code,
                    region_code=region_code,
                    parcel_uid=parcel_uid,
                    base_id=0,
                    initialized_from_base_id=0,
                    initialized_at=now,
                )
                db.add(result)
            result.tenant_code = tenant_code
            result.region_code = region_code
            result.parcel_uid = parcel_uid
            result.bsm = self._parse_int(data.get("bsm"), default=0) if data.get("bsm") else None
            result.ysdm = data["ysdm"]
            result.dkbm = data["dkbm"]
            result.dkmc = data["dkmc"]
            result.syqxz = data.get("syqxz")
            result.dklb = data["dklb"]
            result.tdlylx = data.get("tdlylx")
            result.dldj = data["dldj"]
            result.tdyt = data["tdyt"]
            result.sfjbnt = data["sfjbnt"]
            result.scmj = self._parse_decimal(data.get("scmj"), required=True)
            result.dkdz = data.get("dkdz")
            result.dkxz = data.get("dkxz")
            result.dknz = data.get("dknz")
            result.dkbz = data.get("dkbz")
            result.dkbzxx = data.get("dkbzxx")
            result.zjrxm = data.get("zjrxm")
            result.source_import_batch_id = result.source_import_batch_id or batch.id
            result.source_import_row_id = result.source_import_row_id or row_record.id
            result.last_import_batch_id = batch.id
            result.last_import_row_id = row_record.id
            result.initialized_from_base_id = result.initialized_from_base_id or 0
            db.flush()
            self._write_dk_geometries(db, "survey_dk_result", {result.id: geometry})
            self._record_operation(db, batch, row_record, result, operation, before, chunk_no)
            return operation, result.dkbm

        raise ValueError(f"unsupported data type: {file_type}")

    def _write_dk_geometries(self, db: Session, table_name: str, geometries_by_id: dict[int, dict | None]) -> None:
        if not geometries_by_id:
            return
        stmt = text(
            f"""
            UPDATE {table_name}
            SET geom = CASE
                WHEN :geojson IS NULL THEN NULL
                ELSE ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4527))
            END
            WHERE id = :row_id
            """
        )
        for row_id, geometry in geometries_by_id.items():
            db.execute(
                stmt,
                {
                    "row_id": row_id,
                    "geojson": json.dumps(geometry, ensure_ascii=False) if geometry else None,
                },
            )

    def _copy_dk_result_geometries(self, db: Session, base_ids: list[int]) -> None:
        if not base_ids:
            return
        db.execute(
            text(
                """
                UPDATE survey_dk_result AS result
                SET geom = base.geom
                FROM survey_dk_base AS base
                WHERE result.base_id = base.id
                  AND base.id = ANY(:base_ids)
                """
            ),
            {"base_ids": base_ids},
        )

    def _recount_member_counts(self, db: Session, contractor_codes: set[str], survey_batch_id: int | None = None) -> None:
        if not contractor_codes:
            return
        code_list = list(contractor_codes)
        if survey_batch_id is None:
            batch_ids = set()
            for code_chunk in self._chunks(code_list, self.chunk_size):
                batch_ids.update(
                    db.scalars(
                        select(SurveyCbfBase.batch_id).where(SurveyCbfBase.source_cbfbm.in_(code_chunk)).distinct()
                    ).all()
                )
        else:
            batch_ids = [survey_batch_id]
        for batch_id in batch_ids:
            for code_chunk in self._chunks(code_list, self.chunk_size):
                contractors = db.scalars(
                    select(SurveyCbfBase).where(
                        SurveyCbfBase.batch_id == batch_id,
                        SurveyCbfBase.source_cbfbm.in_(code_chunk),
                    )
                ).all()
                if not contractors:
                    continue
                counts = dict(
                    db.execute(
                        select(SurveyCbfJtcyBase.base_contractor_code, func.count(SurveyCbfJtcyBase.id))
                        .where(
                            SurveyCbfJtcyBase.batch_id == batch_id,
                            SurveyCbfJtcyBase.base_contractor_code.in_(code_chunk),
                        )
                        .group_by(SurveyCbfJtcyBase.base_contractor_code)
                    ).all()
                )
                results = {}
                contractor_ids = [contractor.id for contractor in contractors]
                for id_chunk in self._chunks(contractor_ids, self.chunk_size):
                    results.update(
                        {
                            result.base_id: result
                            for result in db.scalars(
                                select(SurveyCbfResult).where(
                                    SurveyCbfResult.base_id.in_(id_chunk),
                                )
                            ).all()
                        }
                    )
                for contractor in contractors:
                    count = counts.get(contractor.source_cbfbm, 0)
                    contractor.cbfcysl = count
                    result = results.get(contractor.id)
                    if result is None:
                        continue
                    if not result.is_changed and result.survey_status == "not_surveyed":
                        result.cbfcysl = count

    def _recount_result_member_counts(self, db: Session, contractor_codes: set[str], survey_batch_id: int) -> None:
        if not contractor_codes:
            return
        for code_chunk in self._chunks(list(contractor_codes), self.chunk_size):
            counts = dict(
                db.execute(
                    select(SurveyCbfJtcyResult.cbfbm, func.count(SurveyCbfJtcyResult.id))
                    .where(
                        SurveyCbfJtcyResult.cbfbm.in_(code_chunk),
                    )
                    .group_by(SurveyCbfJtcyResult.cbfbm)
                ).all()
            )
            contractors = db.scalars(
                select(SurveyCbfResult).where(
                    SurveyCbfResult.cbfbm.in_(code_chunk),
                ).order_by(SurveyCbfResult.cbfbm.asc(), SurveyCbfResult.id.desc())
            ).all()
            for contractor in contractors:
                if not contractor.is_changed and contractor.survey_status == "not_surveyed":
                    contractor.cbfcysl = counts.get(contractor.cbfbm, 0)

    def _unused_legacy_recount_member_counts(self, db: Session, contractor_codes: set[str]) -> None:
        for code in contractor_codes:
            pass

    def _ensure_import_survey_batch(self, db: Session, batch: DataImportBatch, current_user: User, now: datetime) -> SurveyBatch:
        if batch.linked_survey_batch_id:
            survey_batch = db.get(SurveyBatch, batch.linked_survey_batch_id)
            if survey_batch is not None:
                return survey_batch

        survey_batch = SurveyBatch(
            batch_no=self._next_no(db, "SUR", SurveyBatch.id),
            batch_name=f"{batch.import_name} 璋冩煡鎴愭灉",
            region_code=batch.region_code,
            region_name=batch.region_name,
            survey_type="import_survey",
            status="active",
            started_at=now,
            created_by=current_user.id,
            remark=f"鐢卞鍏ユ壒娆?{batch.import_no} 鑷姩鐢熸垚",
        )
        db.add(survey_batch)
        db.flush()
        batch.linked_survey_batch_id = survey_batch.id
        return survey_batch

    def _copy_base_to_contractor_result(self, result: SurveyCbfResult, base: SurveyCbfBase) -> None:
        result.region_code = base.region_code
        result.tenant_code = base.tenant_code
        result.contractor_uid = base.contractor_uid
        result.base_id = base.id
        result.cbfbm = base.cbfbm
        result.cbflx = base.cbflx
        result.cbfmc = base.cbfmc
        result.cbfzjlx = base.cbfzjlx
        result.cbfzjhm = base.cbfzjhm
        result.cbfdz = base.cbfdz
        result.yzbm = base.yzbm
        result.lxdh = base.lxdh
        result.cbfcysl = base.cbfcysl
        result.cbfdcrq = base.cbfdcrq
        result.cbfdcy = base.cbfdcy
        result.cbfdcjs = base.cbfdcjs
        result.gsjs = base.gsjs
        result.gsjsr = base.gsjsr
        result.gsshrq = base.gsshrq
        result.gsshr = base.gsshr
        result.group_region_code = base.group_region_code
        result.group_region_name = base.group_region_name
        result.source_import_batch_id = base.source_import_batch_id
        result.source_import_row_id = base.source_import_row_id
        result.last_import_batch_id = base.last_import_batch_id
        result.last_import_row_id = base.last_import_row_id
        result.initialized_from_base_id = base.id

    def _copy_base_to_member_result(self, result: SurveyCbfJtcyResult, base: SurveyCbfJtcyBase) -> None:
        result.region_code = base.region_code
        result.tenant_code = base.tenant_code
        result.contractor_uid = base.contractor_uid
        result.member_uid = base.member_uid
        result.base_id = base.id
        result.cbfbm = base.cbfbm
        result.cyxm = base.cyxm
        result.cyzjlx = base.cyzjlx
        result.cyzjhm = base.cyzjhm
        result.cyxb = base.cyxb
        result.yhzgx = base.yhzgx
        result.cybz = base.cybz
        result.sfgyr = base.sfgyr
        result.cybzsm = base.cybzsm
        result.is_household_head = base.yhzgx == "01"
        result.source_import_batch_id = base.source_import_batch_id
        result.source_import_row_id = base.source_import_row_id
        result.last_import_batch_id = base.last_import_batch_id
        result.last_import_row_id = base.last_import_row_id
        result.initialized_from_base_id = base.id

    def _copy_base_to_fbf_result(self, result: SurveyFbfResult, base: SurveyFbfBase) -> None:
        result.region_code = base.region_code
        result.tenant_code = base.tenant_code
        result.issuer_uid = base.issuer_uid
        result.base_id = base.id
        result.fbfbm = base.fbfbm
        result.fbfmc = base.fbfmc
        result.fbffzrxm = base.fbffzrxm
        result.fzrzjlx = base.fzrzjlx
        result.fzrzjhm = base.fzrzjhm
        result.lxdh = base.lxdh
        result.fbfdz = base.fbfdz
        result.yzbm = base.yzbm
        result.fbfdcy = base.fbfdcy
        result.fbfdcrq = base.fbfdcrq
        result.fbfdcjs = base.fbfdcjs
        result.source_import_batch_id = base.source_import_batch_id
        result.source_import_row_id = base.source_import_row_id
        result.last_import_batch_id = base.last_import_batch_id
        result.last_import_row_id = base.last_import_row_id
        result.initialized_from_base_id = base.id

    def _copy_base_to_cbdkxx_result(self, result: SurveyCbdkxxResult, base: SurveyCbdkxxBase) -> None:
        result.region_code = base.region_code
        result.tenant_code = base.tenant_code
        result.parcel_info_uid = base.parcel_info_uid
        result.base_id = base.id
        result.dkbm = base.dkbm
        result.fbfbm = base.fbfbm
        result.cbfbm = base.cbfbm
        result.cbjyqqdfs = base.cbjyqqdfs
        result.htmj = base.htmj
        result.cbhtbm = base.cbhtbm
        result.lzhtbm = base.lzhtbm
        result.cbjyqzbm = base.cbjyqzbm
        result.yhtmj = base.yhtmj
        result.htmjm = base.htmjm
        result.yhtmjm = base.yhtmjm
        result.sfqqqg = base.sfqqqg
        result.source_import_batch_id = base.source_import_batch_id
        result.source_import_row_id = base.source_import_row_id
        result.last_import_batch_id = base.last_import_batch_id
        result.last_import_row_id = base.last_import_row_id
        result.initialized_from_base_id = base.id

    def _copy_base_to_dk_result(self, result: SurveyDkResult, base: SurveyDkBase) -> None:
        result.region_code = base.region_code
        result.tenant_code = base.tenant_code
        result.parcel_uid = base.parcel_uid
        result.base_id = base.id
        result.bsm = base.bsm
        result.ysdm = base.ysdm
        result.dkbm = base.dkbm
        result.dkmc = base.dkmc
        result.syqxz = base.syqxz
        result.dklb = base.dklb
        result.tdlylx = base.tdlylx
        result.dldj = base.dldj
        result.tdyt = base.tdyt
        result.sfjbnt = base.sfjbnt
        result.scmj = base.scmj
        result.dkdz = base.dkdz
        result.dkxz = base.dkxz
        result.dknz = base.dknz
        result.dkbz = base.dkbz
        result.dkbzxx = base.dkbzxx
        result.zjrxm = base.zjrxm
        result.source_import_batch_id = base.source_import_batch_id
        result.source_import_row_id = base.source_import_row_id
        result.last_import_batch_id = base.last_import_batch_id
        result.last_import_row_id = base.last_import_row_id
        result.initialized_from_base_id = base.id

    def _normalize_row(self, row: dict, field_map: dict[str, list[str]]) -> dict:
        chinese_aliases = {
            "cbfbm": ["承包方代码"],
            "region_code": ["区域代码"],
            "region_name": ["区域名称"],
            "cbflx": ["承包方类型"],
            "cbfmc": ["承包方名称", "承包方(代表)名称"],
            "cbfzjlx": ["证件类型", "承包方(代表)证件类型"],
            "cbfzjhm": ["证件号码", "承包方(代表)证件号码"],
            "cbfdz": ["承包方地址"],
            "yzbm": ["邮政编码"],
            "lxdh": ["联系电话"],
            "cbfcysl": ["承包方成员数量", "家庭成员数"],
            "cbfdcrq": ["承包方调查日期"],
            "cbfdcy": ["承包方调查员"],
            "cbfdcjs": ["承包方调查记事"],
            "gsjs": ["公示记事"],
            "gsjsr": ["公示记事人"],
            "gsshrq": ["公示审核日期"],
            "gsshr": ["公示审核人"],
            "group_region_code": ["所属组代码"],
            "group_region_name": ["所属组名称"],
            "cyxm": ["成员姓名", "姓名"],
            "cyzjlx": ["证件类型"],
            "cyzjhm": ["证件号码", "身份证号"],
            "cyxb": ["性别"],
            "yhzgx": ["与户主关系"],
            "cybz": ["成员备注代码", "备注代码"],
            "sfgyr": ["是否共有人"],
            "cybzsm": ["成员备注说明", "备注说明"],
        }
        row_lookup = {str(key).strip().lower(): value for key, value in row.items()}
        normalized = {}
        for target, candidates in field_map.items():
            value = None
            for key in [*candidates, *chinese_aliases.get(target, [])]:
                if key in row and row[key] not in (None, ""):
                    value = row[key]
                    break
                lookup_value = row_lookup.get(str(key).strip().lower())
                if lookup_value not in (None, ""):
                    value = lookup_value
                    break
            normalized[target] = str(value).strip() if value is not None else None
        return normalized

    def _entity_key(self, file_type: str, data: dict) -> str | None:
        if file_type == "cbf":
            return data.get("cbfbm")
        if file_type == "cbf_jtcy" and data.get("cbfbm") and data.get("cyzjhm"):
            return f"{data['cbfbm']}:{data['cyzjhm']}"
        if file_type == "fbf":
            return data.get("fbfbm")
        if file_type == "cbdkxx" and data.get("dkbm") and data.get("cbfbm"):
            return f"{data['dkbm']}:{data['cbfbm']}"
        if file_type == "dk":
            return data.get("dkbm")
        return None

    def _ensure_required(self, data: dict, fields: list[str]) -> None:
        missing = [field for field in fields if not data.get(field)]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")

    def _field_map_for(self, file_type: str) -> dict[str, list[str]]:
        if file_type == "cbf":
            return self.cbf_field_map
        if file_type == "cbf_jtcy":
            return self.member_field_map
        if file_type == "fbf":
            return self.fbf_field_map
        if file_type == "cbdkxx":
            return self.cbdkxx_field_map
        if file_type == "dk":
            return self.dk_field_map
        raise ValueError(f"unsupported data type: {file_type}")

    def _normalize_layer_name(self, value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum() or ch == "_")

    def _infer_gdb_layer_type(self, layer_name: str) -> str | None:
        normalized_name = self._normalize_layer_name(layer_name)
        for file_type, aliases in self.gdb_layer_aliases.items():
            if normalized_name in aliases:
                return file_type
        for file_type in sorted(self.gdb_layer_order, key=len, reverse=True):
            if normalized_name.startswith(file_type):
                return file_type
        return None

    def _json_safe(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_safe(item) for item in value]
        if hasattr(value, "__geo_interface__"):
            return self._json_safe(value.__geo_interface__)
        try:
            return self._json_safe(dict(value))
        except (TypeError, ValueError):
            return str(value)

    def _apply_gdb_region_defaults(self, batch: DataImportBatch, data: dict) -> None:
        if data.get("region_code"):
            return
        for key in ("cbfbm", "fbfbm", "dkbm"):
            if data.get(key):
                data["region_code"] = batch.region_code or data[key][:14]
                return
        data["region_code"] = batch.region_code

    def _resolve_code_region(self, value: str | None, current_user: User) -> str:
        normalized = data_access_service.normalize_region_code(value)
        if not normalized:
            raise ValueError("缂哄皯瀵煎叆鍖哄煙")
        data_access_service.ensure_region_in_scope(current_user, normalized, detail="region out of scope")
        return normalized

    def _decode_csv(self, content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="鏃犳硶璇嗗埆 CSV 鏂囦欢缂栫爜")

    def _infer_archive_csv_type(self, filename: str) -> str | None:
        name = filename.replace("\\", "/").lower()
        if any(token in name for token in ("cbf_jtcy", "jtcy", "member", "成员")):
            return "cbf_jtcy"
        if any(token in name for token in ("cbf", "contractor", "承包方")):
            return "cbf"
        return None

    def _parse_int(self, value: str | None, default: int = 0) -> int:
        if value in (None, ""):
            return default
        return int(float(str(value)))

    def _parse_decimal(self, value: str | None, required: bool = False) -> Decimal | None:
        if value in (None, ""):
            if required:
                raise ValueError("missing required numeric field")
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"invalid decimal value: {value}") from exc

    def _snapshot_model(self, instance) -> dict:
        mapper = sa_inspect(instance).mapper
        return {
            column.key: self._json_safe(getattr(instance, column.key))
            for column in mapper.column_attrs
        }

    def _primary_key_snapshot(self, instance) -> dict:
        mapper = sa_inspect(instance).mapper
        return {
            column.key: self._json_safe(getattr(instance, column.key))
            for column in mapper.primary_key
        }

    def _record_operation(
        self,
        db: Session,
        batch: DataImportBatch,
        row_record: DataImportRow,
        instance,
        operation_type: str,
        before_snapshot: dict | None,
        chunk_no: int,
    ) -> None:
        if operation_type != "update" or before_snapshot is None:
            return
        db.add(
            DataImportOperation(
                tenant_code=batch.tenant_code,
                region_code=batch.region_code,
                import_batch_id=batch.id,
                import_file_id=row_record.import_file_id,
                import_row_id=row_record.id,
                chunk_no=chunk_no,
                table_name=instance.__tablename__,
                primary_key=self._primary_key_snapshot(instance),
                operation_type=operation_type,
                before_snapshot=before_snapshot,
                after_snapshot=self._snapshot_model(instance),
            )
        )

    def _rollback_model_map(self) -> dict[str, type]:
        models = [
            Fbf,
            SurveyContractorTask,
            SurveyCbfBase,
            SurveyCbfResult,
            SurveyCbfJtcyBase,
            SurveyCbfJtcyResult,
            SurveyFbfBase,
            SurveyFbfResult,
            SurveyCbdkxxBase,
            SurveyCbdkxxResult,
            SurveyDkBase,
            SurveyDkResult,
        ]
        return {model.__tablename__: model for model in models}

    def _get_by_primary_key(self, db: Session, model, primary_key: dict):
        mapper = sa_inspect(model).mapper
        values = []
        for column in mapper.primary_key:
            if column.key not in primary_key:
                return None
            values.append(self._restore_value(column, primary_key[column.key]))
        return db.get(model, values[0] if len(values) == 1 else tuple(values))

    def _restore_snapshot(self, instance, snapshot: dict) -> None:
        mapper = sa_inspect(instance).mapper
        columns = {column.key: column for column in mapper.column_attrs}
        for key, value in snapshot.items():
            column = columns.get(key)
            if column is None:
                continue
            setattr(instance, key, self._restore_value(column, value))

    def _restore_value(self, column_attr, value):
        if value is None:
            return None
        column_type = column_attr.columns[0].type
        if isinstance(column_type, SAInteger):
            return int(value)
        if isinstance(column_type, SANumeric):
            return Decimal(str(value))
        if isinstance(column_type, SADateTime):
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if isinstance(column_type, SADate):
            return date.fromisoformat(str(value))
        return value

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.combine(datetime.strptime(text, fmt).date(), datetime.min.time())
            except ValueError:
                pass
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            return datetime.combine(date.fromisoformat(text), datetime.min.time())

    def _resolve_group_region(self, db: Session, data: dict, current_user: User) -> tuple[str | None, str | None]:
        code = (data.get("group_region_code") or "").strip()
        if not code:
            return None, None
        data_access_service.ensure_region_in_scope(current_user, code, detail="region out of scope")
        region = db.scalar(select(Region).where(Region.code == code).execution_options(skip_tenant_scope=True))
        name = region.full_name if region else (data.get("group_region_name") or "")
        return code, name.strip() or None

    def _resolve_import_region(self, db: Session, data: dict, current_user: User) -> tuple[str, str | None]:
        code = (data.get("region_code") or "").strip()
        if not code:
            raise ValueError("缂哄皯蹇呭～瀛楁锛歳egion_code")
        normalized = data_access_service.normalize_region_code(code)
        if not normalized or len(normalized) < 6:
            raise ValueError("invalid region code")
        data_access_service.ensure_region_in_scope(current_user, normalized, detail="region out of scope")
        region = db.scalar(select(Region).where(Region.code == normalized).execution_options(skip_tenant_scope=True))
        name = region.full_name if region else (data.get("region_name") or "")
        return normalized, name.strip() or None

    def _next_no(self, db: Session, prefix: str, id_column) -> str:
        next_id = (db.scalar(select(func.max(id_column))) or 0) + 1
        return f"{prefix}{datetime.now():%Y%m%d}{next_id:04d}"

    def _serialize_batch(self, item: DataImportBatch) -> dict:
        return {
            "id": item.id,
            "importNo": item.import_no,
            "importName": item.import_name,
            "importType": item.import_type,
            "sourceType": item.source_type,
            "sourceName": item.source_name,
            "sourceOrg": item.source_org,
            "regionCode": item.region_code,
            "regionName": item.region_name,
            "status": item.status,
            "totalCount": item.total_count,
            "successCount": item.success_count,
            "failedCount": item.failed_count,
            "warningCount": item.warning_count,
            "linkedSurveyBatchId": item.linked_survey_batch_id,
            "importedByName": item.imported_by_name,
            "importedAt": item.imported_at,
            "remark": item.remark,
            "createdAt": item.created_at,
        }

    def _serialize_row(self, item: DataImportRow) -> dict:
        return {
            "id": item.id,
            "rowNo": item.row_no,
            "entityType": item.entity_type,
            "entityKey": item.entity_key,
            "operationType": item.operation_type,
            "status": item.status,
            "targetTable": item.target_table,
            "targetId": item.target_id,
            "errorMessage": item.error_message,
            "warningMessage": item.warning_message,
            "rawData": item.raw_data,
            "normalizedData": item.normalized_data,
            "createdAt": item.created_at,
        }


data_import_service = DataImportService()
