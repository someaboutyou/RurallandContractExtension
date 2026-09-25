from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dictionary import DictionaryItem

# ── 单值配置型字典 ──────────────────────────────────────────────
# 这类字典不是"选项列表"，而是把原本写死在代码里的配置项搬进字典表，
# 由运维在「字典管理」页自行维护，代码侧只负责读取 + 兜底。
# 约定：item_value 为配置键（缺省取 default），item_name 为实际取用的值。

SURVEY_ORG_DICT_TYPE = "survey_org"
SURVEY_ORG_DICT_NAME = "调查单位（机构）"
DEFAULT_SURVEY_ORG = "江苏中天吉奥信息技术股份有限公司"


class DictionaryService:
    def list_items(
        self,
        db: Session,
        dict_type: str | None = None,
        keyword: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict]:
        stmt = select(DictionaryItem).order_by(
            DictionaryItem.dict_type.asc(),
            DictionaryItem.sort_order.asc(),
            DictionaryItem.item_value.asc(),
        )

        if dict_type:
            stmt = stmt.where(DictionaryItem.dict_type == dict_type)
        if keyword:
            kw = f"%{keyword}%"
            stmt = stmt.where(
                DictionaryItem.dict_type.ilike(kw)
                | DictionaryItem.dict_name.ilike(kw)
                | DictionaryItem.item_value.ilike(kw)
                | DictionaryItem.item_name.ilike(kw)
            )
        if enabled is not None:
            stmt = stmt.where(DictionaryItem.enabled == enabled)

        items = db.scalars(stmt).all()
        return [self._serialize(item) for item in items]

    def get_options(self, db: Session, dict_type: str) -> list[dict]:
        stmt = (
            select(DictionaryItem)
            .where(DictionaryItem.dict_type == dict_type, DictionaryItem.enabled == True)  # noqa: E712
            .order_by(DictionaryItem.sort_order.asc(), DictionaryItem.item_value.asc())
        )
        items = db.scalars(stmt).all()
        return [{"value": item.item_value, "label": item.item_name} for item in items]

    def get_setting(
        self,
        db: Session,
        dict_type: str,
        default: str | None = None,
        key: str | None = None,
    ) -> str | None:
        """读取「单值配置型字典」的当前取值。

        - 传了 ``key`` 就先按 ``item_value == key`` 精确命中；
        - 没命中（或没传 key）则取该类型下启用项里排序最靠前的一条；
        - 取用 ``item_name``，为空时退回 ``item_value``；
        - 完全没有可用项时返回 ``default``，保证调用方永远拿得到一个能打印的值。
        """
        stmt = (
            select(DictionaryItem)
            .where(DictionaryItem.dict_type == dict_type, DictionaryItem.enabled == True)  # noqa: E712
            .order_by(DictionaryItem.sort_order.asc(), DictionaryItem.id.asc())
        )
        if key:
            matched = db.scalars(stmt.where(DictionaryItem.item_value == key)).first()
            if matched is not None:
                return (matched.item_name or "").strip() or matched.item_value or default

        item = db.scalars(stmt).first()
        if item is None:
            return default
        return (item.item_name or "").strip() or item.item_value or default

    def create_item(self, db: Session, payload: dict) -> dict:
        item = DictionaryItem(
            dict_type=payload["dictType"].strip(),
            dict_name=payload["dictName"].strip(),
            item_value=payload["itemValue"].strip(),
            item_name=payload["itemName"].strip(),
            sort_order=payload.get("sortOrder") or 0,
            enabled=payload.get("enabled", True),
            remark=payload.get("remark"),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return self._serialize(item)

    def update_item(self, db: Session, item_id: int, payload: dict) -> dict:
        item = self._get_or_404(db, item_id)
        item.dict_type = payload["dictType"].strip()
        item.dict_name = payload["dictName"].strip()
        item.item_value = payload["itemValue"].strip()
        item.item_name = payload["itemName"].strip()
        item.sort_order = payload.get("sortOrder") or 0
        item.enabled = payload.get("enabled", True)
        item.remark = payload.get("remark")
        db.commit()
        db.refresh(item)
        return self._serialize(item)

    def delete_item(self, db: Session, item_id: int) -> None:
        item = self._get_or_404(db, item_id)
        db.delete(item)
        db.commit()

    def _get_or_404(self, db: Session, item_id: int) -> DictionaryItem:
        item = db.get(DictionaryItem, item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="字典项不存在")
        return item

    def _serialize(self, item: DictionaryItem) -> dict:
        return {
            "id": item.id,
            "dictType": item.dict_type,
            "dictName": item.dict_name,
            "itemValue": item.item_value,
            "itemName": item.item_name,
            "sortOrder": item.sort_order,
            "enabled": item.enabled,
            "remark": item.remark,
            "createdAt": item.created_at,
            "updatedAt": item.updated_at,
        }


dictionary_service = DictionaryService()
