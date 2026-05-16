<template>
  <div class="contract-info-panel">
    <!-- 加载中 -->
    <el-skeleton v-if="loading" :rows="6" animated />

    <!-- 无合同 -->
    <el-empty v-else-if="!contract" description="该承包方暂无关联合同" />

    <!-- 合同信息 -->
    <div v-else class="contract-content">
      <!-- 合同基本信息栏 -->
      <div class="contract-summary">
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="合同编码">{{ contract.cbhtbm }}</el-descriptions-item>
          <el-descriptions-item label="承包方式">{{ cbfsLabel }}</el-descriptions-item>
          <el-descriptions-item label="地块总数">{{ contract.cbdkzs ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="签订日期">{{ contract.qdsj ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="承包期限起">{{ contract.cbqxq ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="承包期限止">{{ contract.cbqxz ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="合同总面积(㎡)">{{ contract.htzmj ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="合同总面积(亩)">{{ contract.htzmjm ?? '-' }}</el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 操作工具栏 -->
      <div class="contract-toolbar">
        <el-button type="primary" @click="handlePrint">
          <el-icon><Printer /></el-icon>
          打印合同
        </el-button>
        <el-upload
          ref="uploadRef"
          :show-file-list="false"
          :before-upload="beforeUpload"
          :http-request="handleUpload"
          accept=".pdf,.jpg,.jpeg,.png"
        >
          <el-button type="success">
            <el-icon><Upload /></el-icon>
            上传合同附件
          </el-button>
        </el-upload>
      </div>

      <!-- 电子合同预览 / 合同附件 -->
      <el-tabs v-model="contractTab" class="contract-view-tabs">
        <el-tab-pane label="电子合同" name="preview">
          <div class="contract-preview-wrapper">
            <iframe
              :srcdoc="contract.renderedHtml"
              class="contract-iframe"
              frameborder="0"
              title="合同预览"
            />
          </div>
        </el-tab-pane>
        <el-tab-pane :label="`合同附件（${attachments.length}）`" name="attachments">
          <el-table :data="attachments" border size="small" v-loading="attLoading">
            <el-table-column prop="originalName" label="文件名" min-width="200" />
            <el-table-column prop="category" label="类别" width="100">
              <template #default="{ row }">
                <el-tag size="small">{{ row.category }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
            <el-table-column label="上传时间" width="170">
              <template #default="{ row }">{{ row.createdAt?.slice(0, 16) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="handleDownload(row.id)">下载</el-button>
                <el-button link type="danger" size="small" @click="handleDelete(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Printer, Upload } from "@element-plus/icons-vue";
import {
  fetchSurveyContract,
  printSurveyContract,
} from "../../api/survey";
import {
  uploadSurveyAttachment,
  downloadSurveyAttachment,
  deleteSurveyAttachment,
} from "../../api/survey";

const props = defineProps({
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
});

const loading = ref(false);
const contract = ref(null);
const contractTab = ref("preview");
const attachments = ref([]);
const attLoading = ref(false);
const uploadRef = ref(null);

const cbfsLabel = computed(() => {
  const m = { "001": "家庭承包", "002": "其他方式承包", "003": "招标", "004": "拍卖", "005": "公开协商" };
  return m[contract.value?.cbfs] || contract.value?.cbfs || "-";
});

async function loadContract() {
  if (!props.batchId || !props.contractorUid) return;
  loading.value = true;
  try {
    const { data } = await fetchSurveyContract(props.batchId, props.contractorUid);
    contract.value = data.data;
  } catch {
    contract.value = null;
  } finally {
    loading.value = false;
  }
}

async function loadAttachments() {
  // 通过 phase2 接口获取 attachments，筛选 category === "contract"
  // phase2 接口已返回所有 attachments，我们在父组件传下来或在这里直接调
  // 为了独立性，这里用 phase2 的 fetch 方式读取
  attLoading.value = true;
  try {
    const { fetchSurveyPhase2 } = await import("../../api/survey");
    const { data } = await fetchSurveyPhase2(props.batchId, props.contractorUid);
    attachments.value = (data.data?.attachments || []).filter(
      (a) => a.category === "contract"
    );
  } catch {
    attachments.value = [];
  } finally {
    attLoading.value = false;
  }
}

async function handlePrint() {
  try {
    const { data } = await printSurveyContract(props.batchId, props.contractorUid);
    const w = window.open("", "_blank", "width=900,height=700");
    if (w) {
      w.document.write(data);
      w.document.close();
      setTimeout(() => w.print(), 500);
    }
  } catch {
    ElMessage.error("打印合同失败");
  }
}

async function beforeUpload(file) {
  const isValid = ["application/pdf", "image/jpeg", "image/png"].includes(file.type);
  if (!isValid) {
    ElMessage.error("仅支持 PDF、JPG、PNG 格式");
  }
  return isValid;
}

async function handleUpload({ file }) {
  const fd = new FormData();
  fd.append("category", "contract");
  fd.append("description", file.name);
  fd.append("file", file);
  try {
    await uploadSurveyAttachment(props.batchId, props.contractorUid, fd);
    ElMessage.success("上传成功");
    await loadAttachments();
  } catch {
    ElMessage.error("上传失败");
  }
}

async function handleDownload(attId) {
  try {
    const { data } = await downloadSurveyAttachment(attId);
    const url = window.URL.createObjectURL(new Blob([data]));
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    a.click();
    window.URL.revokeObjectURL(url);
  } catch {
    ElMessage.error("下载失败");
  }
}

async function handleDelete(attId) {
  try {
    await ElMessageBox.confirm("确定要删除此附件吗？", "确认删除", { type: "warning" });
    await deleteSurveyAttachment(attId);
    ElMessage.success("已删除");
    await loadAttachments();
  } catch {
    // cancelled
  }
}

watch(
  () => [props.batchId, props.contractorUid],
  () => {
    loadContract();
    loadAttachments();
  },
  { immediate: true }
);
</script>

<style scoped>
.contract-info-panel {
  min-height: 400px;
}
.contract-summary {
  margin-bottom: 12px;
}
.contract-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.contract-view-tabs {
  margin-top: 4px;
}
.contract-preview-wrapper {
  width: 100%;
  height: calc(92vh - 340px);
  min-height: 500px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}
.contract-iframe {
  width: 100%;
  height: 100%;
  border: none;
}
</style>
