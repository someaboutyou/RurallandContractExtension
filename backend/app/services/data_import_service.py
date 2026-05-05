import csv
import hashlib
import io
import json
import tempfile
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.data_import import DataImportBatch, DataImportFile, DataImportRow
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


class DataImportService:
    cbf_field_map = {
        "cbfbm": ["cbfbm", "承包方代码", "code"],
        "region_code": ["region_code", "区域代码", "regionCode"],
        "region_name": ["region_name", "区域名称", "regionName"],
        "cbflx": ["cbflx", "承包方类型", "typeCode"],
        "cbfmc": ["cbfmc", "承包方名称", "承包方(代表)名称", "name"],
        "cbfzjlx": ["cbfzjlx", "证件类型", "承包方(代表)证件类型", "idType"],
        "cbfzjhm": ["cbfzjhm", "证件号码", "承包方(代表)证件号码", "idNo"],
        "cbfdz": ["cbfdz", "承包方地址", "address"],
        "yzbm": ["yzbm", "邮政编码", "postcode"],
        "lxdh": ["lxdh", "联系电话", "mobile"],
        "cbfcysl": ["cbfcysl", "承包方成员数量", "家庭成员数", "memberCount"],
        "cbfdcrq": ["cbfdcrq", "承包方调查日期", "surveyDate"],
        "cbfdcy": ["cbfdcy", "承包方调查员", "surveyorName"],
        "cbfdcjs": ["cbfdcjs", "承包方调查记事", "surveyNote"],
        "gsjs": ["gsjs", "公示记事", "publicNoticeNote"],
        "gsjsr": ["gsjsr", "公示记事人", "publicNoticeRecorder"],
        "gsshrq": ["gsshrq", "公示审核日期", "publicNoticeReviewDate"],
        "gsshr": ["gsshr", "公示审核人", "publicNoticeReviewer"],
        "group_region_code": ["group_region_code", "所属组代码", "groupRegionCode"],
        "group_region_name": ["group_region_name", "所属组名称", "groupRegionName"],
    }
    member_field_map = {
        "cbfbm": ["cbfbm", "承包方代码", "contractorCode"],
        "cyxm": ["cyxm", "成员姓名", "姓名", "name"],
        "cyzjlx": ["cyzjlx", "证件类型", "idType"],
        "cyzjhm": ["cyzjhm", "证件号码", "身份证号", "idNo"],
        "cyxb": ["cyxb", "性别", "gender"],
        "yhzgx": ["yhzgx", "与户主关系", "relationToHead"],
        "cybz": ["cybz", "成员备注代码", "备注代码", "noteCode"],
        "sfgyr": ["sfgyr", "是否共有人", "isCoOwner"],
        "cybzsm": ["cybzsm", "成员备注说明", "备注说明", "note"],
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
            "承包方代码",
            "区域代码",
            "区域名称",
            "承包方类型",
            "承包方名称",
            "证件类型",
            "证件号码",
            "承包方地址",
            "邮政编码",
            "联系电话",
            "家庭成员数",
            "承包方调查日期",
            "承包方调查员",
            "承包方调查记事",
            "公示记事",
            "公示记事人",
            "公示审核日期",
            "公示审核人",
            "所属组代码",
            "所属组名称",
        ],
        "cbf_jtcy": ["承包方代码", "成员姓名", "证件类型", "证件号码", "性别", "与户主关系", "成员备注代码", "是否共有人", "成员备注说明"],
    }
    template_field_notes = {
        "cbf": [
            ("承包方代码", "必填，18位承包方代码"),
            ("区域代码", "必填，填写本条承包方实际所属村/组等区域代码，导入到 survey 表的 region_code 使用该值"),
            ("区域名称", "选填，区域代码存在于区域表时会按代码取区域全称"),
            ("承包方类型", "必填，1=农户，2=个人，3=单位"),
            ("承包方名称", "必填，农户填写户主或代表名称"),
            ("证件类型", "必填，1=居民身份证，4=户口簿，9=其他"),
            ("证件号码", "必填"),
            ("承包方地址", "必填"),
            ("邮政编码", "必填，6位"),
            ("联系电话", "选填"),
            ("家庭成员数", "选填，导入成员后会自动回算"),
            ("承包方调查日期", "选填，格式 YYYY-MM-DD"),
            ("承包方调查员", "必填"),
            ("承包方调查记事", "选填"),
            ("公示记事", "选填"),
            ("公示记事人", "选填"),
            ("公示审核日期", "选填，格式 YYYY-MM-DD"),
            ("公示审核人", "选填"),
            ("所属组代码", "选填，必须在当前调查员可操作的区域权限范围内"),
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 cbf 或 cbf_jtcy 数据类型")
        batch = db.get(DataImportBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")

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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入批次不存在")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")

        filename = upload_file.filename or "import.zip"
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传 ZIP 压缩包")

        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法读取 ZIP 压缩包") from exc

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
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"压缩包内存在多个 {inferred_type} CSV 文件")
            csv_files[inferred_type] = (inner_name, archive.read(item))

        missing = [label for key, label in (("cbf", "承包方"), ("cbf_jtcy", "家庭成员")) if key not in csv_files]
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"压缩包缺少{','.join(missing)} CSV 文件")

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
            remark="承包方与家庭成员合并上传压缩包",
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
                remark=f"来自压缩包：{filename}",
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="导入 GDB 前请先选择导入区域")

        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传文件为空")

        filename = upload_file.filename or "import_gdb.zip"
        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传包含 .gdb 目录的 ZIP 压缩包")

        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法读取 ZIP 压缩包") from exc

        now = datetime.now(timezone.utc)
        batch.source_type = "gdb"
        archive_file = DataImportFile(
            import_batch_id=batch.id,
            file_type="gdb_archive",
            original_name=filename,
            content_type=upload_file.content_type,
            file_size=len(content),
            file_hash=hashlib.sha256(content).hexdigest(),
            parse_status="success",
            row_count=0,
            uploaded_by=current_user.id,
            uploaded_at=now,
            remark="GDB 全量导入压缩包",
        )
        db.add(archive_file)
        db.flush()

        with tempfile.TemporaryDirectory(prefix="rural_gdb_") as temp_dir:
            self._extract_zip_safely(archive, temp_dir)
            gdb_path = self._find_gdb_path(temp_dir)
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
        return self._serialize_batch(batch)

    def _extract_zip_safely(self, archive: zipfile.ZipFile, target_dir: str) -> None:
        for item in archive.infolist():
            if "\\" in item.filename:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP 压缩包包含非法路径")
            item_path = PurePosixPath(item.filename)
            if item_path.is_absolute() or ".." in item_path.parts:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP 压缩包包含非法路径")
        archive.extractall(target_dir)

    def _find_gdb_path(self, root_dir: str) -> str:
        from pathlib import Path

        for path in Path(root_dir).rglob("*.gdb"):
            if path.is_dir():
                return str(path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP 压缩包中未找到 .gdb 目录")

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
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="后端缺少 Fiona/GDAL，无法读取 GDB") from exc

        try:
            available_layers = list(fiona.listlayers(gdb_path))
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无法读取 GDB 图层：{exc}") from exc

        layer_map: dict[str, str] = {}
        for layer_name in available_layers:
            file_type = self._infer_gdb_layer_type(layer_name)
            if file_type and file_type not in layer_map:
                layer_map[file_type] = layer_name

        stats_list = []
        for file_type in self.gdb_layer_order:
            layer_name = layer_map.get(file_type)
            if not layer_name:
                continue
            stats_list.append(self._process_gdb_layer(db, batch, gdb_path, layer_name, file_type, current_user, now, fiona))

        if not stats_list:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GDB 中未识别到 FBF、CBF、CBF_JTCY、CBDKXX 或 DK 图层")
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
            remark=f"来自 GDB 图层：{layer_name}",
        )
        db.add(import_file)
        db.flush()

        success_count = 0
        failed_count = 0
        warning_count = 0
        seen_keys: set[str] = set()
        affected_contractors: set[str] = set()
        with fiona_module.open(gdb_path, layer=layer_name) as source:
            row_count = len(source)
            for index, feature in enumerate(source, start=1):
                raw = self._json_safe(dict(feature.get("properties") or {}))
                normalized = self._normalize_row(raw, field_map)
                self._apply_gdb_region_defaults(batch, normalized)
                entity_key = self._entity_key(file_type, normalized)
                row_record = DataImportRow(
                    import_batch_id=batch.id,
                    import_file_id=import_file.id,
                    row_no=index,
                    entity_type=file_type,
                    entity_key=entity_key,
                    operation_type="insert",
                    status="pending",
                    target_table=f"survey_{file_type}_base" if file_type not in {"cbf", "cbf_jtcy"} else file_type,
                    raw_data=raw,
                    normalized_data=normalized,
                )
                db.add(row_record)
                db.flush()
                try:
                    if not entity_key:
                        raise ValueError("无法识别业务主键")
                    if entity_key in seen_keys:
                        raise ValueError(f"同一图层内业务主键重复：{entity_key}")
                    seen_keys.add(entity_key)
                    geometry = self._json_safe(feature.get("geometry"))
                    operation, target_id = self._import_row(db, batch, import_file, row_record, file_type, normalized, current_user, now, geometry)
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
                    failed_count += 1

        if file_type == "cbf_jtcy":
            self._recount_member_counts(db, affected_contractors)
        import_file.row_count = row_count
        import_file.error_count = failed_count
        import_file.parse_status = "success" if failed_count == 0 else ("partial_success" if success_count else "failed")
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
            db.add(row_record)
            db.flush()
            try:
                if not entity_key:
                    raise ValueError("无法识别业务主键")
                if entity_key in seen_keys:
                    raise ValueError(f"同一文件内业务主键重复：{entity_key}")
                seen_keys.add(entity_key)
                operation, target_id = self._import_row(db, batch, import_file, row_record, file_type, normalized, current_user, now)
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 cbf 或 cbf_jtcy 模板")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(self.template_headers[file_type])
        if file_type == "cbf":
            writer.writerow(
                [
                    "320623100200000001",
                    "320623100200",
                    "某镇某村",
                    "1",
                    "张三户",
                    "1",
                    "320623199001010011",
                    "某村一组",
                    "226400",
                    "13900000000",
                    "3",
                    "2026-05-01",
                    "调查员A",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "32062310020001",
                    "某村一组",
                ]
            )
        else:
            writer.writerow(["320623100200000001", "张三", "1", "320623199001010011", "1", "01", "", "1", "户主"])
        return f"{file_type}_template.csv", output.getvalue().encode("utf-8-sig")

    def build_template_notes_csv(self, file_type: str) -> tuple[str, bytes]:
        if file_type not in self.template_field_notes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 cbf 或 cbf_jtcy 字段说明")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["字段名称", "填写说明"])
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
        writer.writerow(["行号", "数据类型", "业务键", "错误信息", "原始数据"])
        for row in rows:
            writer.writerow([row.row_no, row.entity_type, row.entity_key, row.error_message, json.dumps(row.raw_data, ensure_ascii=False)])
        return f"import_{batch_id}_failed_rows.csv", output.getvalue().encode("utf-8-sig")

    def list_rows(self, db: Session, batch_id: int, page: int, page_size: int, status_filter: str | None) -> dict:
        stmt = (
            select(DataImportRow)
            .where(DataImportRow.import_batch_id == batch_id)
            .order_by(DataImportRow.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        total_stmt = select(func.count(DataImportRow.id)).where(DataImportRow.import_batch_id == batch_id)
        if status_filter:
            stmt = stmt.where(DataImportRow.status == status_filter)
            total_stmt = total_stmt.where(DataImportRow.status == status_filter)
        return {
            "items": [self._serialize_row(item) for item in db.scalars(stmt).all()],
            "total": db.scalar(total_stmt) or 0,
            "page": page,
            "pageSize": page_size,
        }

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
    ) -> tuple[str, str]:
        survey_batch = self._ensure_import_survey_batch(db, batch, current_user, now)
        if file_type == "cbf":
            required = ["cbfbm", "region_code", "cbflx", "cbfmc", "cbfzjlx", "cbfzjhm", "cbfdz", "yzbm", "cbfdcy"]
            self._ensure_required(data, required)
            data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="承包方不在当前数据权限范围内")
            region_code, _region_name = self._resolve_import_region(db, data, current_user)
            tenant_code = data_access_service.derive_tenant_code(region_code)
            group_region_code, group_region_name = self._resolve_group_region(db, data, current_user)
            base = db.scalar(
                select(SurveyCbfBase).where(
                    SurveyCbfBase.batch_id == survey_batch.id,
                    SurveyCbfBase.source_cbfbm == data["cbfbm"],
                )
            )
            operation = "update" if base else "insert"
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

            result = db.scalar(
                select(SurveyCbfResult).where(
                    SurveyCbfResult.batch_id == survey_batch.id,
                    SurveyCbfResult.base_id == base.id,
                )
            )
            if result is None:
                result = SurveyCbfResult(
                    batch_id=survey_batch.id,
                    contractor_uid=base.contractor_uid,
                    base_id=base.id,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                db.add(result)
                self._copy_base_to_contractor_result(result, base)
            elif not result.is_changed and result.survey_status == "not_surveyed":
                self._copy_base_to_contractor_result(result, base)

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
            return self._import_fbf_row(db, batch, survey_batch, row_record, data, current_user, now)
        if file_type == "cbdkxx":
            return self._import_cbdkxx_row(db, batch, survey_batch, row_record, data, current_user, now)
        if file_type == "dk":
            return self._import_dk_row(db, batch, survey_batch, row_record, data, current_user, now, geometry)
        if file_type != "cbf_jtcy":
            raise ValueError(f"不支持的数据类型：{file_type}")

        required = ["cbfbm", "cyxm", "cyzjlx", "cyzjhm", "cyxb", "yhzgx"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="家庭成员不在当前数据权限范围内")
        contractor_base = db.scalar(
            select(SurveyCbfBase).where(
                SurveyCbfBase.batch_id == survey_batch.id,
                SurveyCbfBase.source_cbfbm == data["cbfbm"],
            )
        )
        if contractor_base is None:
            source_result = db.scalars(
                select(SurveyCbfResult)
                .where(SurveyCbfResult.cbfbm == data["cbfbm"])
                .order_by(SurveyCbfResult.id.desc())
            ).first()
            if source_result is None:
                raise ValueError(f"家庭成员对应承包方不存在：{data['cbfbm']}")
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
            cloned_result = SurveyCbfResult(
                tenant_code=contractor_base.tenant_code,
                region_code=contractor_base.region_code,
                batch_id=survey_batch.id,
                contractor_uid=contractor_base.contractor_uid,
                base_id=contractor_base.id,
                initialized_from_base_id=contractor_base.id,
                initialized_at=now,
            )
            db.add(cloned_result)
            self._copy_base_to_contractor_result(cloned_result, contractor_base)
            db.add(
                SurveyContractorTask(
                    tenant_code=contractor_base.tenant_code,
                    region_code=contractor_base.region_code,
                    batch_id=survey_batch.id,
                    contractor_uid=contractor_base.contractor_uid,
                    cbfbm=contractor_base.cbfbm,
                    cbfmc=contractor_base.cbfmc,
                    task_status="not_started",
                )
            )
        member_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:member:{data['cbfbm']}:{data['cyzjhm']}"))
        base = db.scalar(
            select(SurveyCbfJtcyBase).where(
                SurveyCbfJtcyBase.batch_id == survey_batch.id,
                SurveyCbfJtcyBase.base_contractor_code == data["cbfbm"],
                SurveyCbfJtcyBase.base_member_id_no == data["cyzjhm"],
            )
        )
        operation = "update" if base else "insert"
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

        result = db.scalar(
            select(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.batch_id == survey_batch.id,
                SurveyCbfJtcyResult.base_id == base.id,
            )
        )
        if result is None:
            result = SurveyCbfJtcyResult(
                batch_id=survey_batch.id,
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
        self._recount_member_counts(db, {data["cbfbm"]}, survey_batch.id)
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
    ) -> tuple[str, str]:
        required = ["fbfbm", "fbfmc", "fbffzrxm", "fzrzjlx", "fzrzjhm", "fbfdz", "yzbm", "fbfdcy", "fbfdcrq"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["fbfbm"], detail="发包方不在当前数据权限范围内")
        region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["fbfbm"], current_user)
        tenant_code = data_access_service.derive_tenant_code(region_code)
        issuer_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:fbf:{data['fbfbm']}"))
        base = db.scalar(
            select(SurveyFbfBase).where(
                SurveyFbfBase.batch_id == survey_batch.id,
                SurveyFbfBase.source_fbfbm == data["fbfbm"],
            )
        )
        operation = "update" if base else "insert"
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

        result = db.scalar(select(SurveyFbfResult).where(SurveyFbfResult.batch_id == survey_batch.id, SurveyFbfResult.base_id == base.id))
        if result is None:
            result = SurveyFbfResult(
                batch_id=survey_batch.id,
                issuer_uid=issuer_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_fbf_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_fbf_result(result, base)

        legacy = db.get(Fbf, data["fbfbm"])
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
    ) -> tuple[str, str]:
        required = ["dkbm", "fbfbm", "cbfbm", "cbjyqqdfs", "htmj", "cbhtbm", "cbjyqzbm"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["cbfbm"], detail="承包地块信息不在当前数据权限范围内")
        region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["cbfbm"], current_user)
        tenant_code = data_access_service.derive_tenant_code(region_code)
        parcel_info_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:cbdkxx:{data['dkbm']}:{data['cbfbm']}"))
        base = db.scalar(
            select(SurveyCbdkxxBase).where(
                SurveyCbdkxxBase.batch_id == survey_batch.id,
                SurveyCbdkxxBase.source_dkbm == data["dkbm"],
                SurveyCbdkxxBase.cbfbm == data["cbfbm"],
            )
        )
        operation = "update" if base else "insert"
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

        result = db.scalar(select(SurveyCbdkxxResult).where(SurveyCbdkxxResult.batch_id == survey_batch.id, SurveyCbdkxxResult.base_id == base.id))
        if result is None:
            result = SurveyCbdkxxResult(
                batch_id=survey_batch.id,
                parcel_info_uid=parcel_info_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_cbdkxx_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_cbdkxx_result(result, base)
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
    ) -> tuple[str, str]:
        required = ["ysdm", "dkbm", "dkmc", "dklb", "dldj", "tdyt", "sfjbnt", "scmj"]
        self._ensure_required(data, required)
        data_access_service.ensure_code_in_scope(current_user, data["dkbm"], detail="地块不在当前数据权限范围内")
        region_code = self._resolve_code_region(data.get("region_code") or batch.region_code or data["dkbm"], current_user)
        tenant_code = data_access_service.derive_tenant_code(region_code)
        parcel_uid = str(uuid5(NAMESPACE_URL, f"survey:{survey_batch.id}:dk:{data['dkbm']}"))
        base = db.scalar(
            select(SurveyDkBase).where(
                SurveyDkBase.batch_id == survey_batch.id,
                SurveyDkBase.source_dkbm == data["dkbm"],
            )
        )
        operation = "update" if base else "insert"
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
        base.geometry = geometry
        base.source_import_batch_id = base.source_import_batch_id or batch.id
        base.source_import_row_id = base.source_import_row_id or row_record.id
        base.last_import_batch_id = batch.id
        base.last_import_row_id = row_record.id
        base.initialized_from_table = "import"
        base.initialized_from_key = data["dkbm"]
        base.snapshot_at = now
        db.flush()

        result = db.scalar(select(SurveyDkResult).where(SurveyDkResult.batch_id == survey_batch.id, SurveyDkResult.base_id == base.id))
        if result is None:
            result = SurveyDkResult(
                batch_id=survey_batch.id,
                parcel_uid=parcel_uid,
                base_id=base.id,
                initialized_from_base_id=base.id,
                initialized_at=now,
            )
            db.add(result)
            self._copy_base_to_dk_result(result, base)
        elif not result.is_changed and result.survey_status == "not_surveyed":
            self._copy_base_to_dk_result(result, base)
        return operation, base.dkbm

    def _recount_member_counts(self, db: Session, contractor_codes: set[str], survey_batch_id: int | None = None) -> None:
        if survey_batch_id is None:
            batch_ids = [
                batch_id
                for batch_id in db.scalars(
                    select(SurveyCbfBase.batch_id).where(SurveyCbfBase.source_cbfbm.in_(contractor_codes)).distinct()
                ).all()
            ]
        else:
            batch_ids = [survey_batch_id]
        for batch_id in batch_ids:
            for code in contractor_codes:
                contractor = db.scalar(
                    select(SurveyCbfBase).where(
                        SurveyCbfBase.batch_id == batch_id,
                        SurveyCbfBase.source_cbfbm == code,
                    )
                )
                if contractor is None:
                    continue
                count = db.scalar(
                    select(func.count(SurveyCbfJtcyBase.id)).where(
                        SurveyCbfJtcyBase.batch_id == batch_id,
                        SurveyCbfJtcyBase.base_contractor_code == code,
                    )
                ) or 0
                contractor.cbfcysl = count
                result = db.scalar(
                    select(SurveyCbfResult).where(
                        SurveyCbfResult.batch_id == batch_id,
                        SurveyCbfResult.base_id == contractor.id,
                    )
                )
                if result is not None and not result.is_changed and result.survey_status == "not_surveyed":
                    result.cbfcysl = count

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
            batch_name=f"{batch.import_name} 调查成果",
            region_code=batch.region_code,
            region_name=batch.region_name,
            survey_type="import_survey",
            status="active",
            started_at=now,
            created_by=current_user.id,
            remark=f"由导入批次 {batch.import_no} 自动生成",
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
        result.geometry = base.geometry
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
            "cbfcysl": ["家庭成员数", "承包方成员数量"],
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
            raise ValueError(f"缺少必填字段：{', '.join(missing)}")

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
        raise ValueError(f"不支持的数据类型：{file_type}")

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
            raise ValueError("缺少导入区域")
        data_access_service.ensure_region_in_scope(current_user, normalized, detail="导入区域不在当前数据权限范围内")
        return normalized

    def _decode_csv(self, content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无法识别 CSV 文件编码")

    def _infer_archive_csv_type(self, filename: str) -> str | None:
        name = filename.replace("\\", "/").lower()
        if any(token in name for token in ("cbf_jtcy", "jtcy", "member", "家庭成员", "成员")):
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
                raise ValueError("缺少必填数值字段")
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"数值格式不正确：{value}") from exc

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.combine(datetime.strptime(text, fmt).date(), datetime.min.time())
            except ValueError:
                pass
        return datetime.combine(date.fromisoformat(text), datetime.min.time())

    def _resolve_group_region(self, db: Session, data: dict, current_user: User) -> tuple[str | None, str | None]:
        code = (data.get("group_region_code") or "").strip()
        if not code:
            return None, None
        data_access_service.ensure_region_in_scope(current_user, code, detail="所属组不在当前数据权限范围内")
        region = db.scalar(select(Region).where(Region.code == code).execution_options(skip_tenant_scope=True))
        name = region.full_name if region else (data.get("group_region_name") or "")
        return code, name.strip() or None

    def _resolve_import_region(self, db: Session, data: dict, current_user: User) -> tuple[str, str | None]:
        code = (data.get("region_code") or "").strip()
        if not code:
            raise ValueError("缺少必填字段：region_code")
        normalized = data_access_service.normalize_region_code(code)
        if not normalized or len(normalized) < 6:
            raise ValueError("区域代码格式不正确")
        data_access_service.ensure_region_in_scope(current_user, normalized, detail="区域代码不在当前数据权限范围内")
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
