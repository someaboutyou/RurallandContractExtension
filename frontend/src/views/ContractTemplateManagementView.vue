<template>
  <div class="contract-template-page">
    <div class="panel-title">合同模板管理</div>
    <el-empty v-if="!canManage" description="当前账号暂无权限访问合同模板管理模块。" />

    <template v-else>
      <div class="contract-template-toolbar">
        <div>
          <div class="template-file-name">{{ templateMeta.name || "contract.html" }}</div>
          <div class="template-file-meta">
            最后更新：{{ formatDateTime(templateMeta.updatedAt) }} · {{ formatSize(templateMeta.size) }}
          </div>
        </div>
        <div class="template-actions">
          <el-button :loading="loading" @click="loadTemplate">重新载入</el-button>
          <el-button :loading="previewing" plain type="primary" @click="handlePreview">预览</el-button>
          <el-button :loading="saving" type="success" @click="handleSave">保存模板</el-button>
        </div>
      </div>

      <el-alert
        class="template-alert"
        type="info"
        show-icon
        :closable="false"
        title="保存前会校验 Jinja 模板语法；保存后调查录入里的电子合同预览会立即使用新模板。"
      />

      <div class="contract-template-workspace">
        <section class="template-editor-pane">
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
            placeholder="请输入合同模板 HTML"
          />
        </section>

        <section class="template-preview-pane">
          <div class="pane-head">
            <span>样例数据预览</span>
            <span>{{ previewHtml ? "已渲染" : "未预览" }}</span>
          </div>
          <div v-loading="previewing" class="template-preview-frame">
            <iframe
              v-if="previewHtml"
              :srcdoc="previewHtml"
              title="合同模板预览"
              frameborder="0"
            />
            <el-empty v-else description="点击“预览”查看样例合同效果" />
          </div>
        </section>
      </div>

      <el-collapse class="template-helper">
        <el-collapse-item title="常用模板变量" name="vars">
          <div class="template-var-grid">
            <el-tag v-for="item in commonVars" :key="item" effect="plain">{{ item }}</el-tag>
          </div>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  fetchContractTemplate,
  previewContractTemplate,
  updateContractTemplate,
} from "../api/contractTemplate";
import { useAuthStore } from "../stores/auth";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasAnyPermission(["contract_templates.manage"]));

const loading = ref(false);
const saving = ref(false);
const previewing = ref(false);
const editorContent = ref("");
const previewHtml = ref("");
const templateMeta = reactive({
  name: "",
  updatedAt: "",
  size: 0,
});

const commonVars = [
  "{{ cbhtbm }}",
  "{{ fbfmc }}",
  "{{ fbf_fzr }}",
  "{{ cbfmc }}",
  "{{ cbfzjhm }}",
  "{{ cbfdz }}",
  "{{ contract_years }}",
  "{{ cbqxq_iso }}",
  "{{ cbqxz_iso }}",
  "{{ qdsj_cn }}",
  "{{ htzmjm }}",
  "{% for dk in parcels %}",
  "{% for member in family_members %}",
];

onMounted(() => {
  if (canManage.value) {
    loadTemplate();
  }
});

async function loadTemplate() {
  loading.value = true;
  try {
    const { data } = await fetchContractTemplate();
    const item = data.data || {};
    templateMeta.name = item.name || "contract.html";
    templateMeta.updatedAt = item.updatedAt || "";
    templateMeta.size = item.size || 0;
    editorContent.value = item.content || "";
    previewHtml.value = "";
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "读取合同模板失败");
  } finally {
    loading.value = false;
  }
}

async function handlePreview() {
  previewing.value = true;
  try {
    const { data } = await previewContractTemplate({ content: editorContent.value });
    previewHtml.value = data.data?.renderedHtml || "";
    ElMessage.success("预览已更新");
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "模板预览失败");
  } finally {
    previewing.value = false;
  }
}

async function handleSave() {
  try {
    await ElMessageBox.confirm(
      "保存后会覆盖当前合同模板，并影响后续所有电子合同预览。确定保存吗？",
      "保存合同模板",
      { type: "warning" },
    );
  } catch {
    return;
  }

  saving.value = true;
  try {
    const { data } = await updateContractTemplate({ content: editorContent.value });
    const item = data.data || {};
    templateMeta.name = item.name || "contract.html";
    templateMeta.updatedAt = item.updatedAt || "";
    templateMeta.size = item.size || 0;
    editorContent.value = item.content || editorContent.value;
    ElMessage.success("合同模板已保存");
    await handlePreview();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存合同模板失败");
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
