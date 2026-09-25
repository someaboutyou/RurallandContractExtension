<template>
  <div class="m-detail">
    <div v-if="loading" class="m-detail__loading">
      <van-loading size="22px" vertical>加载中…</van-loading>
    </div>

    <template v-else-if="result">
      <div class="m-detail__hero">
        <p class="m-detail__name">{{ result.cbfmc || "（未命名）" }}</p>
        <p class="m-detail__code">{{ result.cbfbm || "—" }}</p>
        <van-tag v-if="statusText" :type="statusTagType">{{ statusText }}</van-tag>
      </div>

      <van-cell-group inset title="承包方信息">
        <van-cell title="承包方地址" :value="result.cbfdz || '—'" />
        <van-cell title="联系电话" :value="result.lxdh || '—'" />
        <van-cell title="成员数量" :value="`${members.length} 人`" />
      </van-cell-group>

      <van-cell-group inset :title="`家庭成员（${members.length}）`">
        <van-cell
          v-for="member in members"
          :key="member.memberUid || member.idNo || member.name"
          :title="member.name || '（未填姓名）'"
          :label="memberLabel(member)"
        >
          <template #value>
            <van-tag v-if="member.isHouseholdHead" type="success" plain>户主</van-tag>
          </template>
        </van-cell>
        <van-cell v-if="!members.length" title="暂无成员数据" />
      </van-cell-group>

      <van-cell-group inset title="采集作业">
        <van-cell title="地块与勾绘" is-link value="进入" @click="goParcels" />
        <van-cell title="拍照附件" is-link value="进入" @click="goAttachments" />
      </van-cell-group>

      <div class="m-detail__actions">
        <van-button round block type="primary" @click="goAttachments">继续采集</van-button>
      </div>
    </template>

    <van-empty v-else description="未找到该承包方的调查数据" />
  </div>
</template>

<script setup>
/**
 * 承包方调查录入（移动端 · 只读视图 + 作业入口）。
 *
 * 数据源：`GET /surveys/batches/{batchId}/results/{contractorUid}` →
 * `data.data`（承包方主体字段 + `familyMembers` 数组）。
 *
 * 现状与边界：本页先打通「看数据 → 进作业页」的闭环，
 * 成员/地块的**编辑提交**复用现有接口（`updateSurveyResult` / `maintainSurveyMembers` /
 * `saveParcelBoundary` 等），按后续分期逐步接上；编辑形态与 PC 端保持一致口径，
 * 避免两端写出不同的校验规则。
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { fetchSurveyResult } from "../../api/survey";
import {
  VanButton,
  VanCell,
  VanCellGroup,
  VanEmpty,
  VanLoading,
  VanTag,
  showToast,
} from "../ui.js";

const STATUS_LABELS = {
  not_started: "未调查",
  not_surveyed: "未调查",
  in_progress: "调查中",
  surveyed: "已调查",
  changed: "有变化",
  unchanged: "无变化",
  confirmed: "已确认",
  skipped: "已跳过",
  deregistered: "已注销",
};

const route = useRoute();
const router = useRouter();

const batchId = computed(() => String(route.params.batchId || ""));
const contractorUid = computed(() => String(route.params.contractorUid || ""));

const loading = ref(true);
const result = ref(null);

const members = computed(() => result.value?.familyMembers || []);
const rawStatus = computed(() => result.value?.taskStatus || result.value?.surveyStatus || "");
const statusText = computed(() => STATUS_LABELS[rawStatus.value] || "");
const statusTagType = computed(() => {
  switch (rawStatus.value) {
    case "confirmed":
      return "success";
    case "surveyed":
    case "changed":
    case "in_progress":
      return "primary";
    case "skipped":
    case "deregistered":
      return "warning";
    default:
      return "default";
  }
});

function memberLabel(member) {
  const parts = [];
  if (member.relationToHead) parts.push(`与户主关系 ${member.relationToHead}`);
  if (member.idNo) {
    // 身份证号中间打码：外业场景常有人围观屏幕
    parts.push(maskIdNo(member.idNo));
  }
  return parts.join(" · ") || "—";
}

function maskIdNo(value) {
  const text = String(value);
  if (text.length < 8) return text;
  return `${text.slice(0, 6)}${"*".repeat(text.length - 10)}${text.slice(-4)}`;
}

async function loadResult() {
  loading.value = true;
  try {
    const { data } = await fetchSurveyResult(batchId.value, contractorUid.value);
    result.value = data?.data || null;
  } catch (error) {
    showToast(error?.response?.data?.detail || "调查数据加载失败");
    result.value = null;
  } finally {
    loading.value = false;
  }
}

function goParcels() {
  router.push({
    name: "mobile-task-parcels",
    params: { batchId: batchId.value, contractorUid: contractorUid.value },
  });
}

function goAttachments() {
  router.push({
    name: "mobile-task-attachments",
    params: { batchId: batchId.value, contractorUid: contractorUid.value },
  });
}

onMounted(loadResult);
</script>

<style scoped>
.m-detail {
  padding-bottom: 24px;
}

.m-detail__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
}

.m-detail__hero {
  padding: 18px 20px 20px;
  background: #fff;
  text-align: center;
}

.m-detail__name {
  margin: 0;
  font-size: 20px;
  font-weight: 500;
  color: #1f2d3d;
}

.m-detail__code {
  margin: 6px 0 10px;
  font-size: 12px;
  letter-spacing: 0.5px;
  color: #8a94a6;
}

.m-detail__actions {
  padding: 20px 16px 0;
}
</style>
