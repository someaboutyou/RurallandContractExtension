<template>
  <div class="contract-template-page">
    <div class="panel-title">{{ currentTitle }}管理</div>
    <el-empty v-if="!canManage" description="当前账号暂无权限访问打印模板管理模块。" />

    <template v-else>
      <div class="contract-template-toolbar">
        <div>
          <div class="template-file-name">{{ templateMeta.name || expectedFileName }}</div>
          <div class="template-file-meta">
            最后更新：{{ formatDateTime(templateMeta.updatedAt) }} · {{ formatSize(templateMeta.size) }}
          </div>
        </div>
        <div class="template-actions">
          <el-button :loading="loading" @click="loadTemplate">重新载入</el-button>
          <el-button :disabled="templateMissing" :loading="previewing" plain type="primary" @click="handlePreview">
            预览
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
        title="保存前会校验 Jinja 模板语法；保存后业务打印预览会使用新的模板文件。"
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
            :disabled="templateMissing"
            :placeholder="templateMissing ? '模板文件补充后可在这里编辑' : `请输入${currentTitle} HTML`"
          />
        </section>

        <section class="template-preview-pane">
          <div class="pane-head">
            <span>样例数据预览</span>
            <span>{{ previewHtml ? "已渲染" : "未预览" }}</span>
          </div>
          <div v-loading="previewing" class="template-preview-frame">
            <iframe v-if="previewHtml" :srcdoc="previewHtml" :title="`${currentTitle}预览`" frameborder="0" />
            <el-empty v-else :description="templateMissing ? '模板文件不存在' : '点击“预览”查看样例效果'" />
          </div>
        </section>
      </div>

      <el-collapse v-if="!templateMissing" class="template-helper">
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
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  fetchContractTemplate,
  previewContractTemplate,
  updateContractTemplate,
} from "../api/contractTemplate";
import { useAuthStore } from "../stores/auth";

const TEMPLATE_OPTIONS = {
  contract: { title: "合同模板", filename: "contract.html" },
  "plot-sketch-map": { title: "承包地块示意图模板", filename: "poltsketchmap.html" },
  "registration-application": { title: "不动产登记申请书模板", filename: "registration_application.html" },
  "cadastral-survey": { title: "地籍调查表模板", filename: "cadastral_survey.html" },
  "issuer-survey": { title: "发包方调查表模板", filename: "issuer_survey.html" },
};

const route = useRoute();
const authStore = useAuthStore();
const canManage = computed(() => authStore.hasAnyPermission(["contract_templates.manage"]));
const currentTemplateKey = computed(() => route.meta.templateKey || "contract");
const currentConfig = computed(() => TEMPLATE_OPTIONS[currentTemplateKey.value] || TEMPLATE_OPTIONS.contract);
const currentTitle = computed(() => templateMeta.title || currentConfig.value.title);
const expectedFileName = computed(() => currentConfig.value.filename);

const loading = ref(false);
const saving = ref(false);
const previewing = ref(false);
const templateMissing = ref(false);
const editorContent = ref("");
const previewHtml = ref("");
const templateMeta = reactive({
  title: "",
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

watch(
  () => currentTemplateKey.value,
  () => {
    if (canManage.value) {
      loadTemplate();
    }
  },
);

async function loadTemplate() {
  loading.value = true;
  templateMissing.value = false;
  try {
    const { data } = await fetchContractTemplate(currentTemplateKey.value);
    const item = data.data || {};
    templateMeta.title = item.title || currentConfig.value.title;
    templateMeta.name = item.name || currentConfig.value.filename;
    templateMeta.updatedAt = item.updatedAt || "";
    templateMeta.size = item.size || 0;
    editorContent.value = item.content || "";
    previewHtml.value = "";
  } catch (error) {
    templateMeta.title = currentConfig.value.title;
    templateMeta.name = currentConfig.value.filename;
    templateMeta.updatedAt = "";
    templateMeta.size = 0;
    editorContent.value = "";
    previewHtml.value = "";
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
  try {
    const { data } = await previewContractTemplate(currentTemplateKey.value, { content: editorContent.value });
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
      `保存后会覆盖当前${currentTitle.value}，并影响后续业务打印预览。确定保存吗？`,
      `保存${currentTitle.value}`,
      { type: "warning" },
    );
  } catch {
    return;
  }

  saving.value = true;
  try {
    const { data } = await updateContractTemplate(currentTemplateKey.value, { content: editorContent.value });
    const item = data.data || {};
    templateMeta.title = item.title || currentConfig.value.title;
    templateMeta.name = item.name || currentConfig.value.filename;
    templateMeta.updatedAt = item.updatedAt || "";
    templateMeta.size = item.size || 0;
    editorContent.value = item.content || editorContent.value;
    ElMessage.success("打印模板已保存");
    await handlePreview();
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
