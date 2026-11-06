<template>
  <section class="panel template-page">
    <div class="toolbar template-toolbar">
      <div>
        <div class="panel-title">模板管理</div>
        <div class="template-subtitle">
          下载调查建库所需的调查表、声明书与申请书模板，模板格式与 CS 版建库系统一致。
        </div>
      </div>
      <div class="toolbar-actions">
        <el-button :loading="loading" plain @click="loadTemplates">刷新</el-button>
      </div>
    </div>

    <div v-loading="loading" class="template-scroll">
      <el-empty
        v-if="!loading && !templates.length"
        description="暂无可下载的模板文件"
      />

      <section v-for="group in groups" :key="group.name" class="template-group">
        <div class="template-group-title">{{ group.name }}</div>
        <div class="template-grid">
          <article v-for="item in group.items" :key="item.key" class="template-card">
            <div class="template-card-head">
              <span class="template-card-title">{{ item.label }}</span>
              <el-tag
                :type="item.format === 'Excel' ? 'success' : 'primary'"
                effect="plain"
                size="small"
              >
                {{ item.format }}
              </el-tag>
            </div>
            <p class="template-card-desc">{{ item.description || "—" }}</p>
            <div class="template-card-meta">
              <span class="template-card-file" :title="item.filename">{{ item.filename }}</span>
              <span>{{ formatSize(item.size) }}</span>
            </div>
            <div class="template-card-actions">
              <el-button
                :disabled="!item.available"
                :loading="downloadingKey === item.key"
                type="primary"
                @click="handleDownload(item)"
              >
                {{ item.available ? "下载模板" : "文件缺失" }}
              </el-button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { downloadSurveyTemplate, fetchSurveyTemplates } from "../api/surveyTemplate";

const loading = ref(false);
const templates = ref([]);
const downloadingKey = ref("");

const groups = computed(() => {
  const buckets = new Map();
  for (const item of templates.value) {
    const name = item.category || "其他";
    if (!buckets.has(name)) buckets.set(name, []);
    buckets.get(name).push(item);
  }
  return Array.from(buckets, ([name, items]) => ({ name, items }));
});

function formatSize(size) {
  const value = Number(size) || 0;
  if (!value) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

async function loadTemplates() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyTemplates();
    templates.value = data?.data || [];
  } catch {
    ElMessage.error("加载模板清单失败");
  } finally {
    loading.value = false;
  }
}

async function handleDownload(item) {
  if (!item?.available || downloadingKey.value) return;
  downloadingKey.value = item.key;
  try {
    const { data } = await downloadSurveyTemplate(item.key);
    const url = URL.createObjectURL(data);
    const link = document.createElement("a");
    link.href = url;
    link.download = item.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    ElMessage.success(`已下载：${item.label}（${item.format}）`);
  } catch {
    ElMessage.error("下载模板失败");
  } finally {
    downloadingKey.value = "";
  }
}

onMounted(loadTemplates);
</script>

<style scoped>
.template-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.template-toolbar {
  align-items: flex-start;
}

.template-subtitle {
  margin-top: -4px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.template-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding-right: 4px;
}

.template-group + .template-group {
  margin-top: 18px;
}

.template-group-title {
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid var(--accent);
  color: var(--text);
  font-size: 15px;
  font-weight: 700;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.template-card {
  display: flex;
  flex-direction: column;
  min-height: 168px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--panel-strong);
  box-shadow: var(--shadow);
}

.template-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.template-card-title {
  color: var(--text);
  font-size: 15px;
  font-weight: 700;
}

.template-card-desc {
  flex: 1 1 auto;
  margin: 10px 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.template-card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
}

.template-card-file {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-card-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

@media (max-width: 640px) {
  .template-grid {
    grid-template-columns: 1fr;
  }
}
</style>
