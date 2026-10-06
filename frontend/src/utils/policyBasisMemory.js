/**
 * 政策依据记忆。
 *
 * 「政策依据」是延包调查里必须留档备查的政策法规凭据，程序无从推断，只能人工填写。
 * 但同一批次、同一村组的合户 / 分户往往依据同一份文件（如某号文件、某次村民会议决议），
 * 每次重敲一遍没有意义 —— 这里记住上一次填过的值，下次打开弹窗自动带出。
 *
 * ⛔ 只做「带出」不做「自动提交」：用户仍能看到并修改它，别让程序替他认定依据。
 */
const STORAGE_KEY = "survey.policyBasis.last";

export function loadPolicyBasis() {
  try {
    return localStorage.getItem(STORAGE_KEY) || "";
  } catch {
    // 隐私模式 / 存储被禁用时静默降级为空
    return "";
  }
}

export function savePolicyBasis(value) {
  try {
    const text = String(value || "").trim();
    if (text) localStorage.setItem(STORAGE_KEY, text);
  } catch {
    /* 忽略：记不住不影响本次提交 */
  }
}
