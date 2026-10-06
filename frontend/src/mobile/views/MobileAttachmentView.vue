<template>
  <div class="m-attach">
    <van-cell-group inset title="本次上传">
      <van-field
        :model-value="categoryLabel"
        readonly
        is-link
        label="类别"
        placeholder="请选择附件类别"
        @click="categoryPickerVisible = true"
      />
      <van-field v-model="description" label="说明" placeholder="选填，如「户口簿第 2 页」" maxlength="120" />
    </van-cell-group>

    <div class="m-attach__capture">
      <van-button block round type="primary" :loading="uploading" @click="onCapture('CAMERA')">
        拍照上传
      </van-button>
      <van-button block round plain :disabled="uploading" @click="onCapture('PHOTOS')">
        从相册选择
      </van-button>
      <van-button
        block
        round
        type="success"
        :disabled="uploading"
        @click="onOcrScan"
      >
        证件识别上传（自动扫描）
      </van-button>
    </div>

    <van-cell-group inset :title="`已上传（${attachments.length}）`">
      <van-cell
        v-for="item in attachments"
        :key="item.id"
        :title="item.originalName || '附件'"
        :label="categoryLabelOf(item.category)"
        is-link
        @click="onPreview(item)"
      >
        <template #value>
          <van-button size="mini" plain type="danger" @click.stop="onDelete(item)">删除</van-button>
        </template>
      </van-cell>
      <van-cell v-if="!attachments.length" title="暂无附件" label="点上方按钮开始拍照采集" />
    </van-cell-group>

    <p class="m-attach__hint">
      照片会自动压缩后上传；网络不佳时请等待提示成功后再离开本页。
    </p>

    <van-popup v-model:show="categoryPickerVisible" position="bottom" round>
      <van-picker
        :columns="categoryColumns"
        title="选择附件类别"
        @confirm="onCategoryConfirm"
        @cancel="categoryPickerVisible = false"
      />
    </van-popup>

    <OcrResultDialog
      v-model:show="ocrDialogVisible"
      :title="ocrTitle"
      :doc-type="ocrDocType"
      :fields="ocrFields"
      :elapsed-ms="ocrElapsedMs"
      @confirm="onOcrConfirm"
    />

    <!-- 全屏自动扫描层：取景框 + 三条件自动抓拍 + 识别 -->
    <OcrScanOverlay
      v-if="ocrScanVisible"
      :try-recognize="tryRecognize"
      @close="ocrScanVisible = false"
    />

    <!-- 识别诊断层：显示 OCR 实际收到的裁框图 + 原生解码尺寸，截图回传即可定性 -->
    <van-popup
      v-model:show="diagVisible"
      position="center"
      round
      :style="{ width: '86%', padding: '16px' }"
    >
      <p class="attach-diag__title">识别诊断</p>
      <p class="attach-diag__text">{{ diagMessage }}</p>
      <p v-if="diagDims" class="attach-diag__text">引擎收到的图像尺寸：{{ diagDims.w }}×{{ diagDims.h }}px</p>
      <img v-if="diagUrl" :src="diagUrl" class="attach-diag__img" alt="OCR 输入图" />
      <p class="attach-diag__hint">上图即 OCR 实际收到的画面，截图发群里即可定位问题</p>
      <van-button block type="primary" @click="diagVisible = false">知道了</van-button>
    </van-popup>
  </div>
</template>

<script setup>
/**
 * 拍照附件采集页。
 *
 * 接口沿用 PC 端同一套：
 * - 列表：`GET /surveys/batches/{id}/results/{uid}/phase2` → `data.data.attachments`
 * - 上传：`POST .../attachments`，FormData 字段固定为 `category` + `description` + `file`
 *   （与 PC 端 `handleUploadAttachment` 完全一致，别改字段名）
 * - 类别：`GET /surveys/attachment-categories` → `{ label, value }[]`，
 *   来源是「附件组管理」页的叶子项
 *
 * 采集走 `native/camera.js`：App 内调原生相机，浏览器兜底 input[type=file]；
 * 两条路径都会先压缩，避免外业原图上传卡死。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  deleteSurveyAttachment,
  fetchSurveyAttachmentCategories,
  fetchSurveyPhase2,
  previewSurveyAttachment,
  uploadSurveyAttachment,
} from "../../api/survey";
import { takePhoto } from "../native/camera.js";
import { isOcrAvailable, recognizeImageBlob, rotateImageBlob } from "../ocr/ocr.js";
import { detectDocType, detectHouseholdRegister, parseHouseholdRegister, parseIdCardBack, parseIdCardFront } from "../ocr/parser.js";
import OcrResultDialog from "../components/OcrResultDialog.vue";
import OcrScanOverlay from "../components/OcrScanOverlay.vue";
import {
  VanButton,
  VanCell,
  VanCellGroup,
  VanField,
  VanPicker,
  VanPopup,
  showConfirmDialog,
  showImagePreview,
  showToast,
} from "../ui.js";

const route = useRoute();

const batchId = computed(() => String(route.params.batchId || ""));
const contractorUid = computed(() => String(route.params.contractorUid || ""));

const categoryOptions = ref([]);
const category = ref("");
const description = ref("");
const categoryPickerVisible = ref(false);

const attachments = ref([]);
const uploading = ref(false);
const loading = ref(false);

// ── 证件识别状态 ────────────────────────────────────────────────
const ocrAvailable = isOcrAvailable();
const ocrScanVisible = ref(false);
const ocrDialogVisible = ref(false);
const ocrTitle = ref("识别结果");
const ocrDocType = ref("");
const ocrFields = ref([]);
const ocrElapsedMs = ref(0);
/** 等待确认上传的照片（弹层确认后落库） */
let ocrPendingPhoto = null;

const categoryLabel = computed(
  () => categoryOptions.value.find((item) => item.value === category.value)?.label || "",
);
const categoryColumns = computed(() =>
  categoryOptions.value.map((item) => ({ text: item.label, value: item.value })),
);

function categoryLabelOf(code) {
  if (!code) return "未分类";
  return categoryOptions.value.find((item) => item.value === code)?.label || code;
}

async function loadCategories() {
  try {
    const { data } = await fetchSurveyAttachmentCategories();
    const items = (data?.data || []).filter((item) => item?.value);
    categoryOptions.value = items;
  } catch {
    // 拿不到类别不阻塞采集：允许"未分类"上传（category 传空串后端会拒，故这里给出兜底项）
    categoryOptions.value = [{ label: "其他材料", value: "其他材料" }];
  }
  if (!category.value) {
    category.value = categoryOptions.value[0]?.value || "";
  }
}

async function loadAttachments() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyPhase2(batchId.value, contractorUid.value);
    attachments.value = data?.data?.attachments || [];
  } catch (error) {
    showToast(error?.response?.data?.detail || "附件列表加载失败");
    attachments.value = [];
  } finally {
    loading.value = false;
  }
}

function onCategoryConfirm({ selectedOptions }) {
  category.value = selectedOptions?.[0]?.value || "";
  categoryPickerVisible.value = false;
}

async function onCapture(source) {
  if (!category.value) {
    showToast("请先选择附件类别");
    return;
  }

  let photo;
  try {
    photo = await takePhoto({ source, quality: 80, maxWidth: 1920 });
  } catch (error) {
    showToast(error?.message || "拍照失败");
    return;
  }

  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append("category", category.value);
    formData.append("description", description.value || "");
    formData.append("file", photo.blob, photo.fileName);

    await uploadSurveyAttachment(batchId.value, contractorUid.value, formData);
    showToast("上传成功");
    description.value = "";
    await loadAttachments();
  } catch (error) {
    showToast(error?.response?.data?.detail || "上传失败，请重试");
  } finally {
    if (photo?.previewUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(photo.previewUrl);
    }
    uploading.value = false;
  }
}

/**
 * 证件识别上传（自动扫描版）：打开全屏扫描层 → 实时预览 + 自动抓拍 →
 * 抓拍帧交给 tryRecognize 识别 → 成功弹确认层（照片 + 字段），确认后走附件上传。
 * 手动"拍照上传"路径（takePhoto）保留不动，作为扫描不可用时的兜底。
 */
function onOcrScan() {
  if (!ocrAvailable) {
    showToast("证件识别仅在 App 内可用");
    return;
  }
  if (!category.value) {
    showToast("请先选择附件类别");
    return;
  }
  ocrScanVisible.value = true;
}

/**
 * 扫描层抓到一帧后的识别回调（由 OcrScanOverlay await）。
 * 返回 {ok}：ok=true 已弹确认层，扫描层关闭；false 时扫描层提示并继续扫。
 *
 * 旋转重试：取景框是竖向的，证件竖放时抓拍图里文字是横躺的——
 * 原图认不出就转 90°/270° 重试，认出后附件也存「转正后」的图。
 */
/**
 * 扫描层抓到一帧后的识别回调（由 OcrScanOverlay await）。
 *
 * ⛔ 方向判定不能只看"认没认出内容"：识别引擎会逐行纠正文字角度，
 * **倒立的图内容全对、但行序是反的**（号码行跑到最上、姓名落到最下），
 * 按行序抽字段就会把姓名串进住址。所以每个候选角度都要过
 * `geometryOk` 几何校验（号码行在最底部），全不过才用兜底结果。
 *
 * 返回 {ok}：ok=true 已弹确认层，扫描层关闭；false 时扫描层提示并继续扫。
 */
async function tryRecognize(photo) {
  let fallback = null; // 几何不合理但内容可解析的结果（兜底用）
  let elapsedTotal = 0;
  const attempts = []; // 诊断：每个角度的结果摘要
  let lastPreview = ""; // 诊断：最后一次识别出的文字预览
  let sawLines = false;
  let highResTried = false; // 户口簿高清重试（整轮一次）
  let lastDims = null; // 诊断：最后一次原生解码位图尺寸
  let lastInputBlob = null; // 诊断：最后一次实际送检的图

  for (const deg of [0, 90, 270]) {
    let blob = photo.blob;
    if (deg) {
      try {
        blob = await rotateImageBlob(photo.blob, deg);
      } catch {
        continue;
      }
    }
    let result;
    try {
      result = await recognizeImageBlob(blob);
    } catch (error) {
      if (!deg) return { ok: false, message: error?.message || "识别失败，请重试" };
      continue;
    }
    elapsedTotal += Number(result.elapsedMs || 0);
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

    // ⛔ 户口簿判定必须在 detectDocType 之前（登记卡里的 18 位号码会被
    // detectDocType 的号码兜底误判成身份证人像面）；方向重试以"姓名认出"为判据
    if (detectHouseholdRegister(result.lines)) {
      let parsed = parseHouseholdRegister(result.lines);
      let elapsedMs = result.elapsedMs;
      const nameOf = (p) => p.fields.find((field) => field.key === "name")?.value;

      // 登记卡满页小字：标准分辨率下常只剩号码行认得出，姓名没认出时
      // 同一帧再跑一次高清识别（det 基准 1600→2600），整轮只重试一次
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
          /* 高清重试失败不影响主流程 */
        }
      }

      const candidate = { docType: "household", parsed, elapsedMs, photo: { ...photo, blob } };
      if (nameOf(parsed)) {
        acceptResult(candidate.docType, candidate.parsed, candidate.elapsedMs, candidate.photo);
        return { ok: true };
      }
      if (!fallback) fallback = candidate;
      continue;
    }

    const docType = detectDocType(result.lines);
    if (!docType) continue;
    const parsed = docType === "id_front" ? parseIdCardFront(result.lines) : parseIdCardBack(result.lines);

    if (parsed.geometryOk) {
      acceptResult(docType, parsed, result.elapsedMs, { ...photo, blob });
      return { ok: true };
    }
    if (!fallback) fallback = { docType, parsed, elapsedMs: result.elapsedMs, photo: { ...photo, blob } };
  }

  if (fallback) {
    // 三个方向都几何异常（极端倾斜等）：至少内容能解析，交给人工在弹层里核对
    acceptResult(fallback.docType, fallback.parsed, fallback.elapsedMs, fallback.photo);
    return { ok: true };
  }
  const message = sawLines
    ? `已识别到文字但未命中证件版式（${attempts.join("，")}），请让证件占满取景框、光线充足后重试`
    : `没识别到文字（${attempts.join("，")}），请正对证件、对焦清晰后重试`;
  // 带识别输入图的诊断弹层：图坏/图糊/图好但识别坏，截图回传即可定性
  showDiag(message, lastPreview, lastDims, lastInputBlob);
  return { ok: false, message };
}

/* ---- 识别诊断层状态 ---- */
const diagVisible = ref(false);
const diagMessage = ref("");
const diagDims = ref(null);
const diagUrl = ref("");

function showDiag(message, preview, dims, blob) {
  diagMessage.value = [message, preview ? `识别原文：${preview}` : ""].filter(Boolean).join("\n");
  diagDims.value = dims || null;
  if (diagUrl.value) {
    URL.revokeObjectURL(diagUrl.value);
    diagUrl.value = "";
  }
  if (blob) {
    try {
      diagUrl.value = URL.createObjectURL(blob);
    } catch {
      /* 生成预览失败不影响诊断文字 */
    }
  }
  diagVisible.value = true;
}

function acceptResult(docType, parsed, elapsedMs, photo) {
  ocrDocType.value = docType;
  ocrTitle.value =
    docType === "household" ? "户口簿页识别" : docType === "id_front" ? "身份证人像面识别" : "身份证国徽面识别";
  ocrFields.value = parsed.fields;
  ocrElapsedMs.value = elapsedMs;
  ocrPendingPhoto = photo;
  ocrDialogVisible.value = true;
}

/** 弹层确认：把（可能改过的）字段写进说明后上传 */
async function onOcrConfirm(values) {
  const photo = ocrPendingPhoto;
  ocrPendingPhoto = null;
  if (!photo) return;

  const DOC_LABELS = {
    name: "姓名",
    gender: "性别",
    relationToHead: "与户主关系",
    idNo: "证件号码",
    address: "住址",
    authority: "签发机关",
    validPeriod: "有效期限",
  };
  const summary = Object.entries(values)
    .filter(([, value]) => value)
    .map(([key, value]) => `${DOC_LABELS[key] || key}：${value}`)
    .join("；");

  const userNote = description.value.trim();
  const composed = summary
    ? `${userNote ? `${userNote}；` : ""}【证件识别】${summary}`.slice(0, 200)
    : userNote;

  await uploadPhoto(photo, composed);
}

/** 复用普通上传链路；description 参数允许覆盖表单里的说明 */
async function uploadPhoto(photo, composedDescription) {
  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append("category", category.value);
    formData.append("description", composedDescription ?? description.value ?? "");
    formData.append("file", photo.blob, photo.fileName);

    await uploadSurveyAttachment(batchId.value, contractorUid.value, formData);
    showToast("上传成功");
    description.value = "";
    await loadAttachments();
  } catch (error) {
    showToast(error?.response?.data?.detail || "上传失败，请重试");
  } finally {
    if (photo?.previewUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(photo.previewUrl);
    }
    uploading.value = false;
  }
}

async function onPreview(item) {  try {
    const { data } = await previewSurveyAttachment(item.id);
    const url = URL.createObjectURL(data);
    showImagePreview({
      images: [url],
      closeable: true,
      onClose: () => URL.revokeObjectURL(url),
    });
  } catch (error) {
    showToast(error?.response?.data?.detail || "预览失败");
  }
}

async function onDelete(item) {
  try {
    await showConfirmDialog({
      title: "删除附件",
      message: `确认删除「${item.originalName || "该附件"}」？`,
    });
  } catch {
    return;
  }
  try {
    await deleteSurveyAttachment(item.id);
    showToast("已删除");
    await loadAttachments();
  } catch (error) {
    showToast(error?.response?.data?.detail || "删除失败");
  }
}

onMounted(async () => {
  await loadCategories();
  await loadAttachments();
});
</script>

<style scoped>
.m-attach {
  padding-bottom: 24px;
}

.m-attach__capture {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 16px 6px;
}

.m-attach__hint {
  margin: 16px 24px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #a6adbb;
  text-align: center;
}

/* 识别诊断层 */
.attach-diag__title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  color: #1f2d3d;
}

.attach-diag__text {
  margin: 0 0 6px;
  font-size: 13px;
  line-height: 1.5;
  color: #333;
  word-break: break-all;
}

.attach-diag__img {
  display: block;
  width: 100%;
  margin: 8px 0;
  border: 1px solid #e5e6eb;
  border-radius: 6px;
}

.attach-diag__hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: #969799;
}
</style>
