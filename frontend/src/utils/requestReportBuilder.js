/**
 * HTML report generation utilities for request detail export and print.
 * Pure functions – no Vue reactivity or side-effects beyond DOM download.
 */

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function formatReportText(value) {
  if (!value) {
    return "-";
  }
  return escapeHtml(String(value)).replaceAll("\n", "<br />");
}

export function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 19);
}

export function formatFileSize(value) {
  if (!Number.isFinite(value) || value <= 0) {
    return "0 B";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

export function formatDataScope(value) {
  return (
    {
      all: "全部数据",
      county: "县级范围",
      town: "镇级范围",
      village: "村级范围",
      self: "仅本人相关",
      "": "沿用账号范围",
      null: "沿用账号范围",
      undefined: "沿用账号范围",
    }[value] || value || "沿用账号范围"
  );
}

export function formatCandidateMode(value) {
  return (
    {
      permission_scope: "按权限编码匹配",
      role_scope: "按候选角色匹配",
      manual_assign: "人工指定办理人",
      "": "按权限与数据范围自动匹配",
      null: "按权限与数据范围自动匹配",
      undefined: "按权限与数据范围自动匹配",
    }[value] || value || "按权限与数据范围自动匹配"
  );
}

function buildWorkflowStepHtml(steps) {
  return (steps || [])
    .map(
      (item) => `
        <div class="report-step report-step--${escapeHtml(item.status)}">
          <div class="report-step-name">${escapeHtml(item.name)}</div>
          <div class="report-step-meta">${escapeHtml(item.code)} · ${escapeHtml(item.label)}</div>
        </div>`,
    )
    .join("");
}

function buildCandidateHtml(candidates) {
  if (!candidates?.length) {
    return '<div class="report-empty">当前环节暂无候选办理人。</div>';
  }
  return candidates
    .map(
      (item) => `
        <div class="report-card">
          <div class="report-card-title">${escapeHtml(item.userName || item.username || "-")}</div>
          <div class="report-card-meta">${escapeHtml(item.roleName || "-")} · ${escapeHtml(item.regionName || item.regionCode || "-")}</div>
        </div>`,
    )
    .join("");
}

function buildParticipantHtml(participants) {
  if (!participants?.length) {
    return '<div class="report-empty">当前申请还没有办理轨迹。</div>';
  }
  return participants
    .map(
      (item) => `
        <div class="report-timeline-item">
          <div class="report-timeline-head">
            <div class="report-card-title">${escapeHtml(item.actionLabel || item.action)}</div>
            <div class="report-card-meta">${escapeHtml(formatDateTime(item.createdAt))}</div>
          </div>
          <div class="report-card-meta">${escapeHtml(item.userName || item.username || "-")}${item.roleName ? ` · ${escapeHtml(item.roleName)}` : ""}${item.stepName ? ` · ${escapeHtml(item.stepName)}` : ""}</div>
          ${item.comment ? `<div class="report-comment">${formatReportText(item.comment)}</div>` : ""}
        </div>`,
    )
    .join("");
}

function buildAttachmentHtml(attachments) {
  if (!attachments?.length) {
    return '<div class="report-empty">当前申请还没有上传附件。</div>';
  }
  return attachments
    .map(
      (item) => `
        <div class="report-card">
          <div class="report-card-title">${escapeHtml(item.originalName || "-")}</div>
          <div class="report-card-meta">
            ${escapeHtml(formatFileSize(item.fileSize))}
            ${item.category ? ` 路 ${escapeHtml(item.category)}` : ""}
            ${item.stageCode ? ` 路 ${escapeHtml(item.stageCode)}` : ""}
          </div>
          <div class="report-card-meta">
            ${escapeHtml(item.uploadedByName || "-")} 路 ${escapeHtml(formatDateTime(item.createdAt))}
          </div>
        </div>`,
    )
    .join("");
}

function buildTaskConfigHtml(taskConfig) {
  if (!taskConfig) {
    return '<div class="report-empty">当前节点没有额外业务配置。</div>';
  }
  const candidateRoles = taskConfig.candidateRoleCodes?.length
    ? taskConfig.candidateRoleCodes.map((item) => `<span class="report-pill">${escapeHtml(item)}</span>`).join("")
    : '<span class="report-empty-inline">未单独限定</span>';
  return `
    <div class="report-grid report-grid--two">
      <div class="report-field"><span class="report-field-label">权限编码</span><span class="report-field-value">${escapeHtml(taskConfig.permissionCode || "-")}</span></div>
      <div class="report-field"><span class="report-field-label">数据范围</span><span class="report-field-value">${escapeHtml(formatDataScope(taskConfig.dataScope))}</span></div>
      <div class="report-field"><span class="report-field-label">候选模式</span><span class="report-field-value">${escapeHtml(formatCandidateMode(taskConfig.candidateUserMode))}</span></div>
      <div class="report-field"><span class="report-field-label">审核意见</span><span class="report-field-value">${taskConfig.requireComment ? "必须填写" : "可选填写"}</span></div>
      <div class="report-field report-field--full"><span class="report-field-label">候选角色</span><span class="report-field-value report-pill-wrap">${candidateRoles}</span></div>
    </div>`;
}

/**
 * Build a full HTML report for a request detail, optionally including an SVG workflow diagram.
 */
export function buildDetailReportHtml(detail, workflow, svgMarkup = "") {
  if (!detail) {
    return "";
  }
  const workflowSection = svgMarkup
    ? `<div class="report-diagram">${svgMarkup}</div>`
    : '<div class="report-empty">当前流程图未生成图形快照，已保留流程步骤摘要。</div>';
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>${escapeHtml(detail.requestTitle || detail.serialNo)} - 审批留痕</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body { margin: 0; padding: 32px; color: #2f3b24; background: #f6f4eb; font-family: "Microsoft YaHei", "PingFang SC", sans-serif; }
    .report-shell { max-width: 1120px; margin: 0 auto; background: #fffdfa; border: 1px solid #e7e1cf; border-radius: 24px; padding: 30px; box-shadow: 0 16px 40px rgba(69, 80, 44, 0.08); }
    .report-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; padding-bottom: 20px; border-bottom: 1px solid #ebe5d5; }
    .report-title { margin: 0; font-size: 30px; font-weight: 800; letter-spacing: 0.02em; }
    .report-subtitle { margin-top: 10px; color: #6d745d; font-size: 14px; }
    .report-status { display: inline-flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: 999px; background: #eef5df; color: #55712f; font-weight: 700; }
    .report-section { margin-top: 24px; }
    .report-section-title { margin: 0 0 14px; font-size: 18px; font-weight: 800; }
    .report-grid { display: grid; gap: 12px; }
    .report-grid--summary { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .report-grid--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .report-field, .report-card, .report-step, .report-timeline-item { padding: 14px 16px; border: 1px solid #e8e1d0; border-radius: 16px; background: #fff; }
    .report-field--full { grid-column: 1 / -1; }
    .report-field-label { display: block; color: #7b806d; font-size: 13px; }
    .report-field-value { display: block; margin-top: 8px; font-size: 15px; font-weight: 700; line-height: 1.7; word-break: break-word; }
    .report-step { background: #fbfaf5; }
    .report-step--completed { background: #f0f9eb; border-color: #d7ebc6; }
    .report-step--current { background: #fdf6ec; border-color: #f3ddbb; }
    .report-step--rejected { background: #fef0f0; border-color: #f6c7c7; }
    .report-step-name, .report-card-title { font-size: 15px; font-weight: 800; }
    .report-step-meta, .report-card-meta { margin-top: 8px; color: #747b66; font-size: 13px; line-height: 1.6; }
    .report-pill-wrap { display: flex; flex-wrap: wrap; gap: 8px; }
    .report-pill { display: inline-flex; align-items: center; padding: 5px 10px; border-radius: 999px; background: #eef5df; color: #55712f; font-size: 12px; font-weight: 700; }
    .report-empty, .report-empty-inline { color: #8b907f; font-size: 13px; }
    .report-comment { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: #f6f8ef; line-height: 1.7; }
    .report-timeline { display: grid; gap: 12px; }
    .report-timeline-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
    .report-diagram { border: 1px solid #e8e1d0; border-radius: 18px; background: #fafcf7; padding: 16px; overflow: hidden; }
    .report-diagram svg { width: 100%; height: auto; }
    @media print {
      body { background: #fff; padding: 0; }
      .report-shell { border: 0; border-radius: 0; box-shadow: none; max-width: none; }
      .report-section, .report-field, .report-card, .report-step, .report-timeline-item { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <div class="report-shell">
    <div class="report-header">
      <div>
        <h1 class="report-title">${escapeHtml(detail.requestTitle || detail.serialNo)}</h1>
        <div class="report-subtitle">${escapeHtml(detail.serialNo)} · ${escapeHtml(detail.requestType || "-")} · ${escapeHtml(detail.workflowVersionLabel || "跟随当前生效版本")}</div>
      </div>
      <div class="report-status">${escapeHtml(detail.status || "-")} · ${escapeHtml(detail.currentStep || "-")}</div>
    </div>

    <section class="report-section">
      <h2 class="report-section-title">摘要信息</h2>
      <div class="report-grid report-grid--summary">
        <div class="report-field"><span class="report-field-label">创建人</span><span class="report-field-value">${escapeHtml(detail.createdByName || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">租户编码</span><span class="report-field-value">${escapeHtml(detail.tenantCode || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">区域编码</span><span class="report-field-value">${escapeHtml(detail.regionCode || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">更新时间</span><span class="report-field-value">${escapeHtml(formatDateTime(detail.updatedAt))}</span></div>
      </div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">基础信息</h2>
      <div class="report-grid report-grid--two">
        <div class="report-field"><span class="report-field-label">发包方</span><span class="report-field-value">${escapeHtml(detail.issuerName || "-")} (${escapeHtml(detail.issuerCode || "-")})</span></div>
        <div class="report-field"><span class="report-field-label">承包方</span><span class="report-field-value">${escapeHtml(detail.contractorName || "-")} (${escapeHtml(detail.contractorCode || "-")})</span></div>
        <div class="report-field"><span class="report-field-label">证件类型</span><span class="report-field-value">${escapeHtml(detail.contractorIdType || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">证件号码</span><span class="report-field-value">${escapeHtml(detail.contractorIdNo || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">联系电话</span><span class="report-field-value">${escapeHtml(detail.mobile || "-")}</span></div>
        <div class="report-field"><span class="report-field-label">合同代码</span><span class="report-field-value">${escapeHtml(detail.contractCode || "-")}</span></div>
        <div class="report-field report-field--full"><span class="report-field-label">联系地址</span><span class="report-field-value">${formatReportText(detail.address)}</span></div>
        <div class="report-field report-field--full"><span class="report-field-label">申请原因</span><span class="report-field-value">${formatReportText(detail.reason)}</span></div>
        <div class="report-field report-field--full"><span class="report-field-label">备注</span><span class="report-field-value">${formatReportText(detail.note)}</span></div>
      </div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">当前节点配置</h2>
      ${buildTaskConfigHtml(detail.taskConfig)}
    </section>

    <section class="report-section">
      <h2 class="report-section-title">流程步骤</h2>
      <div class="report-grid">${buildWorkflowStepHtml(detail.workflowSteps)}</div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">当前流程图</h2>
      <div class="report-card-meta">${escapeHtml(workflow?.workflowName || detail.workflowCode || "-")} · ${escapeHtml(workflow?.workflowVersionLabel || detail.workflowVersionLabel || "跟随当前生效版本")}</div>
      ${workflowSection}
    </section>

    <section class="report-section">
      <h2 class="report-section-title">候选办理人</h2>
      <div class="report-grid">${buildCandidateHtml(detail.candidateHandlers)}</div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">附件清单</h2>
      <div class="report-grid">${buildAttachmentHtml(detail.attachments)}</div>
    </section>

    <section class="report-section">
      <h2 class="report-section-title">审批留痕</h2>
      <div class="report-timeline">${buildParticipantHtml(detail.participants)}</div>
    </section>
  </div>
  <script>
    window.addEventListener("load", function () {
      if (window.location.search.includes("autoprint=1")) {
        setTimeout(function () { window.print(); }, 240);
      }
    });
  <\/script>
</body>
</html>`;
}

export function downloadTextFile(filename, content) {
  const blob = new Blob([content], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function buildReportFilename(detailRecord) {
  const serialNo = detailRecord?.serialNo || "request";
  return `${serialNo}-approval-report.html`.replace(/[\\/:*?"<>|]/g, "_");
}
