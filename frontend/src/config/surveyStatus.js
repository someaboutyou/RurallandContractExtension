// 调查成果状态集合 —— 前端的唯一来源。
//
// ⛔ 与后端 `backend/app/services/survey/base.py::SurveyServiceBase` 上的
//    `confirmable_survey_statuses` / `terminal_survey_statuses` **必须同源**：
//      · 服务端「确认调查结果」的准入集合（`task.py::confirm_result`）
//      · `/surveys` 列表行的「确认」按钮（`SurveyView.vue`）
//      · 录入弹窗的「确认调查结果」按钮（`ContractorResultDialog.vue`）
//    三处消费同一份定义。改一边就必须改另一边。
//
// 历史事故（2026-09-27 定位）：前端只认 `'surveyed'`，后端却认
// `{surveyed, changed, unchanged}` ⇒ 有变化（changed / unchanged）的户
// **后端放行、界面根本不给点**，功能静默死锁，用户看到的就是
// 「保存了调查结果，列表里却没有确认按钮」。反向（界面能点、保存 403）
// 同样是同源性问题，两条都要防。
//
// ⛔ 别和「已调查」的**统计**口径混用：统计口径还包含 `confirmed`
// （后端 `SURVEYED_TASK_STATUSES`），那是"录过了"，这里是"录了但还没定案"。

/** 可以「确认调查结果」的成果状态（已录入、未定案）。 */
export const CONFIRMABLE_SURVEY_STATUSES = ["surveyed", "changed", "unchanged"];

/** 定案态：只能由「确认调查结果」「跳过」两个动作写入，保存不得回退。 */
export const TERMINAL_SURVEY_STATUSES = ["confirmed", "skipped"];

/**
 * 编辑闸门：处于这些状态的成果**已定案，不许再改数据**（表单只读、保存接口 400）。
 *
 * ⛔ 它**不等于** `TERMINAL_SURVEY_STATUSES`：`skipped`（跳过）属于定案态，
 *   但跳过之后仍然允许补录（现有口径），所以编辑闸门只有 `confirmed`。
 *   两个集合不能互相替换 —— 换成定案态集合会让跳过的户在前端被锁死、
 *   后端却仍然放行，又是「界面挡着、请求发不出去」那类同源事故。
 *
 * 与后端 `base.py::SurveyServiceBase.locked_survey_statuses` 同源（逐元素相等）。
 * 消费方：`IssuerSurveyDialog.vue`（发包方表单只读判定 + 保存按钮显示条件）。
 */
export const LOCKED_SURVEY_STATUSES = ["confirmed"];
