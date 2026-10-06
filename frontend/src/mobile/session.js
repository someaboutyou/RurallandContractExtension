/**
 * 移动端登录会话辅助：「记住账号密码」与「主动退出」的仲裁。
 *
 * 背景（2026-10-04 事故）：MobileLoginView 的 onMounted 会在发现已保存凭据时
 * **自动重新登录**。于是「退出登录」的实际流程是：
 *   清 token → 跳登录页 → 登录页自动重登 → 跳回「我的待调查」
 * 用户看到的就是"退出没成功，还能查数据"。
 *
 * 仲裁规则：
 * - **主动退出**时写 sessionStorage 标记 ⇒ 本次页面会话内登录页只预填、不自动登录；
 * - 标记用 sessionStorage 而非 localStorage：杀掉 App 重开后标记自动消失，
 *   冷启动的自动登录（记住账号密码的本意）不受影响；
 * - 用户手动点一次「登录」即清除标记，之后本会话内再进登录页恢复自动登录语义。
 */

export const CREDENTIALS_KEY = "rural_land_mobile_credentials";
const MANUAL_LOGOUT_KEY = "rural_land_manual_logout";

/** 主动退出登录时调用：本会话内禁止自动登录 */
export function markManualLogout() {
  try {
    sessionStorage.setItem(MANUAL_LOGOUT_KEY, "1");
  } catch {
    /* sessionStorage 不可用时退化为"允许自动登录"，不影响主流程 */
  }
}

/** 登录页 onMounted 判断：是否因主动退出而跳过自动登录 */
export function isManualLogoutPending() {
  try {
    return sessionStorage.getItem(MANUAL_LOGOUT_KEY) === "1";
  } catch {
    return false;
  }
}

/** 手动登录成功后调用：恢复本会话内的自动登录语义 */
export function clearManualLogout() {
  try {
    sessionStorage.removeItem(MANUAL_LOGOUT_KEY);
  } catch {
    /* 忽略 */
  }
}
