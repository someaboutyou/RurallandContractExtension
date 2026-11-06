"""承包方家庭关系检查 / 替换（对齐 CS 版「家庭关系处理」）。

检查规则（与 CS 版 ``TaskRelationDealOperation.RelationCheck`` 同口径）：
1. 承包方本人那条成员记录，家庭关系必须是「本人」或「户主」；
2. 非承包方本人的成员，不能是「户主」（存在多个户主）；
3. 家庭关系不能为空，且必须在家庭关系代码表中；
4. 年龄校验：
   - 子女类关系应比承包方年轻（年龄差 <= 0 告警）；
   - 父母类关系应比承包方年长（年龄差 >= 0 告警）；
   - 孙子女类关系年龄差应大于 35 岁；
   - 其他关系年龄差应大于 15 岁。

替换规则（与 CS 版 ``TaskInitialVPRelationShipOperation`` 同口径）：
把当前批次内所有家庭关系等于「查找内容」的成员批量改为「替换内容」。
"""

from __future__ import annotations

import logging
import re
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.survey import SurveyBatch, SurveyCbfBase, SurveyCbfJtcyResult, SurveyCbfResult
from app.models.user import User
from app.services.data_access_service import data_access_service
from app.services.dictionary_service import dictionary_service

logger = logging.getLogger(__name__)

RELATION_DICT_TYPE = "nyt2539_c20_relation_to_head"

_SELF_RELATIONS = {"本人", "户主"}
_UP_RELATIONS = {"父母", "父亲", "母亲"}
_DOWN_RELATIONS = {
    "子", "女", "独生子", "长子", "次子", "三子", "四子", "五子",
    "其他儿子", "独生女", "长女", "次女", "三女", "四女", "五女", "其他女儿",
}
_GRAND_DOWN_RELATIONS = {
    "孙子", "孙女", "外孙子", "外孙女",
    "孙媳妇或外孙媳妇", "孙女婿或外孙女婿",
    "曾孙子或外曾孙子", "曾孙女或外曾孙女",
    "其他孙子、孙女或外孙子、外孙女",
}


def _birth_from_id(id_no: str) -> date | None:
    digits = re.sub(r"\D", "", id_no or "")
    try:
        if len(digits) == 18:
            return date(int(digits[6:10]), int(digits[10:12]), int(digits[12:14]))
        if len(digits) == 15:
            return date(1900 + int(digits[6:8]), int(digits[8:10]), int(digits[10:12]))
    except ValueError:
        return None
    return None


def _year_diff(contractor_birth: date, member_birth: date) -> int:
    return member_birth.year - contractor_birth.year


class ContractorRelationService:
    def _dictionary(self, db: Session) -> tuple[dict[str, str], dict[str, str]]:
        options = dictionary_service.get_options(db, RELATION_DICT_TYPE)
        label_by_code = {item["value"]: item["label"] for item in options}
        code_by_label = {item["label"]: item["value"] for item in options}
        return label_by_code, code_by_label

    @staticmethod
    def _relation_label(value: str | None, label_by_code: dict[str, str]) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        return label_by_code.get(text, text)

    def _load_batch_data(
        self, db: Session, batch_id: int, current_user: User
    ) -> tuple[SurveyBatch, list[SurveyCbfBase], dict[str, SurveyCbfResult], dict[str, list[SurveyCbfJtcyResult]]]:
        batch = db.get(SurveyBatch, batch_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="调查批次不存在")
        data_access_service.ensure_region_filter_in_scope(
            current_user, batch.region_code, detail="当前批次区域不在可处理范围内"
        )
        bases = db.scalars(
            select(SurveyCbfBase)
            .where(
                SurveyCbfBase.tenant_code == batch.tenant_code,
                SurveyCbfBase.batch_id == batch_id,
            )
            .order_by(SurveyCbfBase.cbfbm.asc(), SurveyCbfBase.id.desc())
            .execution_options(skip_tenant_scope=True)
        ).all()
        # 同一户可能存在多条 base 快照（分户/合户/历史数据），按 uid 取最新一条，
        # 否则检查会把同一户的成员重复统计。
        unique_bases: list[SurveyCbfBase] = []
        seen_uids: set[str] = set()
        for base in bases:
            if not base.contractor_uid or base.contractor_uid in seen_uids:
                continue
            seen_uids.add(base.contractor_uid)
            unique_bases.append(base)
        bases = unique_bases
        uids = list(seen_uids)
        results: dict[str, SurveyCbfResult] = {}
        members: dict[str, list[SurveyCbfJtcyResult]] = {}
        if uids:
            result_rows = db.scalars(
                select(SurveyCbfResult)
                .where(
                    SurveyCbfResult.tenant_code == batch.tenant_code,
                    SurveyCbfResult.contractor_uid.in_(uids),
                )
                .order_by(SurveyCbfResult.id.asc())
                .execution_options(skip_tenant_scope=True)
            ).all()
            for row in result_rows:
                results[row.contractor_uid] = row
            member_rows = db.scalars(
                select(SurveyCbfJtcyResult)
                .where(
                    SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
                    SurveyCbfJtcyResult.contractor_uid.in_(uids),
                )
                .order_by(SurveyCbfJtcyResult.id.asc())
                .execution_options(skip_tenant_scope=True)
            ).all()
            for row in member_rows:
                members.setdefault(row.contractor_uid, []).append(row)
        return batch, bases, results, members

    def check(self, db: Session, batch_id: int, current_user: User) -> dict:
        _, bases, results, members = self._load_batch_data(db, batch_id, current_user)
        label_by_code, _ = self._dictionary(db)
        all_labels = set(label_by_code.values())
        issues: list[dict] = []
        member_count = 0

        for base in bases:
            result = results.get(base.contractor_uid)
            contractor_name = (result.cbfmc if result else base.cbfmc) or ""
            contractor_id = (result.cbfzjhm if result else base.cbfzjhm) or ""
            contractor_birth = _birth_from_id(contractor_id)
            for member in members.get(base.contractor_uid, []):
                member_count += 1
                relation = self._relation_label(member.yhzgx, label_by_code)
                is_self = member.cyxm == contractor_name and member.cyzjhm == contractor_id
                base_issue = {
                    "contractorCode": (result.cbfbm if result else base.cbfbm) or "",
                    "contractorName": contractor_name,
                    "memberName": member.cyxm or "",
                    "memberIdNo": member.cyzjhm or "",
                    "relation": relation,
                }

                def add_issue(kind: str, message: str) -> None:
                    issues.append({**base_issue, "type": kind, "message": message})

                if is_self and relation not in _SELF_RELATIONS:
                    add_issue("self_relation", "承包方本人的家庭关系应为「本人」或「户主」")
                    continue
                if not is_self and relation == "户主":
                    add_issue("multiple_head", "非承包方本人不能为户主（存在多个户主）")
                    continue
                if not relation:
                    add_issue("empty", "未填写家庭关系")
                    continue
                if relation not in all_labels:
                    add_issue("invalid", f"家庭关系「{relation}」不在家庭关系代码表中")
                    continue

                member_birth = _birth_from_id(member.cyzjhm)
                if contractor_birth is None or member_birth is None:
                    continue
                diff = _year_diff(contractor_birth, member_birth)
                if relation in _DOWN_RELATIONS:
                    if diff <= 0:
                        add_issue("age", f"家庭关系为「{relation}」，但年龄不比承包方小")
                    elif abs(diff) <= 15:
                        add_issue("age", f"家庭关系为「{relation}」，但年龄只相差 {abs(diff)} 岁")
                elif relation in _UP_RELATIONS:
                    if diff >= 0:
                        add_issue("age", f"家庭关系为「{relation}」，但年龄不比承包方大")
                    elif abs(diff) <= 15:
                        add_issue("age", f"家庭关系为「{relation}」，但年龄只相差 {abs(diff)} 岁")
                elif relation in _GRAND_DOWN_RELATIONS and abs(diff) <= 35:
                    add_issue("age", f"家庭关系为「{relation}」，但年龄只相差 {abs(diff)} 岁")

        return {
            "contractorCount": len(bases),
            "memberCount": member_count,
            "issueCount": len(issues),
            "issues": issues,
        }

    def repair_members(self, db: Session, batch_id: int, current_user: User) -> dict:
        """家庭成员关联修复（对齐 CS 版「数据修复-家庭成员修复」）。

        CS 版修复的是成员身上的 ``FamilyID``（所属承包方 ID）。本系统的对应
        字段是 ``survey_cbf_jtcy_result.contractor_uid``，同时成员表还冗余了
        ``cbfbm``（承包方编码）。修复规则：

        1. 成员 uid 不属于本批次、但编码能匹配到本批次承包方 ⇒ 把 uid 修正到
           该承包方；
        2. 成员 uid 属于本批次、但编码与承包方当前编码不一致 ⇒ 把编码修正；
        3. 只修关联字段，不改姓名、证件、家庭关系等业务数据。

        与 CS 版一致，仅修复当前地域（本批次）的成员关联。
        """
        batch, bases, results, _ = self._load_batch_data(db, batch_id, current_user)
        uids = {base.contractor_uid for base in bases if base.contractor_uid}
        code_by_uid: dict[str, str] = {}
        uid_by_code: dict[str, str] = {}
        for base in bases:
            result = results.get(base.contractor_uid)
            code = (result.cbfbm if result else base.cbfbm) or ""
            if not code:
                continue
            code_by_uid[base.contractor_uid] = code
            uid_by_code.setdefault(code, base.contractor_uid)

        codes = list(uid_by_code)
        if not codes and not uids:
            return {
                "scannedMembers": 0,
                "repairedMembers": 0,
                "repairedContractors": 0,
                "samples": [],
            }

        members = db.scalars(
            select(SurveyCbfJtcyResult)
            .where(
                SurveyCbfJtcyResult.tenant_code == batch.tenant_code,
                or_(
                    SurveyCbfJtcyResult.contractor_uid.in_(uids),
                    SurveyCbfJtcyResult.cbfbm.in_(codes),
                ),
            )
            .order_by(SurveyCbfJtcyResult.id.asc())
            .execution_options(skip_tenant_scope=True)
        ).all()

        repaired = 0
        repaired_contractors: set[str] = set()
        samples: list[dict] = []
        for member in members:
            target_uid = member.contractor_uid if member.contractor_uid in uids else uid_by_code.get(member.cbfbm)
            if not target_uid:
                continue
            target_code = code_by_uid.get(target_uid) or member.cbfbm
            old_uid, old_code = member.contractor_uid, member.cbfbm
            changed = False
            if old_uid != target_uid:
                member.contractor_uid = target_uid
                changed = True
            if target_code and old_code != target_code:
                member.cbfbm = target_code
                changed = True
            if changed:
                repaired += 1
                repaired_contractors.add(target_uid)
                if len(samples) < 50:
                    samples.append({
                        "memberName": member.cyxm or "",
                        "oldContractorUid": old_uid,
                        "newContractorUid": target_uid,
                        "oldCbfbm": old_code,
                        "newCbfbm": member.cbfbm,
                    })

        db.commit()
        logger.info(
            "家庭成员关联修复 batch_id=%s 扫描=%s 修复成员=%s 涉及承包方=%s 操作人=%s",
            batch_id, len(members), repaired, len(repaired_contractors),
            getattr(current_user, "username", None),
        )
        return {
            "scannedMembers": len(members),
            "repairedMembers": repaired,
            "repairedContractors": len(repaired_contractors),
            "samples": samples,
        }

    def replace(
        self,
        db: Session,
        batch_id: int,
        from_relation: str,
        to_relation: str,
        current_user: User,
    ) -> dict:
        batch, bases, _, members = self._load_batch_data(db, batch_id, current_user)
        if batch.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="调查批次已结束，不能替换家庭关系",
            )
        label_by_code, code_by_label = self._dictionary(db)
        from_label = self._relation_label(from_relation, label_by_code)
        to_label = self._relation_label(to_relation, label_by_code)
        to_code = code_by_label.get(to_label)
        if not from_label:
            raise HTTPException(status_code=400, detail="查找内容不允许为空")
        if not to_code:
            raise HTTPException(status_code=400, detail="替换内容不在家庭关系代码表中")
        if from_label == to_label:
            raise HTTPException(status_code=400, detail="查找内容与替换内容不能相同")

        updated_members = 0
        updated_contractors: set[str] = set()
        for base in bases:
            for member in members.get(base.contractor_uid, []):
                if self._relation_label(member.yhzgx, label_by_code) != from_label:
                    continue
                member.yhzgx = to_code
                if to_label == "户主":
                    member.is_household_head = True
                elif from_label == "户主":
                    member.is_household_head = False
                updated_members += 1
                updated_contractors.add(base.contractor_uid)

        db.commit()
        logger.info(
            "家庭关系替换 batch_id=%s %s -> %s 成员=%s 承包方=%s 操作人=%s",
            batch_id, from_label, to_label, updated_members, len(updated_contractors),
            getattr(current_user, "username", None),
        )
        return {
            "fromLabel": from_label,
            "toLabel": to_label,
            "updatedMembers": updated_members,
            "updatedContractors": len(updated_contractors),
        }


contractor_relation_service = ContractorRelationService()
