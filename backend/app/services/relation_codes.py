# -*- coding: utf-8 -*-
"""「与户主关系」（`yhzgx`）码值的**单一口径**。

为什么需要这个模块
------------------
字典 `nyt2539_c20_relation_to_head`（`dictionary_presets.py` + `dictionary_items` 表）
权威定义：

    ``01`` 本人、``02`` **户主**、``10`` 配偶、``20`` 子、``30`` 女、……

真实数据也如此 —— `survey_cbf_jtcy_result.yhzgx='02'` 有 **17.98 万**条
（**每户恰好一条**），`'01'` 只有 1 条。

但历史上代码到处按 ``01 = 户主`` 实现（裸比较 ``yhzgx == "01"`` 出现在
`contractor_service` / `survey/base` / `survey/household` / 契约出件等多个文件里），
后果四条：

1. `survey_cbf_jtcy_result.is_household_head` 全库**只有 1 条**为 true；
2. `survey/base.py::_validate_confirmable` 要求「恰好 1 个户主」而判据取 ``01``
   ⇒ 179,788 个 `cbflx=1` 的户里**只有 1 户**能通过
   ⇒ **「确认调查结果」对真实户几乎全部 400**（实测）；
3. 合户 / 分户把新户户主写成 ``01``，与存量户的 ``02`` 并存
   ⇒ **同一个户里出现两个"户主"**；
4. 合同出件（`contract_template_service` 的 `YHZGX_MAP`）把 ``02`` 印成"配偶"。

定案口径（2026-09-25 用户拍板）
------------------------------
    优先「户主」(``02``) → 次选「本人」(``01``) → 都没有则**兜底取第一条成员**。

由此推论：**只要这一户有成员，就一定能判定出唯一户主**，
所以"户主校验"只应在"一个成员都没有"时失败。

使用约束
--------
⛔ 凡需要判断"谁是户主 / 某人是不是户主"的地方**一律调用本模块**，
不要再写 ``== "01"`` / ``== "02"`` 的裸比较 —— 这正是历史上口径走偏的成因。
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.dictionary_presets import NYT2539_APPENDIX_C_DICTIONARY_ITEMS
from app.models.dictionary import DictionaryItem

#: 与户主关系代码表的字典类型
RELATION_DICT_TYPE = "nyt2539_c20_relation_to_head"

#: 字典里「户主」的码值
HEAD_RELATION_VALUE = "02"

#: 字典里「本人」的码值（无户主时的次选）
SELF_RELATION_VALUE = "01"

#: 判定户主的优先顺序（定案口径）
HEAD_RELATION_PRIORITY: tuple[str, ...] = (HEAD_RELATION_VALUE, SELF_RELATION_VALUE)

#: 兜底展示映射：**直接从字典预设派生**，避免再维护第二份真相。
FALLBACK_RELATION_LABELS: dict[str, str] = {
    code: name
    for dict_type, _dict_name, code, name, _sort_order, _remark in NYT2539_APPENDIX_C_DICTIONARY_ITEMS
    if dict_type == RELATION_DICT_TYPE
}


def normalize_relation_code(value: Any) -> str:
    """把落库/传参的码值规整成去空白的字符串（兼容 int、None）。"""
    if value is None:
        return ""
    return str(value).strip()


def is_head_relation(value: Any) -> bool:
    """该关系码是否可视为「户主」（``02`` 户主 或 ``01`` 本人）。"""
    return normalize_relation_code(value) in HEAD_RELATION_PRIORITY


def pick_household_head(members: Iterable[Any] | None):
    """按定案口径从成员集合里挑出户主。

    **优先级**（第二条起的四条，即本次定案口径）：

    1. 显式标记 ``is_household_head=True`` —— 这是**应用自己**记录的"谁是户主"
       （变更户主 / 分户 / 合户 / 维护成员 都会写它）。它必须先于码值推断，
       否则合户后新户指定的户主会被从原户带过来的 ``02`` 覆盖掉。
    2. ``yhzgx == "02"``（字典：**户主**）
    3. ``yhzgx == "01"``（字典：本人）
    4. 兜底：第一条成员

    返回被挑中的成员对象；集合为空时返回 ``None``。
    不修改任何成员，纯读取 —— 校验 / 展示等只读场景可直接调用。
    """
    items = [m for m in (members or [])]
    designated = [m for m in items if bool(getattr(m, "is_household_head", False))]
    if designated:
        return designated[0]
    for code in HEAD_RELATION_PRIORITY:
        for member in items:
            if normalize_relation_code(getattr(member, "yhzgx", None)) == code:
                return member
    return items[0] if items else None


def pick_household_head_code(members: Iterable[Any] | None) -> str:
    """同 :func:`pick_household_head`，但只返回其关系码（空集合返回 ``""``）。"""
    head = pick_household_head(members)
    if head is None:
        return ""
    return normalize_relation_code(getattr(head, "yhzgx", None))


def sync_household_head_flags(members: Iterable[Any] | None, *, head: Any | None = None):
    """把 ``is_household_head`` 收敛到**唯一一人**，并返回该成员。

    ``members`` 通常是 ORM 成员对象列表（属性会被就地改写，由调用方负责 commit）。
    显式传 ``head`` 时以它为准则（用于"操作本已指定户主"的场景）。
    """
    items = [m for m in (members or [])]
    if head is None:
        head = pick_household_head(items)
    for member in items:
        member.is_household_head = member is head
    return head


#: 字典里 `80` = 其他。用于"关系已无从考证"的兜底改写（见下）。
NEUTRAL_RELATION_VALUE = "80"


def normalize_non_head_relations(members: Iterable[Any] | None, head: Any) -> int:
    """把**非户主**成员身上残留的"户主类"关系码收敛为 ``80``（其他），返回改写条数。

    典型场景是**合户**：A、B 两户各自有一个 ``yhzgx='02'`` 的户主，成员整体并入新户后，
    若原样保留，新户里就会同时出现多个"户主"（这正是用户报的现象）。
    这两个人相对**新户主**的关系无从推断，写"配偶/子女"都是臆造，
    故取字典中语义诚实的 ``80 其他``；真正的户主由 ``head`` 指定为 ``02``。
    """
    changed = 0
    for member in members or []:
        if member is head:
            continue
        if is_head_relation(getattr(member, "yhzgx", None)):
            member.yhzgx = NEUTRAL_RELATION_VALUE
            changed += 1
    return changed


def head_relation_after_change(new_head_relation: Any, old_head_relation: Any) -> str:
    """变更户主时，**原户主**该改成什么关系码？

    做法是"对调"：原户主继承新户主原先的关系；若新户主原先也是户主类码
    （``02``/``01``，说明双方都无有效关系描述），则收敛为 ``10``（配偶）——
    这样能保证**一个户里只有一个户主类码**，与本模块的判定口径自洽。
    """
    new_code = normalize_relation_code(new_head_relation)
    old_code = normalize_relation_code(old_head_relation)
    if not is_head_relation(old_code):
        return old_code
    if not is_head_relation(new_code):
        return new_code
    return "10"


def relation_labels(db: Session) -> dict[str, str]:
    """展示口径：``{码值: 名称}``。

    优先取字典（与前端 `useDictionary` 同源）；字典整类为空或全被停用时，
    退回 :data:`FALLBACK_RELATION_LABELS`（内容与字典预设一致）。
    """
    rows = db.execute(
        select(DictionaryItem.item_value, DictionaryItem.item_name)
        .where(
            DictionaryItem.dict_type == RELATION_DICT_TYPE,
            DictionaryItem.enabled.is_(True),
        )
        .order_by(DictionaryItem.sort_order.asc(), DictionaryItem.item_value.asc())
    ).all()
    labels = {normalize_relation_code(value): name for value, name in rows if value}
    return labels or dict(FALLBACK_RELATION_LABELS)
