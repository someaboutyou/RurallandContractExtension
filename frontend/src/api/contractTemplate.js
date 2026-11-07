import http from "./http";

/** 打印模板母版清单（管理页左侧面板）。 */
export function fetchPrintTemplates() {
  return http.get("/contract-templates");
}

export function fetchContractTemplate(templateKey = "contract") {
  return http.get(`/contract-templates/${templateKey}`);
}

export function updateContractTemplate(templateKey = "contract", payload) {
  return http.put(`/contract-templates/${templateKey}`, payload);
}

export function previewContractTemplate(templateKey = "contract", payload) {
  return http.post(`/contract-templates/${templateKey}/preview`, payload);
}

/** 下载「无内容数据」的空白 Word（模板以空白上下文渲染 → docx）。 */
export function downloadBlankTemplateWord(templateKey) {
  return http.get(`/contract-templates/${templateKey}/blank-word`, {
    responseType: "blob",
    timeout: 120000,
  });
}
