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

async function onPreview(item) {
  try {
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
</style>
