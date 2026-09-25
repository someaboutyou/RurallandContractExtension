/**
 * 相机封装：优先 Capacitor 原生相机，浏览器打开时兜底 input[type=file] 调起系统相机/相册。
 *
 * 采集端只负责「拿到一张压缩后的图片 Blob」，如何组装成 FormData 由调用方决定
 * （调查附件接口是 multipart/form-data，字段名见 `src/mobile/api/attachmentForm.js`）。
 *
 * 为什么要压缩：外业一次要拍身份证/户口簿/合同/地块多张，原图动辄 3~5MB，
 * 农村网络上传体验很差。这里统一把长边压到 `maxWidth` 并按 `quality` 重编码。
 */

import { Capacitor } from "@capacitor/core";

/**
 * 拍照或从相册选图。
 * @param {{ source?: "CAMERA"|"PHOTOS", quality?: number, maxWidth?: number }} options
 * @returns {Promise<{ blob: Blob, previewUrl: string, fileName: string }>}
 */
export async function takePhoto(options = {}) {
  const { source = "CAMERA", quality = 80, maxWidth = 1920 } = options;

  if (Capacitor.isNativePlatform()) {
    const { Camera, CameraResultType, CameraSource } = await import("@capacitor/camera");

    const photo = await Camera.getPhoto({
      quality,
      width: maxWidth,
      correctOrientation: true,
      resultType: CameraResultType.Uri,
      source: source === "PHOTOS" ? CameraSource.Photos : CameraSource.Camera,
    });

    // 原生返回的是 webPath（可直接给 <img src>，也能被 fetch 读取）
    const response = await fetch(photo.webPath);
    const blob = await response.blob();
    const format = photo.format || "jpeg";

    return {
      blob,
      previewUrl: photo.webPath,
      fileName: buildFileName(format),
    };
  }

  // ── 浏览器 / H5 兜底 ────────────────────────────────
  const picked = await pickFileFromBrowser(source);
  if (!picked) {
    throw new Error("未选择图片");
  }
  const compressed = await compressImage(picked, { maxWidth, quality });
  return {
    blob: compressed,
    previewUrl: URL.createObjectURL(compressed),
    fileName: buildFileName("jpeg"),
  };
}

/** 生成形如 `IMG_20260922_105811.jpg` 的文件名。 */
export function buildFileName(extension = "jpeg") {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  const stamp =
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `IMG_${stamp}.${extension}`;
}

function pickFileFromBrowser(source) {
  return new Promise((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    // capture 让移动浏览器直接调起相机；选相册时不设该属性
    if (source === "CAMERA") {
      input.capture = "environment";
    }
    input.style.display = "none";
    document.body.appendChild(input);

    const cleanup = () => {
      input.remove();
    };

    input.addEventListener("change", () => {
      const file = input.files?.[0] || null;
      cleanup();
      resolve(file);
    });
    input.addEventListener("cancel", () => {
      cleanup();
      resolve(null);
    });

    input.click();
  });
}

/**
 * 用 canvas 把图片按长边缩放并重编码为 jpeg，显著减小体积。
 * @param {File|Blob} file
 * @param {{ maxWidth?: number, quality?: number }} options
 * @returns {Promise<Blob>}
 */
export async function compressImage(file, { maxWidth = 1920, quality = 80 } = {}) {
  const bitmap = await loadBitmap(file);
  const scale = Math.min(1, maxWidth / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.drawImage(bitmap, 0, 0, width, height);
  if (typeof bitmap.close === "function") {
    bitmap.close();
  }

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", quality / 100),
  );
  return blob || file;
}

async function loadBitmap(file) {
  if (typeof createImageBitmap === "function") {
    return createImageBitmap(file);
  }
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error("图片解码失败"));
      image.src = url;
    });
    return image;
  } finally {
    URL.revokeObjectURL(url);
  }
}
