export const MOBILE_REGEX = /^1[3-9]\d{9}$/;
export const CHINA_ID_REGEX = /(^\d{15}$)|(^\d{17}[\dXx]$)/;
export const POSTCODE_REGEX = /^\d{6}$/;

/** 证件号码最大长度：与后端 schema（`Field(max_length=20)`）一致，超出会被 422 拒绝。 */
export const ID_NO_MAX_LENGTH = 20;

export function validateMobile(value) {
  return MOBILE_REGEX.test(String(value).trim());
}

export function validateChinaId(value) {
  return CHINA_ID_REGEX.test(String(value).trim());
}

export function validatePostcode(value) {
  return POSTCODE_REGEX.test(String(value).trim());
}

// ---- 身份证深度校验 ----
// `validateChinaId` 只判断"长得像不像"（15 位或 17 位+校验位），供既有页面沿用；
// 下面这组函数额外验算地区码、出生日期与 GB 11643 校验位，
// 用于承包方调查录入这类对号码准确性要求高的场景。

const ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
const ID_CHECK_CODES = "10X98765432";
// GB/T 2260 省级行政区划前两位（含中国台湾 71、中国香港 81、中国澳门 82）。
const PROVINCE_CODES = new Set([
  "11", "12", "13", "14", "15",
  "21", "22", "23",
  "31", "32", "33", "34", "35", "36", "37",
  "41", "42", "43", "44", "45", "46",
  "50", "51", "52", "53", "54",
  "61", "62", "63", "64", "65",
  "71", "81", "82",
]);

/** 判断是否真实存在的日历日期（含闰年与各月天数）。 */
function isCalendarDate(year, month, day) {
  if (!Number.isInteger(year) || month < 1 || month > 12 || day < 1) {
    return false;
  }
  const date = new Date(year, month - 1, day);
  return (
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day
  );
}

function diagnoseId18(value) {
  if (!PROVINCE_CODES.has(value.slice(0, 2))) {
    return { code: "province", message: "身份证号前 2 位地区码无效" };
  }
  const year = Number(value.slice(6, 10));
  const month = Number(value.slice(10, 12));
  const day = Number(value.slice(12, 14));
  if (year < 1900 || !isCalendarDate(year, month, day)) {
    return { code: "birthday", message: "身份证号中的出生日期无效" };
  }
  let total = 0;
  for (let i = 0; i < 17; i += 1) {
    total += Number(value[i]) * ID_WEIGHTS[i];
  }
  if (ID_CHECK_CODES[total % 11] !== value[17].toUpperCase()) {
    return { code: "checksum", message: "身份证号校验位不正确，请核对后重新输入" };
  }
  return { code: "", message: "" };
}

function diagnoseId15(value) {
  if (!PROVINCE_CODES.has(value.slice(0, 2))) {
    return { code: "province", message: "身份证号前 2 位地区码无效" };
  }
  // 15 位号码的出生年份一律为 19xx。
  const year = 1900 + Number(value.slice(6, 8));
  const month = Number(value.slice(8, 10));
  const day = Number(value.slice(10, 12));
  if (!isCalendarDate(year, month, day)) {
    return { code: "birthday", message: "身份证号中的出生日期无效" };
  }
  return { code: "", message: "" };
}

/**
 * 诊断身份证号。
 *
 * @returns {{ code: string, message: string }} `code` 为空串表示通过，否则为
 *   `empty` / `charset` / `length` / `province` / `birthday` / `checksum`。
 *
 * @param {string} value 待校验值（会自动 trim）
 * @param {{ incompleteOk?: boolean }} [options] `incompleteOk` 为真时，
 *   长度不足 15 / 18 位的"还没输完"状态不判错（用于边输入边提示的场景）。
 */
export function diagnoseChinaId(value, options = {}) {
  const { incompleteOk = false } = options;
  const text = String(value ?? "").trim();
  if (!text) {
    return { code: "empty", message: "请输入证件号码" };
  }
  // X 只允许出现在末位，所以先摘掉末位再要求其余各位全为数字。
  if (/[^0-9]/.test(text.replace(/[Xx]$/, ""))) {
    return { code: "charset", message: "身份证号只能包含数字，末位可为 X" };
  }
  if (text.length < 15) {
    if (incompleteOk) return { code: "", message: "" };
    return { code: "length", message: "身份证号应为 18 位（末位可为 X）或 15 位" };
  }
  if (text.length === 15) {
    return diagnoseId15(text);
  }
  if (text.length < 18) {
    if (incompleteOk) return { code: "", message: "" };
    return { code: "length", message: "身份证号应为 18 位（末位可为 X）或 15 位" };
  }
  if (text.length > 18) {
    return { code: "length", message: "身份证号应为 18 位（末位可为 X）或 15 位" };
  }
  return diagnoseId18(text);
}

/** 身份证号校验位不符时的判定码，独立出来是因为它有特殊的分档口径。 */
const CHECKSUM_CODE = "checksum";

/**
 * 评估证件号码的录入问题（业务口径，供表单即时提示与保存前拦截共用）。
 *
 * 三档口径，避免"本次新录入的值"与"库里的历史值"一刀切：
 *   1. 空值 / 超长 / 身份证格式问题（长度、字符、地区码、出生日期）→ 一律 error；
 *   2. 身份证校验位不符 → 本次新录入或改动过的值判 error（阻断保存）；
 *      未改动的历史值只给 warn，否则库内那批校验位有误的存量数据会被锁死，
 *      连改个联系电话都保存不了；
 *   3. 非身份证（户口簿、军官证等）只校验非空与长度，不限定格式。
 *
 * @param {string|number} idType 证件类型，`"1"` 表示居民身份证
 * @param {string} value 证件号码
 * @param {{ requireValue?: boolean, changed?: boolean, incompleteOk?: boolean }} [options]
 *   `requireValue` 为真时空值也报错（保存前用）；`changed` 表示该值本次是否
 *   新录入或改动过（默认视为改动）；`incompleteOk` 为真时"还没输完"的长度不报错。
 * @returns {{ level: "error" | "warn", message: string } | null} null 表示无需提示
 */
export function evaluateIdNoIssue(idType, value, options = {}) {
  const { requireValue = false, changed = true, incompleteOk = false } = options;
  const text = String(value ?? "").trim();
  if (!text) {
    return requireValue ? { level: "error", message: "请输入证件号码" } : null;
  }
  if (text.length > ID_NO_MAX_LENGTH) {
    return { level: "error", message: `证件号码不能超过 ${ID_NO_MAX_LENGTH} 位` };
  }
  if (String(idType) !== "1") return null;
  const { code, message } = diagnoseChinaId(text, { incompleteOk });
  if (!code) return null;
  if (code === CHECKSUM_CODE && !changed) {
    return { level: "warn", message: "身份证号校验位不正确，请核对（历史数据可沿用）" };
  }
  return { level: "error", message };
}
