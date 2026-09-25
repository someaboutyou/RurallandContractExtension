// 身份证/证件号码校验的离线验收：直接跑纯函数，不需要起服务、不碰数据库。
//   node scripts/_verify_idno_validator.mjs
//
// 期望值来源：
//   - OK-D / OK-M / OK-X 三条是库里真实存在、校验位正确的号码（取自 survey_cbf_result）；
//   - 320827194101104423 是库里真实存在、校验位不正确的号码（探测脚本已确认）；
//   - 其余边界值按 GB 11643 手工演算（见各用例注释）。
import {
  ID_NO_MAX_LENGTH,
  diagnoseChinaId,
  evaluateIdNoIssue,
  validateChinaId,
} from "../frontend/src/utils/validators.js";

let failed = 0;
let passed = 0;

function check(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    passed += 1;
    return;
  }
  failed += 1;
  console.log(`  ✗ ${name}\n      期望 ${JSON.stringify(expected)}\n      实际 ${JSON.stringify(actual)}`);
}

function checkCode(name, value, expected, options) {
  check(`diagnoseChinaId(${JSON.stringify(value)}) → code`, diagnoseChinaId(value, options).code, expected);
}

console.log("== diagnoseChinaId：格式 / 地区码 / 出生日期 / 校验位 ==");
// 真实库样本：320827196502040391（承包方）、321324197507260229（成员）、32082719630820521X（末位 X）
checkCode("真实库合法号码", "320827196502040391", "");
checkCode("真实库合法号码（成员）", "321324197507260229", "");
checkCode("真实库合法号码（末位 X）", "32082719630820521X", "");
checkCode("末位小写 x 同样接受", "32082719630820521x", "");
checkCode("真实库校验位错误的号码", "320827194101104423", "checksum");
checkCode("空值", "", "empty");
checkCode("纯空白", "   ", "empty");
checkCode("首尾空格自动 trim", "  320827196502040391  ", "");
checkCode("17 位（未输完）", "32082719650204039", "length");
checkCode("17 位 + incompleteOk", "32082719650204039", "", { incompleteOk: true });
checkCode("10 位 + incompleteOk", "3208271965", "", { incompleteOk: true });
checkCode("10 位（保存时）", "3208271965", "length");
checkCode("19 位", "3208271965020403911", "length");
// 地区码：前两位必须是省级代码，99 / 00 都不存在。
checkCode("地区码 99 无效", "990827196502040391", "province");
checkCode("地区码 00 无效", "000827196502040391", "province");
// 出生日期：1965 不是闰年，2 月只有 28 天；月份 02 配上「32 日」也不存在。
checkCode("非闰年的 2 月 29 日", "320827196502290391", "birthday");
checkCode("不存在的 2 月 32 日", "320827196502320391", "birthday");
checkCode("月份 13", "320827196513040391", "birthday");
checkCode("年份 0000", "320827000002040391", "birthday");
// 字符集：只能数字，且 X 只允许出现在末位。
checkCode("中间夹字母 A", "32082719650204039A", "charset");
checkCode("中间夹 X", "3208271965X2040391", "charset");
checkCode("中间夹空格", "3208271965 2040391", "charset");
// 15 位老式身份证：年份一律 19xx。
checkCode("15 位合法", "110101900307231", "");
checkCode("15 位日期非法", "110101900237231", "birthday");
checkCode("15 位地区码非法", "990101900307231", "province");

console.log("== evaluateIdNoIssue：新录入值从严、历史值降级为提示 ==");
// 校验位有误的历史值：只要没被改动过，就只提示不阻断，否则存量数据会被锁死。
check("历史值 + 校验位有误 → warn", evaluateIdNoIssue("1", "320827194101104423", { changed: false })?.level, "warn");
check("本次改动的值 + 校验位有误 → error", evaluateIdNoIssue("1", "320827194101104423", { changed: true })?.level, "error");
// 长度、字符、地区码、出生日期属于"一眼错"，无论新旧都拦。
check("历史值 + 地区码无效 → error", evaluateIdNoIssue("1", "990827196502040391", { changed: false })?.level, "error");
check("历史值 + 日期无效 → error", evaluateIdNoIssue("1", "320827196502290391", { changed: false })?.level, "error");
// 非身份证不限格式，只查非空与长度。
check("户口簿号任意字符 → 不提示", evaluateIdNoIssue("2", "户字第 001 号/张某", { changed: true }), null);
check("军官证号 → 不提示", evaluateIdNoIssue("3", "南字第1234567号", { changed: true }), null);
check("非身份证 + 超长 → error", evaluateIdNoIssue("2", "X".repeat(ID_NO_MAX_LENGTH + 1), { changed: true })?.level, "error");
// 空值：界面即时提示时不报（避免一打开就满屏红），保存时必须报。
check("空值 + 不要求必填 → 不提示", evaluateIdNoIssue("1", "", { requireValue: false }), null);
check("空值 + 要求必填 → error", evaluateIdNoIssue("1", "", { requireValue: true })?.level, "error");
// 超长：后端 schema 是 max_length=20，超了会被 422，前端先拦。
check("超过 20 位 → error", evaluateIdNoIssue("1", "1".repeat(ID_NO_MAX_LENGTH + 1), { changed: true })?.level, "error");
// 边输入边提示：长度没输够不报错；保存前校验则报错。
check("未输完 + incompleteOk → 不提示", evaluateIdNoIssue("1", "320827196502", { incompleteOk: true }), null);
check("未输完 + 保存校验 → error", evaluateIdNoIssue("1", "320827196502", { incompleteOk: false })?.level, "error");

console.log("== 回归：既有 validateChinaId 行为未变（4 个页面在用它）==");
check("validateChinaId 合法号", validateChinaId("320827196502040391"), true);
check("validateChinaId 校验位错但形式合法 → 仍为 true", validateChinaId("320827194101104423"), true);
check("validateChinaId 17 位", validateChinaId("32082719650204039"), false);
check("validateChinaId 15 位", validateChinaId("110101900307231"), true);
check("validateChinaId 非数字", validateChinaId("户字第001号"), false);
check("ID_NO_MAX_LENGTH 与后端 max_length 对齐", ID_NO_MAX_LENGTH, 20);

console.log(`\n通过 ${passed} 项，失败 ${failed} 项`);
process.exit(failed ? 1 : 0);
