<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div>
        <div class="panel-title">承包方管理</div>
      </div>
      <div class="toolbar-actions toolbar-wrap">
        <el-input
          v-model="filters.name"
          clearable
          placeholder="承包方名称"
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.memberName"
          clearable
          placeholder="家庭成员名称"
          style="width: 160px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.idNo"
          clearable
          placeholder="证件号码"
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="filters.address"
          clearable
          placeholder="承包方地址"
          style="width: 180px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-button plain @click="handleSearch">查询</el-button>
        <el-button plain @click="resetFilters">重置</el-button>
        <el-button plain @click="loadData">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">新增承包方</el-button>
      </div>
    </div>

    <div class="contractor-workspace">
      <div class="contractor-table-area">
        <div class="table-shell">
          <div class="table-scroll">
            <el-table v-loading="loading" :data="rows" border>
              <el-table-column prop="code" label="承包方代码" min-width="180" />
              <el-table-column prop="name" label="承包方名称" min-width="180" />
              <el-table-column prop="typeCode" label="承包方类型" min-width="120">
                <template #default="{ row }">{{ contractorTypeLabel(row.typeCode) }}</template>
              </el-table-column>
              <el-table-column prop="mobile" label="联系电话" min-width="140" />
              <el-table-column prop="groupRegionName" label="所属组" min-width="180" show-overflow-tooltip />
              <el-table-column prop="address" label="承包方地址" min-width="260" />
              <el-table-column prop="memberCount" label="家庭成员数" min-width="110" />
              <el-table-column prop="surveyorName" label="调查员" min-width="120" />
              <el-table-column prop="surveyDate" label="调查日期" min-width="120" />
              <el-table-column v-if="canManage" label="操作" fixed="right" min-width="160">
                <template #default="{ row }">
                  <div class="table-actions">
                    <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
                    <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <div class="pagination-wrap">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            background
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </div>

      <aside class="contractor-region-panel">
        <div class="region-panel-head">
          <div>
            <div class="region-panel-title">区域筛选</div>
            <div class="region-panel-subtitle">{{ activeRegionLabel || "全部区域" }}</div>
          </div>
          <el-button link type="primary" @click="clearRegionFilter">全部</el-button>
        </div>
        <el-input
          v-model="regionNameKeyword"
          class="region-filter-search"
          clearable
          placeholder="按区域名称搜索"
        />
        <el-tree
          class="region-filter-tree"
          :data="displayRegionTree"
          node-key="value"
          highlight-current
          :current-node-key="activeRegionCode"
          :props="regionTreeProps"
          :expand-on-click-node="false"
          :default-expanded-keys="regionDefaultExpandedKeys"
        >
          <template #default="{ node, data }">
            <div class="region-tree-node">
              <button class="region-tree-label" type="button" @click.stop="handleRegionNodeClick(data)">
                {{ node.label }}
              </button>
              <el-dropdown trigger="click" @command="(command) => handleRegionAction(command, data)">
                <el-button link type="primary" class="region-tree-action" @click.stop>操作</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="printSurveyForms">批量打印调查表</el-dropdown-item>
                    <el-dropdown-item command="printRoster">打印承包方清册</el-dropdown-item>
                    <el-dropdown-item command="exportSurveyForms">导出调查表信息</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-tree>
      </aside>
    </div>
  </section>

  <el-dialog
    v-model="dialogVisible"
    :title="editingCode ? '编辑承包方' : '新增承包方'"
    class="contractor-dialog"
    width="92vw"
    top="3vh"
    destroy-on-close
  >
    <el-tabs v-model="activeMainTab" class="compact-dialog-tabs">
      <el-tab-pane label="承包方信息" name="base">
        <el-form ref="formRef" :model="form" :rules="rules" class="compact-form" label-position="top" status-icon>
          <div class="form-grid">
            <el-form-item label="承包方代码" prop="code">
              <el-input v-model="form.code" placeholder="请输入承包方代码" />
            </el-form-item>
            <el-form-item label="承包方类型" prop="typeCode">
              <el-select v-model="form.typeCode" placeholder="请选择承包方类型">
                <el-option label="农户" value="1" />
                <el-option label="个人" value="2" />
                <el-option label="单位" value="3" />
              </el-select>
            </el-form-item>
            <el-form-item label="承包方名称" prop="name">
              <el-input v-model="form.name" placeholder="请输入承包方名称" />
            </el-form-item>
            <el-form-item label="所属组" prop="groupRegionCode">
              <el-tree-select
                v-model="form.groupRegionCode"
                :data="regionTree"
                check-strictly
                clearable
                filterable
                node-key="value"
                placeholder="请选择所属组"
                :props="regionTreeProps"
                @change="handleGroupRegionChange"
              />
            </el-form-item>
            <el-form-item label="证件类型" prop="idType">
              <el-select v-model="form.idType" placeholder="请选择证件类型">
                <el-option label="居民身份证" value="1" />
                <el-option label="军官证" value="2" />
                <el-option label="护照" value="3" />
                <el-option label="户口簿" value="4" />
                <el-option label="其他" value="9" />
              </el-select>
            </el-form-item>
            <el-form-item label="证件号码" prop="idNo">
              <el-input v-model="form.idNo" placeholder="请输入证件号码" />
            </el-form-item>
            <el-form-item label="联系电话" prop="mobile">
              <el-input v-model="form.mobile" placeholder="请输入联系电话" />
            </el-form-item>
            <el-form-item label="邮政编码" prop="postcode">
              <el-input v-model="form.postcode" placeholder="请输入邮政编码" />
            </el-form-item>
            <el-form-item label="调查员" prop="surveyorName">
              <el-input v-model="form.surveyorName" placeholder="请输入调查员姓名" />
            </el-form-item>
            <el-form-item label="调查日期" prop="surveyDate">
              <el-date-picker
                class="form-date-picker"
                v-model="form.surveyDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择调查日期"
              />
            </el-form-item>
            <el-form-item class="form-span-2" label="承包方地址" prop="address">
              <el-input v-model="form.address" placeholder="请输入承包方地址" />
            </el-form-item>
            <el-form-item class="form-span-2" label="调查记事" prop="surveyNote">
              <el-input v-model="form.surveyNote" :rows="3" type="textarea" placeholder="请输入调查记事" />
            </el-form-item>
            <el-form-item class="form-span-2" label="公示记事" prop="publicNoticeNote">
              <el-input v-model="form.publicNoticeNote" :rows="3" type="textarea" placeholder="请输入公示记事" />
            </el-form-item>
            <el-form-item label="公示记事人" prop="publicNoticeRecorder">
              <el-input v-model="form.publicNoticeRecorder" placeholder="请输入公示记事人" />
            </el-form-item>
            <el-form-item label="公示审核日期" prop="publicNoticeReviewDate">
              <el-date-picker
                class="form-date-picker"
                v-model="form.publicNoticeReviewDate"
                type="date"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                placeholder="请选择公示审核日期"
              />
            </el-form-item>
            <el-form-item class="form-span-2" label="公示审核人" prop="publicNoticeReviewer">
              <el-input v-model="form.publicNoticeReviewer" placeholder="请输入公示审核人" />
            </el-form-item>
          </div>
        </el-form>
      </el-tab-pane>

      <el-tab-pane :disabled="form.typeCode !== '1'" :label="`家庭成员（${form.familyMembers.length}）`" name="family">
        <div v-if="form.typeCode !== '1'" class="family-empty">
          当前承包方类型不是农户，无需维护家庭成员信息。
        </div>

        <template v-else>
          <div class="member-tab-actions">
            <div class="member-tab-tip">
              <div class="member-tab-title">家庭成员维护</div>
              <div>家庭成员较多时，可在下方标签之间快速切换。</div>
            </div>
            <el-button type="primary" plain @click="appendFamilyMember">新增成员</el-button>
          </div>

          <el-tabs
            v-if="form.familyMembers.length"
            v-model="activeMemberTab"
            class="member-tabs"
            type="card"
            closable
            @tab-remove="removeFamilyMemberByKey"
          >
            <el-tab-pane
              v-for="(member, index) in form.familyMembers"
              :key="member._tabKey"
              :label="member.name?.trim() || `成员 ${index + 1}`"
              :name="member._tabKey"
            >
              <div class="member-pane-card">
                <div class="member-pane-header">
                  <div>
                    <div class="member-pane-name">{{ member.name?.trim() || `成员 ${index + 1}` }}</div>
                    <div class="member-pane-meta">
                      关系代码：{{ member.relationToHead || "未填写" }}
                      <span class="member-pane-dot">·</span>
                      证件号：{{ member.idNo || "未填写" }}
                    </div>
                  </div>
                </div>

                <el-form :model="member" class="compact-form member-form" label-position="top">
                  <div class="member-form-grid">
                    <el-form-item label="姓名">
                      <el-input v-model="member.name" placeholder="请输入姓名" />
                    </el-form-item>
                    <el-form-item label="性别">
                      <el-select v-model="member.gender" placeholder="请选择性别">
                        <el-option label="男" value="1" />
                        <el-option label="女" value="2" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="与户主关系">
                      <el-input v-model="member.relationToHead" placeholder="请输入关系代码，如 01" />
                    </el-form-item>
                    <el-form-item label="证件类型">
                      <el-select v-model="member.idType" placeholder="请选择证件类型">
                        <el-option label="居民身份证" value="1" />
                        <el-option label="军官证" value="2" />
                        <el-option label="护照" value="3" />
                        <el-option label="户口簿" value="4" />
                        <el-option label="其他" value="9" />
                      </el-select>
                    </el-form-item>
                    <el-form-item class="member-span-2" label="证件号码">
                      <el-input v-model="member.idNo" placeholder="请输入证件号码" />
                    </el-form-item>
                    <el-form-item label="是否共有人">
                      <el-select v-model="member.isCoOwner" clearable placeholder="请选择">
                        <el-option label="是" value="1" />
                        <el-option label="否" value="2" />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="备注代码">
                      <el-input v-model="member.noteCode" placeholder="如需填写请输入代码" />
                    </el-form-item>
                    <el-form-item class="member-span-full" label="成员备注说明">
                      <el-input v-model="member.note" type="textarea" :rows="3" placeholder="请输入成员备注说明" />
                    </el-form-item>
                  </div>
                </el-form>
              </div>
            </el-tab-pane>
          </el-tabs>

          <div v-else class="family-empty">
            暂无家庭成员，请点击右上角“新增成员”。
          </div>
        </template>
      </el-tab-pane>

      <el-tab-pane :disabled="!editingCode" label="地块信息" name="parcels">
        <div v-if="parcelsTabActivated" class="parcels-map-area">
          <div v-if="parcelsLoading" class="parcels-status">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>加载地块数据...</span>
          </div>
          <div v-else-if="parcelsError" class="parcels-status">
            <span>{{ parcelsError }}</span>
            <el-button size="small" @click="loadParcelData">重试</el-button>
          </div>
          <div v-else-if="parcelData.length === 0" class="parcels-status">
            <span>该承包方暂无关联地块信息。</span>
          </div>
          <template v-else>
            <div class="parcels-layout">
              <div class="parcels-map-container">
                <div ref="parcelMapRootRef" class="parcels-ol-map"></div>
                <div class="parcels-map-basemap">
                  <el-segmented
                    v-model="activeBasemap"
                    :options="basemapOptions"
                    size="small"
                    @change="switchBasemap"
                  />
                </div>
              </div>
              <div class="parcels-info-panel">
                <div class="parcels-info-title">地块列表 ({{ parcelData.length }})</div>
                <div class="parcels-info-list">
                  <div
                    v-for="item in parcelData"
                    :key="item.dkbm"
                    class="parcels-info-item"
                    :class="{ 'parcels-info-item--flash': flashDkbm === item.dkbm }"
                    @click="focusParcel(item)"
                  >
                    <div class="parcels-info-dkbm">{{ item.dkbm }}</div>
                    <div class="parcels-info-dkmc">{{ item.dkmc || '--' }}</div>
                    <div class="parcels-info-meta">
                      <span v-if="item.htmj">合同面积: {{ item.htmj }}m²</span>
                      <span v-if="item.scmj">实测面积: {{ item.scmj }}m²</span>
                    </div>
                  </div>
                </div>
              </div>
              <div class="parcels-detail-panel">
                <div class="parcels-detail-title">地块详情</div>
                <div v-if="!selectedParcel" class="parcels-detail-empty">点击左侧地块查看详细信息</div>
                <div v-else class="parcels-detail-list">
                  <div v-for="f in parcelDetailFields" :key="f.key" class="parcels-detail-row">
                    <div class="parcels-detail-label">{{ f.label }}</div>
                    <div class="parcels-detail-value">{{ selectedParcel[f.key] || '--' }}</div>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
        <div v-else class="parcels-status">
          <el-button type="primary" @click="activateParcelsTab">加载地块信息</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Loading } from "@element-plus/icons-vue";

import {
  createContractor,
  deleteContractor,
  fetchContractorDetail,
  fetchContractors,
  updateContractor,
} from "../api/contractor";
import { fetchContractorParcels } from "../api/landParcel";
import { fetchRegionTree } from "../api/region";
import { useAuthStore } from "../stores/auth";
import { useDialogMap } from "../composables/useDialogMap";
import { validateChinaId, validateMobile, validatePostcode } from "../utils/validators";

const authStore = useAuthStore();
const canManage = computed(() => authStore.hasPermission("contractors.manage"));

const loading = ref(false);
const submitting = ref(false);
const dialogVisible = ref(false);
const editingCode = ref("");
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const filters = reactive({
  name: "",
  memberName: "",
  idNo: "",
  address: "",
});
const regionTree = ref([]);
const filterRegionTree = ref([]);
const regionNameKeyword = ref("");
const activeRegionCode = ref("");
const activeRegionLabel = ref("");
const formRef = ref();
const activeMainTab = ref("base");
const activeMemberTab = ref("member-1");
let memberTabSeed = 0;
const regionTreeProps = {
  label: "label",
  children: "children",
};

const createMemberTabKey = () => {
  memberTabSeed += 1;
  return `member-${memberTabSeed}`;
};

const createEmptyFamilyMember = () => ({
  _tabKey: createMemberTabKey(),
  name: "",
  gender: "1",
  idType: "1",
  idNo: "",
  relationToHead: "",
  noteCode: "",
  isCoOwner: "1",
  note: "",
});

const createEmptyForm = () => ({
  code: "",
  typeCode: "1",
  name: "",
  idType: "1",
  idNo: "",
  address: "",
  postcode: "",
  mobile: "",
  surveyDate: "",
  surveyorName: "",
  surveyNote: "",
  publicNoticeNote: "",
  publicNoticeRecorder: "",
  publicNoticeReviewDate: "",
  publicNoticeReviewer: "",
  groupRegionCode: "",
  groupRegionName: "",
  familyMembers: [],
});

const form = reactive(createEmptyForm());

// --- Parcels tab state ---
const parcelsTabActivated = ref(false);
const parcelsLoading = ref(false);
const parcelsError = ref("");
const parcelData = ref([]);
const parcelMapRootRef = ref(null);

const {
  mapReady,
  activeBasemap,
  basemapOptions,
  selectedParcelDkbm,
  initMap,
  switchBasemap,
  loadParcels,
  fitToParcels,
  focusParcel: focusParcelOnMap,
  updateMapSize,
  destroyMap,
  clearSelection: clearMapSelection,
} = useDialogMap(parcelMapRootRef);

const flashDkbm = ref(null);
const selectedParcel = ref(null);

const parcelDetailFields = [
  { key: "dkbm", label: "地块编码" },
  { key: "dkmc", label: "地块名称" },
  { key: "htmj", label: "合同面积(m²)" },
  { key: "scmj", label: "实测面积(m²)" },
  { key: "syqxz", label: "所有权性质" },
  { key: "dklb", label: "地块类别" },
  { key: "dkdz", label: "地块地址" },
];

function triggerFlash(dkbm) {
  flashDkbm.value = dkbm;
  setTimeout(() => {
    if (flashDkbm.value === dkbm) {
      flashDkbm.value = null;
    }
  }, 2800);
}

async function activateParcelsTab() {
  parcelsTabActivated.value = true;
  await nextTick();
  await loadParcelData();
  await nextTick();
  if (parcelData.value.length > 0) {
    await initMap();
    setTimeout(() => updateMapSize(), 100);
  }
}

async function loadParcelData() {
  if (!editingCode.value) return;
  parcelsLoading.value = true;
  parcelsError.value = "";
  try {
    const { data } = await fetchContractorParcels(editingCode.value);
    parcelData.value = data.data || [];
    if (mapReady.value) {
      loadParcels(parcelData.value);
      if (parcelData.value.length > 0) {
        setTimeout(() => fitToParcels(), 300);
      }
    }
  } catch (error) {
    parcelsError.value = error.response?.data?.detail || "加载地块信息失败";
  } finally {
    parcelsLoading.value = false;
  }
}

function focusParcel(item) {
  selectedParcel.value = item;
  triggerFlash(item.dkbm);
  focusParcelOnMap(item.dkbm);
}

const validateMainIdNo = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入证件号码"));
    return;
  }
  if (form.idType === "1" && !validateChinaId(value)) {
    callback(new Error("请输入正确的身份证号"));
    return;
  }
  callback();
};

const validateMobileField = (_rule, value, callback) => {
  if (!value) {
    callback();
    return;
  }
  if (!validateMobile(value)) {
    callback(new Error("请输入正确的手机号"));
    return;
  }
  callback();
};

const validatePostcodeField = (_rule, value, callback) => {
  if (!value) {
    callback(new Error("请输入邮政编码"));
    return;
  }
  if (!validatePostcode(value)) {
    callback(new Error("请输入 6 位邮政编码"));
    return;
  }
  callback();
};

const rules = {
  code: [{ required: true, message: "请输入承包方代码", trigger: "blur" }],
  typeCode: [{ required: true, message: "请选择承包方类型", trigger: "change" }],
  name: [{ required: true, message: "请输入承包方名称", trigger: "blur" }],
  idType: [{ required: true, message: "请选择证件类型", trigger: "change" }],
  idNo: [{ validator: validateMainIdNo, trigger: "blur" }],
  address: [{ required: true, message: "请输入承包方地址", trigger: "blur" }],
  postcode: [{ validator: validatePostcodeField, trigger: "blur" }],
  mobile: [{ validator: validateMobileField, trigger: "blur" }],
  groupRegionCode: [{ required: true, message: "请选择所属组", trigger: "change" }],
  surveyorName: [{ required: true, message: "请输入调查员姓名", trigger: "blur" }],
};

watch(
  () => form.typeCode,
  (value) => {
    if (value === "1" && !form.familyMembers.length) {
      appendFamilyMember();
    }
    activeMainTab.value = "base";
  },
);

watch(activeMainTab, (tabName) => {
  if (tabName === "parcels" && !parcelsTabActivated.value) {
    activateParcelsTab();
  }
});

watch(mapReady, (ready) => {
  if (ready && parcelData.value.length > 0) {
    loadParcels(parcelData.value);
    setTimeout(() => fitToParcels(), 300);
  }
});

watch(dialogVisible, (visible) => {
  if (!visible) {
    parcelsTabActivated.value = false;
    parcelsError.value = "";
    parcelData.value = [];
    selectedParcel.value = null;
    flashDkbm.value = null;
    destroyMap();
  }
});

onBeforeUnmount(() => {
  destroyMap();
});

function resetForm() {
  Object.assign(form, createEmptyForm());
  activeMainTab.value = "base";
  activeMemberTab.value = "";
  formRef.value?.clearValidate();
}

function contractorTypeLabel(code) {
  return { 1: "农户", 2: "个人", 3: "单位" }[code] || code;
}

function normalizeRegionTree(nodes = []) {
  return nodes.map((item) => ({
    ...item,
    value: item.code,
    label: item.name,
    children: normalizeRegionTree(item.children || []),
  }));
}

function filterRegionNodesByName(nodes, keyword) {
  if (!keyword) {
    return nodes;
  }
  return nodes
    .map((item) => {
      const children = filterRegionNodesByName(item.children || [], keyword);
      if (item.label.includes(keyword) || children.length) {
        return { ...item, children };
      }
      return null;
    })
    .filter(Boolean);
}

function collectDefaultExpandedRegionKeys(nodes, expandTownLevel = false) {
  return nodes.flatMap((item) => {
    const children = item.children || [];
    const childKeys = collectDefaultExpandedRegionKeys(children, expandTownLevel);
    if (!children.length || (!expandTownLevel && item.level === "town")) {
      return childKeys;
    }
    return [item.value, ...childKeys];
  });
}

const displayRegionTree = computed(() => {
  const keyword = regionNameKeyword.value.trim();
  return filterRegionNodesByName(filterRegionTree.value, keyword);
});

const regionDefaultExpandedKeys = computed(() =>
  collectDefaultExpandedRegionKeys(displayRegionTree.value, Boolean(regionNameKeyword.value.trim())),
);

function findRegionNode(nodes, code) {
  for (const item of nodes) {
    if (item.value === code) {
      return item;
    }
    const matched = findRegionNode(item.children || [], code);
    if (matched) {
      return matched;
    }
  }
  return null;
}

function handleGroupRegionChange(code) {
  const node = findRegionNode(regionTree.value, code);
  form.groupRegionName = node?.label || "";
}

async function loadRegionTree() {
  const [{ data: groupTree }, { data: villageTree }] = await Promise.all([
    fetchRegionTree(undefined, { includeGroups: true }),
    fetchRegionTree("village"),
  ]);
  regionTree.value = normalizeRegionTree(groupTree.data || []);
  filterRegionTree.value = normalizeRegionTree(villageTree.data || []);
}

function appendFamilyMember() {
  const member = createEmptyFamilyMember();
  form.familyMembers.push(member);
  activeMemberTab.value = member._tabKey;
}

function removeFamilyMemberByKey(targetKey) {
  const index = form.familyMembers.findIndex((item) => item._tabKey === targetKey);
  if (index === -1) {
    return;
  }
  form.familyMembers.splice(index, 1);
  if (!form.familyMembers.length) {
    activeMemberTab.value = "";
    return;
  }
  const nextMember = form.familyMembers[index] || form.familyMembers[index - 1];
  activeMemberTab.value = nextMember._tabKey;
}

async function loadData() {
  loading.value = true;
  try {
    const { data } = await fetchContractors({
      page: page.value,
      page_size: pageSize.value,
      name: filters.name.trim() || undefined,
      memberName: filters.memberName.trim() || undefined,
      idNo: filters.idNo.trim() || undefined,
      address: filters.address.trim() || undefined,
      regionCode: activeRegionCode.value || undefined,
    });
    rows.value = data.data.items;
    total.value = data.data.total;
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadData();
}

function resetFilters() {
  filters.name = "";
  filters.memberName = "";
  filters.idNo = "";
  filters.address = "";
  handleSearch();
}

function handleRegionNodeClick(data) {
  activeRegionCode.value = data.value;
  activeRegionLabel.value = data.label;
  handleSearch();
}

function clearRegionFilter() {
  activeRegionCode.value = "";
  activeRegionLabel.value = "";
  handleSearch();
}

function handleRegionAction(command, data) {
  const actionMap = {
    printSurveyForms: "批量打印调查表",
    printRoster: "打印承包方清册",
    exportSurveyForms: "导出调查表信息",
  };
  ElMessage.info(`${data.label}：${actionMap[command]}功能已预留`);
}

function handlePageChange(value) {
  page.value = value;
  loadData();
}

function handlePageSizeChange(value) {
  pageSize.value = value;
  page.value = 1;
  loadData();
}

function openCreateDialog() {
  editingCode.value = "";
  resetForm();
  appendFamilyMember();
  dialogVisible.value = true;
}

async function openEditDialog(row) {
  editingCode.value = row.code;
  loading.value = true;
  try {
    const { data } = await fetchContractorDetail(row.code);
    const detail = data.data;
    Object.assign(form, {
      code: detail.code,
      typeCode: detail.typeCode,
      name: detail.name,
      idType: detail.idType,
      idNo: detail.idNo,
      address: detail.address,
      postcode: detail.postcode,
      mobile: detail.mobile || "",
      surveyDate: detail.surveyDate || "",
      surveyorName: detail.surveyorName,
      surveyNote: detail.surveyNote || "",
      publicNoticeNote: detail.publicNoticeNote || "",
      publicNoticeRecorder: detail.publicNoticeRecorder || "",
      publicNoticeReviewDate: detail.publicNoticeReviewDate || "",
      publicNoticeReviewer: detail.publicNoticeReviewer || "",
      groupRegionCode: detail.groupRegionCode || "",
      groupRegionName: detail.groupRegionName || "",
      familyMembers: detail.familyMembers?.length
        ? detail.familyMembers.map((item) => ({ ...item, _tabKey: createMemberTabKey() }))
        : [],
    });
    activeMainTab.value = "base";
    activeMemberTab.value = form.familyMembers[0]?._tabKey || "";
    await nextTick();
    formRef.value?.clearValidate();
    dialogVisible.value = true;
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "加载承包方详情失败");
  } finally {
    loading.value = false;
  }
}

function validateFamilyMembers() {
  if (form.typeCode !== "1") {
    return true;
  }
  for (const member of form.familyMembers) {
    if (!member.name || !member.gender || !member.idType || !member.idNo || !member.relationToHead) {
      activeMainTab.value = "family";
      activeMemberTab.value = member._tabKey;
      ElMessage.warning("农户类型下，家庭成员信息需要填写完整");
      return false;
    }
    if (member.idType === "1" && !validateChinaId(member.idNo)) {
      activeMainTab.value = "family";
      activeMemberTab.value = member._tabKey;
      ElMessage.warning(`家庭成员“${member.name || "未命名成员"}”的身份证号格式不正确`);
      return false;
    }
  }
  return true;
}

async function handleSubmit() {
  const valid = await formRef.value.validate().catch(() => false);
  if (!valid) {
    activeMainTab.value = "base";
    ElMessage.warning("请先修正承包方信息中的校验问题");
    return;
  }
  if (!validateFamilyMembers()) {
    return;
  }

  const payload = {
    code: form.code.trim(),
    typeCode: form.typeCode,
    name: form.name.trim(),
    idType: form.idType,
    idNo: form.idNo.trim(),
    address: form.address.trim(),
    postcode: form.postcode.trim(),
    mobile: form.mobile.trim() || null,
    surveyDate: form.surveyDate || null,
    surveyorName: form.surveyorName.trim(),
    surveyNote: form.surveyNote.trim() || null,
    publicNoticeNote: form.publicNoticeNote.trim() || null,
    publicNoticeRecorder: form.publicNoticeRecorder.trim() || null,
    publicNoticeReviewDate: form.publicNoticeReviewDate || null,
    publicNoticeReviewer: form.publicNoticeReviewer.trim() || null,
    groupRegionCode: form.groupRegionCode || null,
    groupRegionName: form.groupRegionName || null,
    familyMembers:
      form.typeCode === "1"
        ? form.familyMembers.map((item) => ({
            name: item.name.trim(),
            gender: item.gender,
            idType: item.idType,
            idNo: item.idNo.trim(),
            relationToHead: item.relationToHead.trim(),
            noteCode: item.noteCode?.trim() || null,
            isCoOwner: item.isCoOwner || null,
            note: item.note?.trim() || null,
          }))
        : [],
  };

  submitting.value = true;
  try {
    if (editingCode.value) {
      await updateContractor(editingCode.value, payload);
      ElMessage.success("承包方已更新");
    } else {
      await createContractor(payload);
      ElMessage.success("承包方已创建");
    }
    dialogVisible.value = false;
    resetForm();
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || "保存失败");
  } finally {
    submitting.value = false;
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除承包方“${row.name}”吗？该操作不可恢复。`, "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteContractor(row.code);
    ElMessage.success("承包方已删除");
    if (rows.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await loadData();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.detail || "删除失败");
    }
  }
}

loadRegionTree();
loadData();
</script>
