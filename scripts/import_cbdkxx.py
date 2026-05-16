"""
Import data from public.cbdkxx into survey_cbdkxx_base and survey_cbdkxx_result.

Usage:
    cd backend && python ../scripts/import_cbdkxx.py
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
import app.db.base as _db  # noqa: F401  ensure all models are registered
from app.db.migrations import upgrade_schema
from app.models.base import Base
from app.models.survey import SurveyBatch, SurveyCbdkxxBase, SurveyCbdkxxResult

engine = create_engine(settings.sqlalchemy_database_uri, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Ensure all tables exist before proceeding
Base.metadata.create_all(engine)
upgrade_schema(engine)


def derive_region_code(value: str | None) -> str | None:
    if not value:
        return None
    text_val = str(value).strip()
    if len(text_val) >= 14:
        return text_val[:14]
    if len(text_val) >= 12:
        return text_val[:12]
    if len(text_val) >= 9:
        return text_val[:9]
    return text_val[:6] if len(text_val) >= 6 else text_val


def derive_tenant_code(region_code: str | None) -> str | None:
    return region_code[:6] if region_code and len(region_code) >= 6 else None


def main():
    db = SessionLocal()
    now = datetime.now(timezone.utc)

    try:
        # 1. Read all rows from public.cbdkxx first, to derive region info for the batch
        rows = db.execute(text("SELECT dkbm, fbfbm, cbfbm, cbjyqqdfs, htmj, cbhtbm, lzhtbm, cbjyqzbm, yhtmj, htmjm, yhtmjm, sfqqqg FROM public.cbdkxx")).fetchall()
        print(f"从 public.cbdkxx 读取到 {len(rows)} 条记录")

        # Derive a representative region_code from the first valid row
        batch_region_code = "321324"
        for row in rows:
            cbfbm = str(row[2]).strip() if row[2] else None
            if cbfbm:
                batch_region_code = derive_region_code(cbfbm) or "321324"
                break
        batch_tenant_code = derive_tenant_code(batch_region_code)

        # 2. Ensure survey batch
        batch = db.scalar(select(SurveyBatch).where(SurveyBatch.batch_name == "cbdkxx 初始导入"))
        if batch is None:
            next_id = (db.scalar(select(SurveyBatch.id).order_by(SurveyBatch.id.desc())) or 0) + 1
            batch = SurveyBatch(
                batch_no=f"SUR{now:%Y%m%d}{next_id:04d}",
                batch_name="cbdkxx 初始导入",
                tenant_code=batch_tenant_code,
                region_code=batch_region_code,
                survey_type="import_survey",
                status="active",
                started_at=now,
                remark="从 public.cbdkxx 表直接导入",
            )
            db.add(batch)
            db.flush()
            print(f"创建调查批次: {batch.batch_no} (tenant={batch_tenant_code}, region={batch_region_code})")

        inserted = 0
        updated = 0
        skipped = 0

        for row in rows:
            dkbm = str(row[0]).strip() if row[0] else None
            fbfbm = str(row[1]).strip() if row[1] else None
            cbfbm = str(row[2]).strip() if row[2] else None
            cbjyqqdfs = str(row[3]).strip() if row[3] else None
            htmj = row[4]
            cbhtbm = str(row[5]).strip() if row[5] else None
            lzhtbm = str(row[6]).strip() if row[6] else None
            cbjyqzbm = str(row[7]).strip() if row[7] else None
            yhtmj = row[8]
            htmjm = row[9]
            yhtmjm = row[10]
            sfqqqg = str(row[11]).strip() if row[11] else None

            # validate required
            if not all([dkbm, fbfbm, cbfbm, cbjyqqdfs, htmj is not None, cbhtbm, cbjyqzbm]):
                print(f"  跳过（缺少必填字段）: dkbm={dkbm}, cbfbm={cbfbm}")
                skipped += 1
                continue

            region_code = derive_region_code(cbfbm)
            tenant_code = derive_tenant_code(region_code)

            htmj_decimal = Decimal(str(htmj))
            yhtmj_decimal = Decimal(str(yhtmj)) if yhtmj is not None else None
            htmjm_decimal = Decimal(str(htmjm)) if htmjm is not None else None
            yhtmjm_decimal = Decimal(str(yhtmjm)) if yhtmjm is not None else None

            parcel_info_uid = str(uuid5(NAMESPACE_URL, f"survey:{batch.id}:cbdkxx:{dkbm}:{cbfbm}"))

            # check existing base record
            existing_base = db.scalar(
                select(SurveyCbdkxxBase).where(
                    SurveyCbdkxxBase.batch_id == batch.id,
                    SurveyCbdkxxBase.source_dkbm == dkbm,
                    SurveyCbdkxxBase.cbfbm == cbfbm,
                )
            )

            if existing_base is not None:
                # update existing
                existing_base.tenant_code = tenant_code
                existing_base.region_code = region_code
                existing_base.parcel_info_uid = parcel_info_uid
                existing_base.dkbm = dkbm
                existing_base.fbfbm = fbfbm
                existing_base.cbfbm = cbfbm
                existing_base.cbjyqqdfs = cbjyqqdfs
                existing_base.htmj = htmj_decimal
                existing_base.cbhtbm = cbhtbm
                existing_base.lzhtbm = lzhtbm
                existing_base.cbjyqzbm = cbjyqzbm
                existing_base.yhtmj = yhtmj_decimal
                existing_base.htmjm = htmjm_decimal
                existing_base.yhtmjm = yhtmjm_decimal
                existing_base.sfqqqg = sfqqqg
                existing_base.snapshot_at = now
                db.flush()

                existing_result = db.scalar(
                    select(SurveyCbdkxxResult).where(
                        SurveyCbdkxxResult.batch_id == batch.id,
                        SurveyCbdkxxResult.base_id == existing_base.id,
                    )
                )
                if existing_result is not None and not existing_result.is_changed and existing_result.survey_status == "not_surveyed":
                    _copy_base_to_result(existing_result, existing_base)
                updated += 1
            else:
                base = SurveyCbdkxxBase(
                    batch_id=batch.id,
                    parcel_info_uid=parcel_info_uid,
                    source_dkbm=dkbm,
                    dkbm=dkbm,
                    fbfbm=fbfbm,
                    cbfbm=cbfbm,
                    cbjyqqdfs=cbjyqqdfs,
                    htmj=htmj_decimal,
                    cbhtbm=cbhtbm,
                    lzhtbm=lzhtbm,
                    cbjyqzbm=cbjyqzbm,
                    yhtmj=yhtmj_decimal,
                    htmjm=htmjm_decimal,
                    yhtmjm=yhtmjm_decimal,
                    sfqqqg=sfqqqg,
                    tenant_code=tenant_code,
                    region_code=region_code,
                    initialized_from_table="cbdkxx",
                    initialized_from_key=f"{dkbm}:{cbfbm}",
                    initialized_at=now,
                    snapshot_at=now,
                )
                db.add(base)
                db.flush()

                result = SurveyCbdkxxResult(
                    batch_id=batch.id,
                    parcel_info_uid=parcel_info_uid,
                    base_id=base.id,
                    dkbm=dkbm,
                    fbfbm=fbfbm,
                    cbfbm=cbfbm,
                    cbjyqqdfs=cbjyqqdfs,
                    htmj=htmj_decimal,
                    cbhtbm=cbhtbm,
                    lzhtbm=lzhtbm,
                    cbjyqzbm=cbjyqzbm,
                    yhtmj=yhtmj_decimal,
                    htmjm=htmjm_decimal,
                    yhtmjm=yhtmjm_decimal,
                    sfqqqg=sfqqqg,
                    tenant_code=tenant_code,
                    region_code=region_code,
                    initialized_from_base_id=base.id,
                    initialized_at=now,
                )
                db.add(result)
                inserted += 1

            if (inserted + updated) % 100 == 0:
                db.commit()
                print(f"  已处理 {inserted + updated} 条...")

        db.commit()
        print(f"\n导入完成：新增 {inserted} 条, 更新 {updated} 条, 跳过 {skipped} 条")

    except Exception as e:
        db.rollback()
        print(f"导入失败: {e}")
        raise
    finally:
        db.close()


def _copy_base_to_result(result: SurveyCbdkxxResult, base: SurveyCbdkxxBase) -> None:
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


if __name__ == "__main__":
    main()
