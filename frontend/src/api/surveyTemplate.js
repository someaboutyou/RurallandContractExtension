import http from "./http";

/** 调查表模板清单。 */
export function fetchSurveyTemplates() {
  return http.get("/survey-templates");
}

/** 按 key 下载模板（.xlt / .dot）。 */
export function downloadSurveyTemplate(templateKey) {
  return http.get(`/survey-templates/${templateKey}`, {
    responseType: "blob",
    timeout: 120000,
  });
}
