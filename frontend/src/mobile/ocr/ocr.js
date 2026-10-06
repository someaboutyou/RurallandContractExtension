/**
 * 端侧 OCR 调用封装（仅 Android 原生壳内可用，浏览器端调用方需自行守卫）。
 *
 * 原生侧：`android/app/.../OcrPlugin.java`（RapidOcr onnx 引擎，PP-OCRv3 模型随包）。
 * 输入是照片 Blob → base64 过桥（照片已经相机插件压缩过，几百 KB 级别）；
 * 输出是文字行数组（text/score/box），字段抽取在 `parser.js`。
 */
import { Capacitor, registerPlugin } from "@capacitor/core";

const Ocr = registerPlugin("Ocr");

export function isOcrAvailable() {
  return Capacitor.isNativePlatform();
}

/**
 * 识别一张图片。
 * @param {Blob} blob 已压缩的照片
 * @param {{ maxSideLen?: number }} [options] maxSideLen：det 内部缩放基准，越小越快
 * @returns {Promise<{ lines: {text: string, score: number, box: {x: number, y: number}[]}[], text: string, elapsedMs: number }>}
 */
export async function recognizeImageBlob(blob, { maxSideLen = 1600 } = {}) {
  if (!isOcrAvailable()) {
    throw new Error("OCR 仅在 App 内可用");
  }
  // 小图先放大到引擎门槛：裁框后的图长边往往只有 ~900px，det 直接跑在
  // 原分辨率（低于 maxSideLen 不放大），住址这类小字特征不足——放大后
  // det 的特征图更细，小字检出率明显提升（上限 2 倍，防无意义插值）。
  const prepared = await upscaleSmallImage(blob, maxSideLen);
  const base64 = await blobToBase64(prepared);
  const result = await Ocr.recognize({ imageBase64: base64, maxSideLen });
  return {
    lines: Array.isArray(result?.lines) ? result.lines : [],
    text: String(result?.text || ""),
    elapsedMs: Number(result?.elapsedMs || 0),
    // 原生侧实际解码参与识别的位图尺寸（诊断用：核对采集→桥接→解码链路）
    imageWidth: Number(result?.imageWidth || 0),
    imageHeight: Number(result?.imageHeight || 0),
  };
}

/** 长边不足 maxSideLen 的小图等比放大（≤2 倍），让 det 跑满门槛分辨率 */
async function upscaleSmallImage(blob, maxSideLen) {
  try {
    const bitmap = await createImageBitmap(blob);
    const longSide = Math.max(bitmap.width, bitmap.height);
    if (longSide <= 0) return blob;
    const target = Math.min(maxSideLen, longSide * 2);
    if (target <= longSide) {
      bitmap.close?.();
      return blob;
    }
    const scale = target / longSide;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close?.();
    const out = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.95));
    return out || blob;
  } catch {
    return blob; // 放大失败不阻断识别
  }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const commaIndex = dataUrl.indexOf(",");
      resolve(commaIndex >= 0 ? dataUrl.slice(commaIndex + 1) : "");
    };
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(blob);
  });
}

/**
 * 把图片旋转 deg 度（仅 90/180/270 有意义），返回新 Blob（jpeg）。
 * 用途：取景框是竖向的、证件竖放时文字在原图里是横躺的，OCR 前转正。
 */
export async function rotateImageBlob(blob, deg) {
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement("canvas");
  const swap = deg === 90 || deg === 270;
  canvas.width = swap ? bitmap.height : bitmap.width;
  canvas.height = swap ? bitmap.width : bitmap.height;
  const ctx = canvas.getContext("2d");
  ctx.translate(canvas.width / 2, canvas.height / 2);
  ctx.rotate((deg * Math.PI) / 180);
  ctx.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2);
  bitmap.close?.();
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (out) => (out ? resolve(out) : reject(new Error("图片旋转失败"))),
      "image/jpeg",
      0.92,
    );
  });
}
