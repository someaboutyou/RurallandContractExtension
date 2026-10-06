<template>
  <div class="ocr-scan">
    <!-- 实时相机预览 -->
    <video ref="videoRef" class="ocr-scan__video" autoplay playsinline muted />

    <!-- 取景框 + 遮罩 -->
    <div class="ocr-scan__center">
      <div ref="frameRef" class="ocr-scan__frame" :class="{ 'ocr-scan__frame--page': isHouseholdMode }">
        <!-- 身份证模式：头像剪影引导；户口簿模式：登记卡页面轮廓 -->
        <svg v-if="!isHouseholdMode" class="ocr-scan__silhouette" viewBox="0 0 130 100" aria-hidden="true">
          <rect x="3" y="3" width="124" height="94" rx="10" fill="none" stroke="rgba(255,255,255,0.5)" stroke-width="2.5" stroke-dasharray="7 6" />
          <circle cx="44" cy="50" r="23" fill="rgba(255,255,255,0.30)" />
          <path d="M 118 85 C 92 85 77 69 77 50 C 77 31 92 15 118 15 Z" fill="rgba(255,255,255,0.30)" />
        </svg>
        <svg v-else class="ocr-scan__silhouette" viewBox="0 0 100 140" aria-hidden="true">
          <rect x="4" y="4" width="92" height="132" rx="8" fill="none" stroke="rgba(255,255,255,0.5)" stroke-width="2.5" stroke-dasharray="7 6" />
          <line x1="18" y1="34" x2="82" y2="34" stroke="rgba(255,255,255,0.35)" stroke-width="3" />
          <line x1="18" y1="58" x2="82" y2="58" stroke="rgba(255,255,255,0.35)" stroke-width="3" />
          <line x1="18" y1="82" x2="66" y2="82" stroke="rgba(255,255,255,0.35)" stroke-width="3" />
        </svg>
        <span class="ocr-scan__orientation-label">{{ isHouseholdMode ? "登记卡信息区对准框内" : "头像朝左" }}</span>
        <span class="ocr-scan__corner ocr-scan__corner--tl" />
        <span class="ocr-scan__corner ocr-scan__corner--tr" />
        <span class="ocr-scan__corner ocr-scan__corner--bl" />
        <span class="ocr-scan__corner ocr-scan__corner--br" />
      </div>
      <p class="ocr-scan__hint" :class="{ 'ocr-scan__hint--ok': hintLevel === 'ok' }">{{ hint }}</p>
    </div>

    <!-- 顶栏 -->
    <div class="ocr-scan__topbar">
      <button class="ocr-scan__close" @click="close">✕</button>
      <span class="ocr-scan__title">证件扫描</span>
    </div>

    <!-- 底部：手动快门（自动拍摄失灵时的兜底） -->
    <div class="ocr-scan__bottom">
      <button
        class="ocr-scan__shutter"
        :class="{ 'ocr-scan__shutter--busy': busy }"
        :disabled="busy"
        @click="manualCapture"
      >
        <van-loading v-if="busy" size="26px" color="#fff" />
      </button>
      <p class="ocr-scan__shutter-label">{{ busy ? "识别中…" : "对准框内自动拍摄" }}</p>
    </div>
  </div>
</template>

<script setup>
/**
 * 证件自动扫描层（体验升级版，替代"拍照→识别"两步）。
 *
 * 原理（全 JS，无需动原生，走热更可上线）：
 * - getUserMedia 起实时预览（Capacitor 的 WebChromeClient 会自动桥接系统相机权限）；
 * - 每 ~220ms 取一帧降采样到 240px 宽，对**取景框中心区域**算三个指标：
 *   ① 亮度（太暗提示开灯/找亮处） ② 拉普拉斯方差（模糊/未对焦） ③ 帧间差（晃动）；
 * - 三条件连续达标 GOOD_STREAK 次（≈1.3 秒）→ 全分辨率抓拍 → 交给父组件的
 *   tryRecognize（内部走现有原生 OcrPlugin）；识别成功关闭本层，失败提示后冷却续扫。
 * - OCR 本身就是"是不是证件"的最终裁判：拿不到证件字段就当作没对准，继续扫。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { VanLoading, showToast } from "../ui.js";

const props = defineProps({
  /** async (photo: {blob, fileName, mode}) => {ok: boolean, message?: string}；ok=true 时父组件已接管结果 */
  tryRecognize: { type: Function, required: true },
  /** "idcard"（默认）| "household"：分入口后两证各用各的取景框/相机参数/识别管线 */
  mode: { type: String, default: "idcard" },
});
const emit = defineEmits(["close"]);

const isHouseholdMode = computed(() => props.mode === "household");

// ── 可调参数（按真机表现微调，全在热更层） ──────────────────────
const SAMPLE_INTERVAL = 220; // 分析节拍 ms
const GOOD_STREAK = 4; // 连续达标次数（≈0.9s，快拍快识）
const CENTER_W = 0.72; // 分析区域（≈取景框占画面比例，略收进框内）
const CENTER_H = 0.58;
const MIN_BRIGHTNESS = 55; // 0-255
const MIN_SHARPNESS = 40; // 拉普拉斯方差
const MAX_DIFF = 9; // 帧间平均差（晃动阈值）
const RETRY_COOLDOWN = 1500; // 识别失败后恢复扫描的等待 ms

const videoRef = ref(null);
const frameRef = ref(null);
const busy = ref(false);
const hintLevel = ref("none");
const conditions = ref({ bright: false, sharp: false, still: false });

let stream = null;
let timer = null;
let sampleCtx = null;
let prevGray = null;
let goodStreak = 0;
let stopped = false;

const hint = computed(() => {
  if (busy.value) return "正在识别…";
  const c = conditions.value;
  if (!c.bright) return "光线不足，请移到明亮处";
  if (!c.sharp) return "对焦中，请勿晃动";
  if (!c.still) return "请保持证件平稳";
  if (goodStreak > 0) return "保持不动，即将自动拍摄…";
  return isHouseholdMode.value
    ? "凑近拍摄登记卡信息区，压平页面"
    : "证件对准框内，保持平稳";
});

onMounted(async () => {
  try {
    // ⛔ 相机参数分模式：身份证用 4:3 的 1920×1440 —— 竖屏手机 + object-fit:cover
    // 会把 16:9 画面左右裁掉，取景框只能映射到视频里约 380px 宽的一条（真机
    // 识别不出的主因）；改 4:3 取流后同一取景框能拿到 ~500px 宽，字大了一圈。
    // 4K 不用（部分机型预览卡顿反而拖垮识别）；户口簿满页小字仍尽量 4K
    // （不支持的设备浏览器自动回落，不影响身份证扫描）。
    stream = await navigator.mediaDevices.getUserMedia({
      video: isHouseholdMode.value
        ? { facingMode: "environment", width: { ideal: 3840 }, height: { ideal: 2160 } }
        : { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1440 } },
      audio: false,
    });
  } catch (error) {
    showToast("无法打开相机（需要相机权限）");
    close();
    return;
  }
  const video = videoRef.value;
  video.srcObject = stream;
  try {
    await video.play();
  } catch {
    /* autoplay 被拦时等 canplay，循环里 readyState 会兜底 */
  }
  scheduleSample();
});

onUnmounted(stop);

function close() {
  stopped = true;
  emit("close");
}

function stop() {
  stopped = true;
  if (timer) clearTimeout(timer);
  timer = null;
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  }
}

function scheduleSample() {
  if (stopped) return;
  timer = setTimeout(async () => {
    if (stopped) return;
    if (!busy.value) analyze();
    scheduleSample();
  }, SAMPLE_INTERVAL);
}

// ── 帧分析 ────────────────────────────────────────────────────
const SAMPLE_W = 240;

function analyze() {
  const video = videoRef.value;
  if (!video || video.readyState < 2 || !video.videoWidth) return;

  const w = SAMPLE_W;
  const h = Math.round((SAMPLE_W * video.videoHeight) / video.videoWidth);
  if (!sampleCtx || sampleCtx.canvas.height !== h) {
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    sampleCtx = canvas.getContext("2d", { willReadFrequently: true });
  }
  sampleCtx.drawImage(video, 0, 0, w, h);
  const { data } = sampleCtx.getImageData(0, 0, w, h);

  // 灰度化
  const gray = new Uint8Array(w * h);
  for (let i = 0, p = 0; i < gray.length; i += 1, p += 4) {
    gray[i] = (data[p] * 299 + data[p + 1] * 587 + data[p + 2] * 114) / 1000;
  }

  // 中心区域（≈取景框）
  const x0 = Math.round(((1 - CENTER_W) / 2) * w);
  const x1 = Math.round(((1 + CENTER_W) / 2) * w);
  const y0 = Math.round(((1 - CENTER_H) / 2) * h);
  const y1 = Math.round(((1 + CENTER_H) / 2) * h);

  // ① 亮度 ② 拉普拉斯方差（清晰度）③ 帧间差（稳定度）——一遍循环全算完
  let sum = 0;
  let count = 0;
  let lapSum = 0;
  let lapSqSum = 0;
  let lapCount = 0;
  let diffSum = 0;
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const idx = y * w + x;
      const g = gray[idx];
      sum += g;
      count += 1;
      if (prevGray) diffSum += Math.abs(g - prevGray[idx]);
      if (x > x0 && x < x1 - 1 && y > y0 && y < y1 - 1) {
        const lap = 4 * g - gray[idx - 1] - gray[idx + 1] - gray[idx - w] - gray[idx + w];
        lapSum += lap;
        lapSqSum += lap * lap;
        lapCount += 1;
      }
    }
  }
  prevGray = gray;

  const brightness = count ? sum / count : 0;
  const diff = count ? diffSum / count : 255;
  let sharpness = 0;
  if (lapCount) {
    const mean = lapSum / lapCount;
    sharpness = lapSqSum / lapCount - mean * mean;
  }

  const bright = brightness >= MIN_BRIGHTNESS;
  const sharp = sharpness >= MIN_SHARPNESS;
  const still = prevGray ? diff <= MAX_DIFF : false;
  conditions.value = { bright, sharp, still };

  if (bright && sharp && still) {
    goodStreak += 1;
    if (goodStreak >= GOOD_STREAK) {
      goodStreak = 0;
      void capture();
    }
  } else {
    goodStreak = 0;
  }
}

// ── 抓拍 + 识别 ────────────────────────────────────────────────
async function capture() {
  if (busy.value || stopped) return;
  const video = videoRef.value;
  if (!video || !video.videoWidth) return;
  busy.value = true;

  try {
    const blob = await grabFrameCrop(video);
    try {
      navigator.vibrate?.(60);
    } catch {
      /* 无振动权限则静默 */
    }
    const outcome = (await props.tryRecognize({ blob, fileName: `doc-${props.mode}-${Date.now()}.jpg`, mode: props.mode })) || {};
    if (outcome.ok) {
      stop();
      emit("close");
      return;
    }
    showToast(outcome.message || "未识别到证件内容，请对准框内重试");
    await sleep(RETRY_COOLDOWN); // 冷却后续扫
  } catch (error) {
    showToast(error?.message || "抓拍失败，请重试");
  } finally {
    busy.value = false;
    prevGray = null; // 冷却后重新积累稳定度
    goodStreak = 0;
  }
}

function manualCapture() {
  goodStreak = GOOD_STREAK; // 直接触发
  void capture();
}

/**
 * 只裁取景框内的区域抓拍（关键精度优化）：
 * 整幅画面发给 OCR 时证件只占中间一小块，住址这类小字必然认不出；
 * 裁框后证件占满 OCR 输入，等效放大 2~3 倍。
 * 坐标换算：object-fit: cover 下视频按 scale 放大居中，把框的屏幕坐标反算回视频像素坐标。
 */
function grabFrameCrop(video) {
  return new Promise((resolve, reject) => {
    const vw = video.videoWidth;
    const vh = video.videoHeight;
    const rect = frameRef.value?.getBoundingClientRect();
    if (!rect || !rect.width || !vw) {
      reject(new Error("抓拍失败"));
      return;
    }
    const scale = Math.max(window.innerWidth / vw, window.innerHeight / vh);
    const offX = (window.innerWidth - vw * scale) / 2;
    const offY = (window.innerHeight - vh * scale) / 2;
    let sx = (rect.left - offX) / scale;
    let sy = (rect.top - offY) / scale;
    let sw = rect.width / scale;
    let sh = rect.height / scale;
    // 越界钳制（框理论在视频区域内，防浮点误差）
    sx = Math.max(0, Math.min(sx, vw - 1));
    sy = Math.max(0, Math.min(sy, vh - 1));
    sw = Math.max(1, Math.min(sw, vw - sx));
    sh = Math.max(1, Math.min(sh, vh - sy));

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(sw);
    canvas.height = Math.round(sh);
    canvas.getContext("2d").drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("抓拍失败"))),
      "image/jpeg",
      0.95,
    );
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
</script>

<style scoped>
.ocr-scan {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: #000;
}

.ocr-scan__video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 取景框：竖向长方形（把身份证比例 85.6:54 旋转 90°），证件上下方向竖放 */
.ocr-scan__center {
  position: absolute;
  left: 50%;
  top: 40%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  pointer-events: none;
}

/* 取景框放大：裁框送给 OCR 时证件的像素数直接决定识别率——
   框每大一分，字的像素就多一分（真机：框小时只认得出号码行） */
.ocr-scan__frame {
  position: relative;
  width: min(78vw, 42vh, 380px);
  aspect-ratio: 54 / 85.6;
  border-radius: 16px;
  box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.5);
  transition: box-shadow 0.2s;
}

/* 户口簿模式：A4 登记卡比例（210:297），框放大并尽量占满屏高——
   满页小字场景下取景框每大一分，字的像素就多一分 */
.ocr-scan__frame--page {
  width: min(80vw, 54vh, 420px);
  aspect-ratio: 210 / 297;
}

/* 头像剪影引导：只画在遮罩层，抓拍裁的是视频帧本身，不会进识别图。
   剪影头朝左、照片区横向 —— 与证件逆时针竖放（识别最优方向）时的实际照片位置一致 */
.ocr-scan__silhouette {
  position: absolute;
  top: 8%;
  left: 50%;
  transform: translateX(-50%);
  width: 56%;
  height: auto;
  pointer-events: none;
}

.ocr-scan__orientation-label {
  position: absolute;
  bottom: 6%;
  left: 50%;
  transform: translateX(-50%);
  padding: 3px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  white-space: nowrap;
}

.ocr-scan__corner {
  position: absolute;
  width: 26px;
  height: 26px;
  border: 3px solid #07c160;
}

.ocr-scan__corner--tl { left: -3px; top: -3px; border-right: none; border-bottom: none; border-top-left-radius: 16px; }
.ocr-scan__corner--tr { right: -3px; top: -3px; border-left: none; border-bottom: none; border-top-right-radius: 16px; }
.ocr-scan__corner--bl { left: -3px; bottom: -3px; border-right: none; border-top: none; border-bottom-left-radius: 16px; }
.ocr-scan__corner--br { right: -3px; bottom: -3px; border-left: none; border-top: none; border-bottom-right-radius: 16px; }

.ocr-scan__hint {
  margin: 14px 0 0;
  padding: 6px 14px;
  max-width: 80vw;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 14px;
  text-align: center;
  white-space: nowrap;
}

.ocr-scan__hint--ok {
  background: rgba(7, 193, 96, 0.85);
}

.ocr-scan__topbar {
  position: absolute;
  top: calc(env(safe-area-inset-top, 0px) + 10px);
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  padding: 0 14px;
}

.ocr-scan__title {
  flex: 1;
  text-align: center;
  color: #fff;
  font-size: 16px;
}

.ocr-scan__close {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 16px;
  line-height: 1;
}

.ocr-scan__bottom {
  position: absolute;
  left: 0;
  right: 0;
  bottom: calc(env(safe-area-inset-bottom, 0px) + 14px);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.ocr-scan__shutter {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: 4px solid rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}

.ocr-scan__shutter--busy {
  opacity: 0.6;
}

.ocr-scan__shutter-label {
  margin: 10px 0 0;
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
}
</style>
