/**
 * Shared attachment utility functions for request views.
 */

export function getAttachmentPreviewKind(item) {
  const contentType = (item?.contentType || "").toLowerCase();
  const fileName = (item?.originalName || "").toLowerCase();
  if (contentType.startsWith("image/") || /\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(fileName)) {
    return "image";
  }
  if (contentType.includes("pdf") || /\.pdf$/i.test(fileName)) {
    return "pdf";
  }
  return "";
}

export function isPreviewableAttachment(item) {
  return Boolean(getAttachmentPreviewKind(item));
}

export function getAttachmentKindLabel(item) {
  const previewType = getAttachmentPreviewKind(item);
  if (previewType === "image") {
    return "图片";
  }
  if (previewType === "pdf") {
    return "PDF";
  }
  const fileName = item?.originalName || "";
  const extension = fileName.includes(".") ? fileName.split(".").pop() : "";
  return (extension || "文件").toUpperCase();
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

export function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  return String(value).replace("T", " ").slice(0, 19);
}

export function statusTagType(status) {
  return (
    {
      待提交: "info",
      审核中: "warning",
      已办结: "success",
      已退回: "danger",
    }[status] || "info"
  );
}

export function workflowTagType(status) {
  return (
    {
      completed: "success",
      current: "warning",
      pending: "info",
      rejected: "danger",
    }[status] || "info"
  );
}
