<template>
  <div class="contract-template-page">
    <el-empty v-if="!canManage" description="当前账号暂无权限访问打印模板管理模块。" />

    <template v-else>
      <div class="template-page-body">
        <!-- 左侧：模板清单（按分组折叠） -->
        <aside class="template-list-pane">
          <div class="pane-title">打印模板</div>
          <el-input
            v-model="filterText"
            class="template-filter"
            placeholder="搜索模板"
            clearable
          />
          <div v-loading="listLoading" class="template-list-scroll">
            <div v-for="group in filteredGroups" :key="group.name" class="template-group">
              <div class="template-group-name">{{ group.name }}</div>
              <div
                v-for="item in group.items"
                :key="item.key"
                class="template-list-item"
                :class="{ active: item.key === selectedKey, missing: !item.available }"
                @click="selectTemplate(item)"
              >
                <span class="template-item-title">{{ item.title }}</span>
                <el-tag v-if="!item.available" type="danger" effect="plain" size="small">缺失</el-tag>
              </div>
            </div>
            <el-empty
              v-if="!listLoading && !filteredGroups.length"
              description="没有匹配的模板"
              :image-size="60"
            />
          </div>
        </aside>

        <!-- 右侧：查看 / 编辑 -->
        <section class="template-editor-pane">
          <div class="editor-toolbar">
            <div>
              <div class="editor-title">{{ currentTitle }}</div>
              <div class="editor-meta">
                {{ templateMeta.name || expectedFileName }}
                <template v-if="templateMeta.updatedAt">
                  · 最后更新：{{ formatDateTime(templateMeta.updatedAt) }} · {{ formatSize(templateMeta.size) }}
                </template>
              </div>
            </div>
            <div class="template-actions">
              <el-button :loading="loading" @click="loadTemplate">重新载入</el-button>
              <el-button
                :disabled="templateMissing"
                :loading="previewing"
                plain
                type="primary"
                @click="handlePreview"
              >
                预览
              </el-button>
              <el-button
                :disabled="templateMissing"
                :loading="downloading"
                plain
                type="warning"
                @click="handleDownloadBlankWord"
              >
                下载空白Word
              </el-button>
              <el-button :disabled="templateMissing" :loading="saving" type="success" @click="handleSave">
                保存模板
              </el-button>
            </div>
          </div>

          <el-alert
            v-if="templateMissing"
            class="template-alert"
            type="warning"
            show-icon
            :closable="false"
            :title="`${currentTitle}文件不存在。请后续将 ${expectedFileName} 补充到 backend/app/templates 后再编辑。`"
          />
          <el-alert
            v-else
            class="template-alert"
            type="info"
            show-icon
            :closable="false"
            title="保存前会校验 Jinja 模板语法；保存后业务打印预览会使用新的模板文件。「下载空白Word」按当前模板以空白上下文渲染导出。"
          />
          <el-alert
            v-if="currentItem?.note"
            class="template-alert"
            type="warning"
            show-icon
            :closable="false"
            :title="currentItem.note"
          />

          <div class="editor-workspace">
            <div class="pane-head">
              <span>HTML / Jinja 模板</span>
              <span>{{ editorContent.length }} 字符</span>
            </div>
            <el-input
              v-model="editorContent"
              class="template-editor"
              type="textarea"
              resize="none"
              spellcheck="false"
              :disabled="templateMissing"
              :placeholder="templateMissing ? '模板文件补充后可在这里编辑' : `请输入${currentTitle} HTML`"
            />
          </div>
        </section>
      </div>

      <!-- 预览：点击「预览」后以弹窗展示 -->
      <el-dialog
        v-model="previewVisible"
        :title="`${currentTitle}预览`"
        width="90%"
        top="4vh"
        destroy-on-close
        class="template-preview-dialog"
      >
        <div v-loading="previewing" class="template-preview-frame">
          <iframe v-if="previewHtml" :srcdoc="previewHtml" :title="`${currentTitle}预览`" frameborder="0" />
          <el-empty v-else description="暂无预览内容" />
        </div>
      </el-dialog>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  downloadBlankTemplateWord,
  fetchContractTemplate,
  fetchPrintTemplates,
  previewContractTemplate,
  updateContractTemplate,
} from "../api/contractTemplate";
import { useAuthStore } from "../stores/auth";

const DEFAULT_KEY = "contract";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasAnyPermission(["contract_templates.manage"]));

// ── 左侧清单 ──
const listLoading = ref(false);
const templateList = ref([]);
const filterText = ref("");
const selectedKey = ref(DEFAULT_KEY);

const filteredGroups = computed(() => {
  const keyword = filterText.value.trim().toLowerCase();
  const buckets = new Map();
  for (const item of templateList.value) {
    if (keyword && !`${item.title} ${item.filename}`.toLowerCase().includes(keyword)) {
      continue;
    }
    const name = item.group || "其他";
    if (!buckets.has(name)) buckets.set(name, []);
    buckets.get(name).push(item);
  }
  return Array.from(buckets, ([name, items]) => ({ name, items }));
});

const currentItem = computed(
  () => templateList.value.find((item) => item.key === selectedKey.value) || null,
);
const currentTitle = computed(() => templateMeta.title || currentItem.value?.title || "模板");
const expectedFileName = computed(() => currentItem.value?.filename || "");

async function loadList() {
  listLoading.value = true;
  try {
    const { data } = await fetchPrintTemplates();
    templateList.value = data?.data || [];
    if (!templateList.value.some((item) => item.key === selectedKey.value)) {
      selectedKey.value = templateList.value[0]?.key || DEFAULT_KEY;
    }
  } catch {
    ElMessage.error("加载模板清单失败");
  } finally {
    listLoading.value = false;
  }
}

function selectTemplate(item) {
  if (!item?.available || item.key === selectedKey.value) return;
  previewHtml.value = "";
  selectedKey.value = item.key;
  loadTemplate();
}

// ── 右侧编辑 ──
const loading = ref(false);
const saving = ref(false);
const previewing = ref(false);
const downloading = ref(false);
const templateMissing = ref(false);
const editorContent = ref("");
const previewHtml = ref("");
const previewVisible = ref(false);
const templateMeta = reactive({
  title: "",
  name: "",
  updatedAt: "",
  size: 0,
});

onMounted(() => {
  if (canManage.value) {
    loadList();
    loadTemplate();
  }
});

async function loadTemplate() {
  loading.value = true;
  templateMissing.value = false;
  try {
    const { data } = await fetchContractTemplate(selectedKey.value);
    const item = data.data || {};
    templateMeta.title = item.title || currentItem.value?.title || "";
    templateMeta.name = item.name || expectedFileName.value;
    templateMeta.updatedAt = item.updatedAt || "";
    templateMeta.size = item.size || 0;
    editorContent.value = item.content || "";
  } catch (error) {
    templateMeta.title = currentItem.value?.title || "";
    templateMeta.name = expectedFileName.value;
    templateMeta.updatedAt = "";
    templateMeta.size = 0;
    editorContent.value = "";
    if (error.response?.status === 404) {
      templateMissing.value = true;
      ElMessage.warning(error.response?.data?.detail || `${currentTitle.value}文件不存在`);
    } else {
      ElMessage.error(error.response?.data?.detail || "读取打印模板失败");
    }
  } finally {
    loading.value = false;
  }
}

async function handlePreview() {
  previewing.value = true;
  previewVisible.value = true;
  try {
    const { data } = await previewContractTemplate(selectedKey.value, { content: editorContent.value });
    previewHtml.value = data.data?.renderedHtml || "";
  } catch (error) {
    previewVisible.value = false;
    ElMessage.error(error.response?.data?.detail || "模板预览失败");
  } finally {
    previewing.value = false;
  }
}

async function handleDownloadBlankWord() {
  downloading.value = true;
  try {
    const { data } = await downloadBlankTemplateWord(selectedKey.value);
    const filename = `${currentTitle.value.replace(/模板$/, "")}.docx`;
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    ElMessage.success(`已下载空白 Word：${filename}`);
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "下载空白 Word 失败");
  } finally {
    downloading.value = false;
  }
}

async function handleSave() {
  try {
    await ElMessageBox.confirm(
      `保存后会覆盖当前${currentTitle.value}，并影响后续业务打印预览。确定保存吗？`,
      `保存${currentTitle.value}`,
      { type: "warning" },
    );
  } catch {
    return;
  }

  saving.value = true;
  try {
    const { data } = await updateContractTemplate(selectedKey.value, { content: editorContent.value });
    const item = data.data || {};
    templateMeta.title = item.title || currentItem.value?.title || "";
    templateMeta.name = item.name || expectedFileName.value;
    templateMeta.updatedAt = item.updatedAt || "";
    templateMeta.size = item.size || 0;
    editorContent.value = item.content || editorContent.value;
    ElMessage.success("打印模板已保存");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存打印模板失败");
  } finally {
    saving.value = false;
  }
}

function formatDateTime(value) {
  if (!value) return "-";
  return value.replace("T", " ").slice(0, 19);
}

function formatSize(value) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  return `${(value / 1024).toFixed(1)} KB`;
}
</script>

<style scoped>
.contract-template-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.template-page-body {
  display: flex;
  flex: 1 1 auto;
  gap: 12px;
  min-height: 0;
}

/* ── 左侧清单 ── */
.template-list-pane {
  display: flex;
  flex-direction: column;
  flex: 0 0 240px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--panel-strong);
  box-shadow: var(--shadow);
}

.pane-title {
  margin-bottom: 10px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}

.template-filter {
  margin-bottom: 10px;
}

.template-list-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}

.template-group + .template-group {
  margin-top: 14px;
}

.template-group-name {
  margin-bottom: 6px;
  padding-left: 8px;
  border-left: 3px solid var(--accent);
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.template-list-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  padding: 8px 10px;
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  color: var(--text);
  font-size: 13px;
}

.template-list-item:hover {
  background: var(--panel, rgba(0, 0, 0, 0.04));
}

.template-list-item.active {
  background: var(--el-color-primary-light-9, #ecf5ff);
  color: var(--el-color-primary, #409eff);
  font-weight: 700;
}

.template-list-item.missing {
  color: var(--el-color-danger, #f56c6c);
  cursor: not-allowed;
}

.template-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── 右侧编辑 ── */
.template-editor-pane {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 0;
}

.editor-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.editor-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}

.editor-meta {
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
}

.template-actions {
  display: flex;
  flex-shrink: 0;
  gap: 0;
}

.template-alert {
  margin-top: 10px;
}

.editor-workspace {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  margin-top: 10px;
}

.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-bottom: 0;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  background: var(--panel-strong);
  color: var(--muted);
  font-size: 12px;
}

.template-editor {
  flex: 1 1 auto;
  min-height: 0;
}

.template-editor :deep(.el-textarea__inner) {
  height: 100%;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.5;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

/* ── 预览弹窗 ── */
.template-preview-frame {
  height: 76vh;
  overflow: auto;
  background: #f2f3f5;
}

.template-preview-frame iframe {
  display: block;
  width: 100%;
  min-height: 100%;
  border: 0;
}

@media (max-width: 900px) {
  .template-page-body {
    flex-direction: column;
  }

  .template-list-pane {
    flex: 0 0 auto;
    max-height: 200px;
  }
}
</style>
