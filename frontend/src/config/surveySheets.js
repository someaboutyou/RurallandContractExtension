/**
 * 家庭成员变化摸底表的选项常量（2026-10-10 简化后仅成员摸底在用）。
 *
 * 《承包地变化摸底表》已改为纯现有数据推导（无录入界面、无独立存储），
 * 原 LAND_CHANGE_REASONS / FAMILY_CONTRACT_MODES 已随录入界面一并移除。
 *
 * ⛔ 与后端 `app/services/survey/sheet.py` 的常量同源（码值一致），改一处要改两处。
 */

/**
 * 表2 增减事件类型 —— 与纸质摸底表的事件列一一对应（每期增加 4 / 减少 4，共 8 类）。
 * ⛔「已补地人口」「抽回或放弃承包地」不是事件，是每期两个独立复选框
 *   （新增人口不一定补了地、减少人口不一定立即抽回；2026-10-15 用户口径），
 *   由 createEmptyMemberSheet 的 srCompensated/srWithdraw/extCompensated/extWithdraw 承载。
 * ⛔ 与后端 `app/services/survey/sheet.py::MEMBER_EVENT_TYPES` 同源（码值一致）；
 *   库里旧码（add_restore）由后端 LEGACY_EVENT_MAP 兜底归一，旧码
 *   compensated/sub_compensated/withdraw 已由迁移拆进复选列并清空事件码。
 */
export const MEMBER_EVENT_TYPES = [
  { value: "add_birth", label: "新生" },
  { value: "add_married_in", label: "婚入" },
  { value: "add_move_in", label: "迁入" },
  { value: "add_other", label: "其他增加" },
  { value: "sub_death", label: "去世" },
  { value: "sub_married_out", label: "婚出" },
  { value: "sub_move_out", label: "迁出" },
  { value: "sub_other", label: "其他减少" },
];

export const MEMBER_EVENT_MAP = Object.fromEntries(
  MEMBER_EVENT_TYPES.map((item) => [item.value, item.label])
);

/** 增加类事件码（"进"）——与后端 sheet.py::_SHEET_ADD_EVENTS 同源 */
export const ADD_EVENT_VALUES = ["add_birth", "add_married_in", "add_move_in", "add_other"];

/** 减少类事件码（"出"）——与后端 sheet.py::_SHEET_SUB_EVENTS 同源 */
export const SUB_EVENT_VALUES = ["sub_death", "sub_married_out", "sub_move_out", "sub_other"];

// ── 在户状态机（2026-10-15 用户口径：可以为空，但必须有进才有出，出了还可以再进）──
//   期初在户 ⇒ 本期只能"出"（或留空/已补地/抽回）；期初不在户 ⇒ 本期只能"进"；
//   二轮期"出"了 ⇒ 延包期还可以再"进"。列7 未填（null）时状态不可判定，不限制。

/**
 * 二轮期期初（1996 年）在户状态："in" 在户 / "out" 不在户 / null 不可判定。
 * ⛔ 期初只看列 7（isSecondRoundMember）：列 7=否时即便二轮期填了增加类，
 * 1996 时点也是"不在户"（人是在期内才进的），否则会误杀"非 1996 成员
 * 婚入/迁入"这一最常见的合法场景。增加事件只影响 presenceAtPeriod2Start。
 */
export function presenceAtPeriod1Start(sheet) {
  if (!sheet) return null;
  if (sheet.isSecondRoundMember === true) return "in";
  if (sheet.isSecondRoundMember === false) return "out";
  return null;
}

/**
 * 延包期期初（2018 年）在户状态：二轮期填了增加类 → 在户；减少类 → 不在户；
 * 否则顺延二轮期期初状态。"出了还可以再进"就落在这一层（二轮期出 → 延包期可进）。
 */
export function presenceAtPeriod2Start(sheet) {
  if (!sheet) return null;
  const ev = sheet.srEventType || "";
  if (ADD_EVENT_VALUES.includes(ev)) return "in";
  if (SUB_EVENT_VALUES.includes(ev)) return "out";
  return presenceAtPeriod1Start(sheet);
}

/** 二轮期（1996—2018）可选事件：按期初状态过滤；状态不可判定时不限制 */
export function srEventOptions(sheet) {
  return eventOptionsForState(presenceAtPeriod1Start(sheet));
}

/** 延包期（2018—2026）可选事件：按期初状态过滤；状态不可判定时不限制 */
export function extEventOptions(sheet) {
  return eventOptionsForState(presenceAtPeriod2Start(sheet));
}

function eventOptionsForState(state) {
  if (state === null) return MEMBER_EVENT_TYPES;
  return MEMBER_EVENT_TYPES.filter((opt) => {
    if (ADD_EVENT_VALUES.includes(opt.value)) return state === "out";
    if (SUB_EVENT_VALUES.includes(opt.value)) return state === "in";
    return true;
  });
}

/** 事件时间边界（2026-10-15 用户口径，与后端 sheet.py 同源）：二轮期 ≤ 2018-12-31，延包期 ≥ 2019-01-01 */
export const SR_EVENT_DATE_MAX = "2018-12-31";
export const EXT_EVENT_DATE_MIN = "2019-01-01";

/**
 * 保存前预检（前端）——与后端 sheet.py::validate_member_sheet_flow 同判据。
 * @param {Array} members 成员行数组（含 sheet 子对象）
 * @returns {string[]} 违规文案列表（逐条点名成员），空数组 = 通过
 */
export function validateMemberSheetFlow(members) {
  const problems = [];
  for (const m of members || []) {
    if (m._deleted) continue;
    const s = m.sheet;
    if (!s || typeof s !== "object") continue;
    const name = m.name || m.idNo || "未命名成员";
    const sr = s.srEventType || "";
    const ext = s.extEventType || "";
    const p1 = presenceAtPeriod1Start(s);
    const p2 = presenceAtPeriod2Start(s);
    if (p1 === "out" && SUB_EVENT_VALUES.includes(sr)) {
      problems.push(`${name}：1996 年不是家庭成员，二轮期（1996—2018）不能填减少类事件（必须有进才有出）`);
    }
    if (p1 === "in" && ADD_EVENT_VALUES.includes(sr)) {
      problems.push(`${name}：1996 年已是家庭成员，二轮期（1996—2018）不能再填增加类事件`);
    }
    if (p2 === "in" && ADD_EVENT_VALUES.includes(ext)) {
      problems.push(`${name}：截至 2018 年仍在户，延包期（2018—2026）不能填增加类事件；如系先迁出再回迁，请先在二轮期填减少类事件`);
    }
    if (p2 === "out" && SUB_EVENT_VALUES.includes(ext)) {
      problems.push(`${name}：截至 2018 年已不在户，延包期（2018—2026）不能填减少类事件；如需回迁请填增加类事件`);
    }
    // 事件时间边界（ISO 日期字符串字典序 = 时间序）
    const srDate = String(s.srEventDate || "").slice(0, 10);
    const extDate = String(s.extEventDate || "").slice(0, 10);
    if (srDate && srDate > SR_EVENT_DATE_MAX) {
      problems.push(`${name}：二轮承包期事件时间不能晚于 2018 年 12 月 31 日`);
    }
    if (extDate && extDate < EXT_EVENT_DATE_MIN) {
      problems.push(`${name}：延包期事件时间不能早于 2019 年 1 月 1 日`);
    }
  }
  return problems;
}

/** 三态（是 / 否 / 未填）下拉的通用选项（摸底弹窗各勾选项共用） */
export const YES_NO_UNSET_OPTIONS = [
  { label: "是", value: true },
  { label: "否", value: false },
  { label: "未填", value: null },
];

/**
 * 成员行 sheet 子对象的空值形态（与后端 sheet.EMPTY_MEMBER_SHEET 同构）。
 * 三态布尔用 true/false/null 承载（null = 未填）。
 */
export function createEmptyMemberSheet() {
  return {
    isSecondRoundMember: null,
    srEventType: "",
    srEventDate: null,
    srCompensated: false,
    srWithdraw: false,
    extEventType: "",
    extEventDate: null,
    extCompensated: false,
    extWithdraw: false,
    hasChange: null,
    economicRelation: "",
    hukouPlace: "",
    residencePlace: "",
    isCivilServant: null,
    isInstitutionStaff: null,
    hasEstablishment: null,
    isActiveMilitary: null,
    hasBusinessLicense: null,
    isPublicServant: null,
    remark: "",
  };
}

/**
 * 成员摸底是否填过任意一项（列表页"已摸底"标记 / 弹窗折叠标题共用判据）。
 * 三态布尔按"非 null 即填过"算；字符串字段按非空算。
 */
export function memberSheetFilled(sheet) {
  if (!sheet || typeof sheet !== "object") return false;
  return Boolean(
    sheet.isSecondRoundMember !== null ||
      sheet.srEventType ||
      sheet.srEventDate ||
      sheet.extEventType ||
      sheet.extEventDate ||
      sheet.srCompensated ||
      sheet.srWithdraw ||
      sheet.extCompensated ||
      sheet.extWithdraw ||
      sheet.economicRelation ||
      String(sheet.hukouPlace || "").trim() ||
      String(sheet.residencePlace || "").trim() ||
      sheet.isInstitutionStaff !== null ||
      sheet.isCivilServant !== null ||
      String(sheet.remark || "").trim(),
  );
}
