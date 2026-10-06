/**
 * 证件 OCR 采集（供「添加家庭成员」等场景复用）。
 * 支持：身份证人像面 / 国徽面 / 户口簿页（首页或常住人口登记卡，未成年人无
 * 身份证时用，字段以人工确认为准）。
 *
 * 与 MobileAttachmentView 的 tryRecognize 同一套判定逻辑（方向 0/90/270 重试 +
 * 几何校验 + 兜底），抽成公共函数后两处共用语义：
 * - ⛔ 方向判定不能只看"认没认出内容"：识别引擎会逐行纠正文字角度，
 *   倒立的图内容全对、但行序是反的，按行序抽字段会把姓名串进住址。
 *   所以每个候选角度都要过 geometryOk 几何校验（号码行在最底部）；
 *   户口簿无固定几何，改用"姓名认出来了"作内容判据。
 * - 三个方向全不过校验但内容可解析时，返回兜底结果交人工核对。
 *
 * 调用方拿到 {ok:true, docType, parsed, elapsedMs, photo} 后自行弹确认层；
 * {ok:false, message} 时扫描层继续扫。
 */

import { isOcrAvailable, recognizeImageBlob, rotateImageBlob } from "./ocr.js";
import {
  detectDocType,
  detectHouseholdRegister,
  parseHouseholdRegister,
  parseIdCardBack,
  parseIdCardFront,
} from "./parser.js";

export { isOcrAvailable };

/**
 * 证件识别（方向重试 + 分档解析）。
 * @param {{blob: Blob, fileName?: string}} photo
 * @param {{ mode?: "auto"|"idcard"|"household" }} [options]
 *   - "idcard"：只走身份证判定（专用入口，登记卡词不会干扰）；
 *   - "household"：户口簿优先，拍成身份证也能兜住（专用入口）；
 *   - "auto"：户口簿判定在前（附件页共用入口，保持原有行为）。
 */
export async function recognizeIdCardWithRetry(photo, { mode = "auto" } = {}) {
  let fallback = null; // 校验不过但内容可解析的结果（兜底用）
  const attempts = []; // 诊断：每个角度的结果摘要（真机定位用）
  let lastPreview = ""; // 诊断：最后一次识别出的文字预览
  let sawLines = false; // 三个角度里是否至少一次识别到文字
  let highResTried = false; // 户口簿高清重试（整轮一次，防耗时翻倍）
  let lastDims = null; // 诊断：最后一次原生解码位图尺寸
  let lastInputBlob = null; // 诊断：最后一次实际送检的图（弹窗展示用）
  // 户口簿是满页小字：登记卡方向常不止 3 个（用户怎么拿都行），多试一个 180°
  const angles = mode === "household" ? [0, 180, 90, 270] : [0, 90, 270];

  for (const deg of angles) {
    let blob = photo.blob;
    if (deg) {
      try {
        blob = await rotateImageBlob(photo.blob, deg);
      } catch {
        attempts.push(`${deg}°:旋转失败`);
        continue;
      }
    }
    let result;
    try {
      result = await recognizeImageBlob(blob);
    } catch (error) {
      if (!deg) return { ok: false, message: error?.message || "识别失败，请重试" };
      attempts.push(`${deg}°:识别异常`);
      continue;
    }
    const lineCount = Array.isArray(result?.lines) ? result.lines.length : 0;
    attempts.push(`${deg}°:${lineCount}行`);
    lastDims = { w: result.imageWidth, h: result.imageHeight };
    lastInputBlob = blob;
    if (lineCount) {
      sawLines = true;
      lastPreview = result.lines
        .map((line) => String(line.text || "").trim())
        .filter(Boolean)
        .slice(0, 8)
        .join(" / ");
    }

    // ⛔ 户口簿判定必须在 detectDocType 之前：登记卡里的 18 位号码会被
    // detectDocType 的"号码兜底"误判成身份证人像面。
    // "idcard" 专用入口直接跳过户口簿判定，两证互不干扰。
    if (mode !== "idcard" && detectHouseholdRegister(result.lines)) {
      let parsed = parseHouseholdRegister(result.lines);
      let elapsedMs = result.elapsedMs;
      const nameOf = (p) => p.fields.find((field) => field.key === "name")?.value;

      // 登记卡满页小字：标准分辨率下常只剩号码行认得出（真机实测）。
      // 姓名没认出时，同一帧再跑一次高清识别（det 基准 1600→2600），
      // 小字检出率显著提升；整轮只重试一次，防识别耗时翻倍。
      if (!nameOf(parsed) && !highResTried) {
        highResTried = true;
        attempts.push("高清重试");
        try {
          const hi = await recognizeImageBlob(blob, { maxSideLen: 2600 });
          const hiParsed = parseHouseholdRegister(hi.lines);
          if (nameOf(hiParsed)) {
            parsed = hiParsed;
            elapsedMs = result.elapsedMs + Number(hi.elapsedMs || 0);
          }
        } catch {
          /* 高清重试失败不影响主流程，走兜底/下一角度 */
        }
      }

      const candidate = { ok: true, docType: "household", parsed, elapsedMs, photo: { ...photo, blob } };
      if (nameOf(parsed)) return candidate; // 姓名认出 = 方向/版式基本正确
      if (!fallback) fallback = candidate;
      continue; // 只有标题词没认出姓名时换角度再试
    }

    const docType = detectDocType(result.lines);
    if (!docType) continue;
    const parsed = docType === "id_front" ? parseIdCardFront(result.lines) : parseIdCardBack(result.lines);

    if (parsed.geometryOk) {
      return { ok: true, docType, parsed, elapsedMs: result.elapsedMs, photo: { ...photo, blob } };
    }
    if (!fallback) {
      fallback = { ok: true, docType, parsed, elapsedMs: result.elapsedMs, photo: { ...photo, blob } };
    }
  }

  if (fallback) return fallback;
  // 失败信息带诊断：各角度行数摘要 + 文字预览 + 实际送检的图与尺寸
  // （调用方弹窗展示，供截图回传定位 —— 图坏/图糊/图好但引擎输出坏，一看便知）
  return {
    ok: false,
    message: sawLines
      ? `已识别到文字但未命中证件版式（${attempts.join("，")}），请让证件占满取景框、光线充足后重试`
      : `没识别到文字（${attempts.join("，")}），请正对证件、对焦清晰后重试`,
    preview: String(lastPreview || "").slice(0, 150),
    dims: lastDims,
    inputBlob: lastInputBlob,
  };
}

/**
 * 从身份证号推性别：第 17 位（15 位证是第 15 位）奇数=男，偶数=女。
 * OCR 只给姓名/号码/住址，性别靠号码反推，避免用户再手填。
 */
export function genderFromIdNo(idNo) {
  const text = String(idNo || "").trim();
  if (text.length === 18) return Number(text[16]) % 2 === 1 ? "1" : "2";
  if (text.length === 15) return Number(text[14]) % 2 === 1 ? "1" : "2";
  return "";
}
