/**
 * 「调查员 / 调查日期」默认取**本次**（当前登录用户 + 当天）的统一口径。
 *
 * 为什么需要它：`survey_cbf_result` / `survey_fbf_result` 是按承包方 / 发包方**全局唯一**的行，
 * 建批次时整行抄进 `*_base` 快照（见 `backend/app/services/survey/batch.py`），调查员 / 调查日期
 * 一并抄过来。于是打开录入弹窗时看到的是**上一次**的调查痕迹（上一批次 / 导入的历史成果），
 * 调查员得逐户手改 —— 用户报的就是这个。
 *
 * 口径（承包方侧 `ContractorResultDialog.vue` 与发包方侧 `IssuerSurveyDialog.vue` **共用**，
 * 两处不许各写一套 —— 同源才好一起改）：
 *   1. 填**本次**：调查员 = 当前登录用户姓名；调查日期 = 当天；
 *   2. 只在这一户 / 这个发包方于本批次**还没被改过**时才填：当前值仍等于批次快照 `*_base` 的值，
 *      或压根没有快照行（分户 / 合户新生成的户就是这种）；
 *      已被改过（≠ 快照值）的一律不动，避免覆盖别人已经录进去的成果；
 *   3. **只读时什么都不填**（不可写 / 批次已结束 / 已确认）：默认值是给录入用的，
 *      凭空写进只读视图会多出假的"已变化"高亮。
 *
 * ⛔ 注意：`cbfdcy/cbfdcrq`、`fbfdcy/fbfdcrq` 属于**权属变化**判定字段
 * （`result.py::_contractor_changed` / `_issuer_changed` 与 `changes.py` 的
 * `contractor_fields` / `issuer_fields`）。填上本次值后一保存，该户 `is_changed` 会变 True、
 * 变化详情多出两条差异、台账「是否变化」列变"是"。这是**有意保留**的口径（用户 2026-09-27 明确），
 * 不要"顺手"把这两个字段从上面几张表里摘掉。
 */

/** 当天日期（YYYY-MM-DD，本地时区）。 */
export function todayIso() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** 当前登录用户姓名（未登录时返回空串，避免把"未登录"写进数据）。 */
export function currentSurveyorName(displayName) {
  const name = String(displayName || "").trim();
  return name === "未登录" ? "" : name;
}

/** 当前值是否仍等于批次快照值（含"当前为空"与"没有快照"两种情况都算"没被改过"）。 */
export function isStillBaseline(value, baseValue) {
  const current = String(value ?? "").trim();
  if (!current) return true;
  return current.slice(0, 10) === String(baseValue ?? "").trim().slice(0, 10);
}

/**
 * 把「本次」的默认值写入表单（就地改 `form`）。
 * @param {object} form 含 `surveyorName` / `surveyDate` 字段的响应式表单
 * @param {{base?: object|null, readonly?: boolean, displayName?: string}} options
 *        `base` 传批次快照对象（`baseContractor` / `baseIssuer`），无快照传 null
 * @returns {boolean} 是否写入过（仅用于调用处按需判断，无副作用）
 */
export function applySurveyActorDefaults(form, { base = null, readonly = false, displayName = "" } = {}) {
  if (!form || readonly) return false;
  let touched = false;
  const name = currentSurveyorName(displayName);
  if ((!base || isStillBaseline(form.surveyorName, base.surveyorName)) && name) {
    form.surveyorName = name;
    touched = true;
  }
  if (!base || isStillBaseline(form.surveyDate, base.surveyDate)) {
    form.surveyDate = todayIso();
    touched = true;
  }
  return touched;
}
