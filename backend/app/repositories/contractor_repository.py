from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.survey import (
    SurveyCbdkxxBase,
    SurveyCbdkxxResult,
    SurveyCbfBase,
    SurveyCbfJtcyBase,
    SurveyCbfJtcyResult,
    SurveyCbfResult,
    SurveyChangeDiff,
    SurveyChangeRecord,
    SurveyDkBase,
    SurveyDkResult,
    SurveyHouseholdTag,
)


class ContractorRepository:
    def list_contractors(
        self,
        db: Session,
        page: int,
        page_size: int,
        *,
        extra_filters: list | None = None,
        keyword: str | None = None,
        type_code: str | None = None,
        name: str | None = None,
        member_name: str | None = None,
        id_no: str | None = None,
        address: str | None = None,
        region_code: str | None = None,
    ) -> tuple[list[SurveyCbfResult], int]:
        total_stmt = select(func.count(SurveyCbfResult.id))
        stmt = select(SurveyCbfResult).order_by(SurveyCbfResult.id.desc()).offset((page - 1) * page_size).limit(page_size)
        if extra_filters:
            total_stmt = total_stmt.where(*extra_filters)
            stmt = stmt.where(*extra_filters)
        if region_code:
            region_pattern = f"{region_code}%"
            condition = or_(
                SurveyCbfResult.group_region_code.like(region_pattern),
                SurveyCbfResult.region_code.like(region_pattern),
                SurveyCbfResult.cbfbm.like(region_pattern),
            )
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if keyword:
            pattern = f"%{keyword}%"
            keyword_filter = or_(
                SurveyCbfResult.cbfbm.ilike(pattern),
                SurveyCbfResult.cbfmc.ilike(pattern),
                SurveyCbfResult.cbfzjhm.ilike(pattern),
                SurveyCbfResult.lxdh.ilike(pattern),
                SurveyCbfResult.cbfdz.ilike(pattern),
            )
            total_stmt = total_stmt.where(keyword_filter)
            stmt = stmt.where(keyword_filter)
        if type_code:
            total_stmt = total_stmt.where(SurveyCbfResult.cbflx == type_code)
            stmt = stmt.where(SurveyCbfResult.cbflx == type_code)
        if name:
            condition = SurveyCbfResult.cbfmc.ilike(f"%{name}%")
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if member_name:
            condition = exists(
                select(SurveyCbfJtcyResult.id).where(
                    SurveyCbfJtcyResult.cbfbm == SurveyCbfResult.cbfbm,
                    SurveyCbfJtcyResult.cyxm.ilike(f"%{member_name}%"),
                )
            )
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if id_no:
            pattern = f"%{id_no}%"
            condition = or_(
                SurveyCbfResult.cbfzjhm.ilike(pattern),
                exists(
                    select(SurveyCbfJtcyResult.id).where(
                        SurveyCbfJtcyResult.cbfbm == SurveyCbfResult.cbfbm,
                        SurveyCbfJtcyResult.cyzjhm.ilike(pattern),
                    )
                ),
            )
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        if address:
            condition = SurveyCbfResult.cbfdz.ilike(f"%{address}%")
            total_stmt = total_stmt.where(condition)
            stmt = stmt.where(condition)
        total = db.scalar(total_stmt) or 0
        return list(db.scalars(stmt).all()), total

    def get_contractor(self, db: Session, code: str) -> SurveyCbfResult | None:
        return db.scalar(
            select(SurveyCbfResult).where(SurveyCbfResult.cbfbm == code).order_by(SurveyCbfResult.id.desc()).limit(1)
        )

    def get_contractor_in_batch(self, db: Session, batch_id: int, code: str) -> SurveyCbfResult | None:
        base = db.scalar(select(SurveyCbfBase).where(SurveyCbfBase.batch_id == batch_id, SurveyCbfBase.cbfbm == code).limit(1))
        if base is None:
            return None
        return db.scalar(
            select(SurveyCbfResult)
            .where(SurveyCbfResult.cbfbm == code)
            .order_by(SurveyCbfResult.id.desc())
            .limit(1)
        )

    def get_base_for_result(self, db: Session, contractor: SurveyCbfResult) -> SurveyCbfBase | None:
        """结果行 → 该户在调查批次里的快照行（``survey_cbf_base``）。

        链接方向是 ``base.result_id → result.id``：在「base 表加 result_id、
        result 表去掉 base_id」那次重构之后，``SurveyCbfResult`` 上**已经没有**
        ``base_id`` 属性了，任何 ``contractor.base_id`` 都会 AttributeError。

        ``result_id`` 尚未回填的历史数据退回按 ``contractor_uid`` 匹配；
        两者都匹配不到就返回 ``None`` —— 承包方管理对「只有结果行、
        没有批次快照行」的户（例如数据导入直写的户）必须照常可读可改。
        """
        if contractor is None or contractor.id is None:
            return None
        base = db.scalar(
            select(SurveyCbfBase)
            .where(SurveyCbfBase.result_id == contractor.id)
            .order_by(SurveyCbfBase.id.desc())
            .limit(1)
        )
        if base is not None:
            return base
        if not contractor.contractor_uid:
            return None
        return db.scalar(
            select(SurveyCbfBase)
            .where(SurveyCbfBase.contractor_uid == contractor.contractor_uid)
            .order_by(SurveyCbfBase.id.desc())
            .limit(1)
        )

    def list_family_members(self, db: Session, contractor: SurveyCbfResult) -> list[SurveyCbfJtcyResult]:
        # 家庭成员按 contractor_uid 归属（与调查模块其它读取处一致），
        # 不用 cbfbm：户被分/合之后 cbfbm 会变，uid 才是稳定身份。
        stmt = (
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.contractor_uid == contractor.contractor_uid,
            )
            .order_by(SurveyCbfJtcyResult.cyxm, SurveyCbfJtcyResult.cyzjhm)
        )
        return list(db.scalars(stmt).all())

    def delete_contractor(self, db: Session, contractor: SurveyCbfResult) -> None:
        """删除一户调查成果，并连带清理所有挂在该户上的派生数据。

        历史实现只删 survey_cbf_jtcy_result / survey_cbf_jtcy_base / survey_cbf_base /
        survey_cbf_result 四张表，其余全部残留：
          - survey_cbdkxx_result / survey_cbdkxx_base  → 该户的地块关联
          - survey_dk_result / survey_dk_base          → 该户新增出来的地块本体
          - survey_change_records / survey_change_diffs → 无主的变更记录与差异行
          - survey_household_tags                       → 无主的户标签
        后果是地块编码被永久占用（同一 dkbm 重新录入直接 400 already exists），
        变更台账里留下一批查不到户的历史行。

        地块本体只在「不再被任何承包方关联」时才删，避免误删别的户仍在使用的
        存量地块。删除范围与 split_household / merge_household 的销毁口径保持一致。
        """
        base = self.get_base_for_result(db, contractor)
        contractor_uid = contractor.contractor_uid
        cbfbm = contractor.cbfbm

        # 先记下该户名下的地块编码，用于后面判断地块本体是否还有别的户在用。
        related_dkbms = set(
            db.scalars(
                select(SurveyCbdkxxResult.dkbm).where(SurveyCbdkxxResult.cbfbm == cbfbm)
            ).all()
        )
        if base is not None:
            related_dkbms.update(
                db.scalars(
                    select(SurveyCbdkxxBase.dkbm).where(
                        SurveyCbdkxxBase.batch_id == base.batch_id,
                        SurveyCbdkxxBase.cbfbm == cbfbm,
                    )
                ).all()
            )

        db.execute(
            delete(SurveyCbfJtcyResult).where(
                SurveyCbfJtcyResult.contractor_uid == contractor_uid,
            )
        )
        if base is not None:
            db.execute(
                delete(SurveyCbfJtcyBase).where(
                    SurveyCbfJtcyBase.batch_id == base.batch_id,
                    SurveyCbfJtcyBase.contractor_uid == contractor_uid,
                )
            )
            db.execute(
                delete(SurveyCbdkxxBase).where(
                    SurveyCbdkxxBase.batch_id == base.batch_id,
                    SurveyCbdkxxBase.cbfbm == cbfbm,
                )
            )

        # 承包方-地块关联（结果态）。契约：地块关联挂在 cbfbm 上，没有 contractor_uid 列。
        db.execute(delete(SurveyCbdkxxResult).where(SurveyCbdkxxResult.cbfbm == cbfbm))

        # 地块本体：仅当已无任何关联时删除。此处的 count 查询发生在上面
        # delete 之后（SQLAlchemy 的 bulk delete 立即下发），因此只统计别的户。
        for dkbm in related_dkbms:
            still_referenced = db.scalar(
                select(func.count(SurveyCbdkxxResult.id)).where(SurveyCbdkxxResult.dkbm == dkbm)
            ) or 0
            if base is not None:
                still_referenced += db.scalar(
                    select(func.count(SurveyCbdkxxBase.id)).where(SurveyCbdkxxBase.dkbm == dkbm)
                ) or 0
            if still_referenced:
                continue
            db.execute(delete(SurveyDkResult).where(SurveyDkResult.dkbm == dkbm))
            if base is not None:
                db.execute(
                    delete(SurveyDkBase).where(
                        SurveyDkBase.batch_id == base.batch_id,
                        SurveyDkBase.dkbm == dkbm,
                    )
                )

        # 变更台账与自动标签：跟注销 / 分户 / 合户的清理口径一致，不留无主行。
        db.execute(
            delete(SurveyChangeDiff).where(SurveyChangeDiff.contractor_uid == contractor_uid)
        )
        db.execute(
            delete(SurveyChangeRecord).where(SurveyChangeRecord.contractor_uid == contractor_uid)
        )
        db.execute(
            delete(SurveyHouseholdTag).where(SurveyHouseholdTag.contractor_uid == contractor_uid)
        )

        if base is not None:
            db.delete(base)
        db.delete(contractor)
        db.commit()


contractor_repository = ContractorRepository()
