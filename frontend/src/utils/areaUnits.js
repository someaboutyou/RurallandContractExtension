/**
 * 面积单位换算（2026-11-04 统一口径）。
 *
 * 定案：数据库与所有 API 的 scmj / htmj / newScmj 一律为平方米（㎡）——
 * 与历史导入数据、打印出件（后端 sheet.py / contract_template_service.py ÷666.67）、
 * NY/T 2539 导出同口径。
 *
 * 调查录入等界面一律用「亩」输入与显示，换算只发生在界面边界（本模块）。
 * ⛔ 不要绕过本模块直接写 666.67 常量；⛔ 后端字段语义不要在界面层再改。
 */
export const SQM_PER_MU = 666.6666667;

/** ㎡ → 亩（保留 digits 位小数；非有限数返回 null） */
export function sqmToMu(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return Number((num / SQM_PER_MU).toFixed(digits));
}

/** 亩 → ㎡（保留 digits 位小数；非有限数返回 null） */
export function muToSqm(value, digits = 2) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return Number((num * SQM_PER_MU).toFixed(digits));
}

/** 显示用：㎡ 值转「X 亩」文案；空值/非法值显示占位符 */
export function formatSqmsAsMu(value, placeholder = "-") {
  if (value === undefined || value === null || value === "") return placeholder;
  const mu = sqmToMu(value);
  return mu === null ? placeholder : `${mu} 亩`;
}
