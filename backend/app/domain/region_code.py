"""数据权限区域编码的共用规则（后端侧，权威实现）。

⛔ 覆盖判定**只按严格前缀**，因为鉴权就是这么判的：
   `data_access_service.ensure_code_in_scope` → `normalized.startswith(permission.region_code)`。
   于是「勾了某个节点」= 该节点整棵子树都被授权，保存时被祖先覆盖的 code 全是冗余。

⚠️ 省级不能当成覆盖：省码是「2 位省码 + 0000」（江苏省 320000），县码是 321324，
   `"321324".startswith("320000")` 为假 —— 勾省在鉴权上授不到任何县。所以：
   - `region_code_covers` 不含省级特例；
   - `collapse_region_codes` 里额外要求「父码确实是全部子码的前缀」，省级父子关系因此不会塌缩。

前端同规则实现：`frontend/src/utils/regionCode.js`，改一边必须改另一边。
"""

from collections.abc import Iterable, Mapping

PROVINCE_CODE_PATTERN_LENGTH = 6


def region_code_covers(ancestor_code: str | None, code: str | None) -> bool:
    """ancestor_code 是否覆盖 code（严格前缀；自身不算覆盖自身）。"""
    ancestor = (ancestor_code or "").strip()
    target = (code or "").strip()
    if not ancestor or not target or ancestor == target:
        return False
    return len(ancestor) < len(target) and target.startswith(ancestor)


def find_covering_code(target_code: str | None, codes: Iterable[str]) -> str | None:
    """从 codes 里找出覆盖 target_code 的那个（最长前缀优先），找不到返回 None。"""
    target = (target_code or "").strip()
    if not target:
        return None
    matched: str | None = None
    for raw in codes:
        code = (raw or "").strip()
        if not region_code_covers(code, target):
            continue
        if matched is None or len(code) > len(matched):
            matched = code
    return matched


def drop_redundant_region_codes(codes: Iterable[str]) -> list[str]:
    """去重 + 去掉被其它已选 code 覆盖的项，保持首次出现的顺序。"""
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = (raw or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return [code for code in ordered if not any(region_code_covers(other, code) for other in ordered)]


def collapse_region_codes(codes: Iterable[str], parent_by_code: Mapping[str, str]) -> list[str]:
    """把「子孙全选」塌缩成父节点一行。

    自底向上处理（码越长越深，先合并组→村，再村→镇，再镇→县）。只在
    **父码确实是全部子码的前缀**时塌缩 —— 省级的「320000 / 321324」父子关系
    （以及 `auto-province` 占位）不满足该条件，因此不会被塌缩掉。
    """
    selected = list(drop_redundant_region_codes(codes))
    selected_set = set(selected)
    if not selected_set:
        return []

    children_by_parent: dict[str, list[str]] = {}
    for code, parent in parent_by_code.items():
        if parent and parent in parent_by_code:
            children_by_parent.setdefault(parent, []).append(code)

    # 深码（组/村/镇）先合并，短码（县）后合并，顺序错会漏掉连锁塌缩。
    for parent in sorted(children_by_parent, key=len, reverse=True):
        children = children_by_parent[parent]
        if not children or not all(child in selected_set for child in children):
            continue
        if not all(child.startswith(parent) for child in children):
            continue
        for child in children:
            selected_set.discard(child)
        selected_set.add(parent)

    # 塌缩后可能重新出现「祖先 + 后代」并存，再去一次冗余。
    ordered = [code for code in selected if code in selected_set]
    ordered.extend(sorted(code for code in selected_set if code not in ordered))
    return drop_redundant_region_codes(ordered)


def normalize_region_codes(codes: Iterable[str], parent_by_code: Mapping[str, str] | None = None) -> list[str]:
    """保存前的归一化总入口。

    parent_by_code 为空时只做去冗余（纯编码规则，不查库）；给了父映射（regions 表来的）才做塌缩。
    """
    if not parent_by_code:
        return drop_redundant_region_codes(codes)
    return collapse_region_codes(codes, parent_by_code)
