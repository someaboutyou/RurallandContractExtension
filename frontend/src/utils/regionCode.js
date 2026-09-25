/**
 * 数据权限区域编码的共用规则（前端侧）。
 *
 * ⛔ 判定「一个已选 code 是否覆盖另一个 code」必须**只按严格前缀**，因为后端鉴权就是这么判的：
 *    `data_access_service.ensure_code_in_scope` → `normalized.startswith(permission.region_code)`。
 *    换句话说「勾了某个节点」在业务上 = 该节点整棵子树都被授权，所以保存时被祖先覆盖的 code
 *    全部是冗余的，可以直接丢掉。
 *
 * ⚠️ 省级是特例，且**不能**当成覆盖：省码是「2 位省码 + 0000」（江苏省 320000），
 *    而县码是 321324 —— `'321324'.startsWith('320000') === false`。
 *    所以「勾江苏省」在鉴权上其实什么都授不到。三态显示里为了让用户看得出
 *    「我的选择在江苏省下面」而按前 2 位做了一次**纯视觉**的提示，那只是展示，不能参与归一化。
 *
 * 后端同规则实现：`backend/app/domain/region_code.py`，改一边必须改另一边。
 */

const PROVINCE_CODE_PATTERN = /^\d{2}0000$/;

/** ancestorCode 是否覆盖 code（严格前缀；自身不算覆盖自身）。 */
export function regionCodeCovers(ancestorCode, code) {
  const ancestor = String(ancestorCode ?? "").trim();
  const target = String(code ?? "").trim();
  if (!ancestor || !target || ancestor === target) {
    return false;
  }
  return ancestor.length < target.length && target.startsWith(ancestor);
}

/** 省级展示用：code 是否为「2 位省码 + 0000」形式的省码。 */
export function isProvinceCode(code) {
  return PROVINCE_CODE_PATTERN.test(String(code ?? "").trim());
}

/**
 * 归一化：去掉被其它已选 code 覆盖的项（去冗余）。
 * 保持首次出现的顺序，顺便去重、去空白。
 */
export function normalizeRegionCodes(codes) {
  const ordered = [];
  const seen = new Set();
  for (const raw of codes || []) {
    const code = String(raw ?? "").trim();
    if (!code || seen.has(code)) continue;
    seen.add(code);
    ordered.push(code);
  }
  return ordered.filter((code) => !ordered.some((other) => regionCodeCovers(other, code)));
}

/**
 * 从候选 code 列表里找出覆盖 targetCode 的那个（最深/最长前缀优先）。
 * 找不到返回 null —— 说明该节点既没被选也没被上级覆盖。
 */
export function findCoveringCode(targetCode, codes) {
  const target = String(targetCode ?? "").trim();
  if (!target) return null;
  let matched = null;
  for (const raw of codes || []) {
    const code = String(raw ?? "").trim();
    if (!regionCodeCovers(code, target)) continue;
    if (matched === null || code.length > matched.length) {
      matched = code;
    }
  }
  return matched;
}
