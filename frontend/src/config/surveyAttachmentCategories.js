/**
 * 调查附件类别（`/surveys` → 承包方调查录入 → 调查附件 & 转业业务申请）。
 *
 * **类别清单的正式来源是「附件组管理」页**（`request-attachment-templates`）：
 * 业务类型「调查附件」、流程节点「承包方调查录入」下的叶子项即为可选类别，
 * 名称既是显示名，也是写入 `survey_attachments.category` 的值（中文）。
 * 作用域常量与默认项见后端 `app/domain/survey_attachment.py`。
 *
 * 本文件只承担两件事：
 *   1. `FALLBACK_SURVEY_ATTACHMENT_CATEGORIES` —— 接口拿不到配置时的兜底选项，
 *      保证上传功能不会因为配置读取失败而不可用；
 *   2. `LEGACY_SURVEY_ATTACHMENT_CATEGORY_LABELS` —— 把历史数据里的英文码
 *      （如 `household_register`）显示成中文，不参与新数据写入。
 */

export const FALLBACK_SURVEY_ATTACHMENT_CATEGORIES = [
  { value: "身份证", label: "身份证" },
  { value: "户口簿", label: "户口簿" },
  { value: "死亡证明", label: "死亡证明" },
  { value: "婚嫁证明", label: "婚嫁证明" },
  { value: "进城落户证明", label: "进城落户证明" },
  { value: "政策依据", label: "政策依据" },
  { value: "授权委托书", label: "授权委托书" },
  { value: "合同扫描件", label: "合同扫描件" },
];

const LEGACY_SURVEY_ATTACHMENT_CATEGORY_LABELS = {
  id_card: "身份证",
  household_register: "户口簿",
  death_certificate: "死亡证明",
  marriage_certificate: "婚嫁证明",
  urban_settlement: "进城落户证明",
  policy_basis: "政策依据",
  authorization: "授权委托书",
  contract: "合同扫描件",
};

/**
 * 类别码 → 显示名。
 * 先查当前生效的类别配置（新数据的值就是中文名），再查历史英文码映射；
 * 都查不到就原样返回，避免历史数据被显示成空白。空值回落为 "-"。
 */
export function surveyAttachmentCategoryLabel(value, categories = []) {
  if (!value) {
    return "-";
  }
  const matched = categories.find((item) => item.value === value || item.label === value);
  if (matched) {
    return matched.label;
  }
  return LEGACY_SURVEY_ATTACHMENT_CATEGORY_LABELS[value] || value;
}
