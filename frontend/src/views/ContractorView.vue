<template>
  <section class="panel table-page">
    <div class="toolbar">
      <div class="panel-title">承包方管理</div>
      <div class="toolbar-actions">
        <el-button plain @click="loadData">刷新</el-button>
        <el-button v-if="canManage" type="success" @click="openCreateDialog">新增承包方</el-button>
      </div>
    </div>

    <div class="table-shell">
      <div class="table-scroll">
        <el-table v-loading="loading" :data="rows" border>
          <el-table-column prop="code" label="承包方代码" min-width="180" />
          <el-table-column prop="name" label="承包方名称" min-width="180" />
          <el-table-column prop="typeCode" label="承包方类型" min-width="120">
            <template #default="{ row }">{{ contractorTypeLabel(row.typeCode) }}</template>
          </el-table-column>
          <el-table-column prop="mobile" label="联系电话" min-width="140" />
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
  </section>

  <el-dialog
    v-model="dialogVisible"
    :title="editingCode ? '编辑承包方' : '新增承包方'"
    class="contractor-dialog"
    width="980px"
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
    </el-tabs>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button :loading="submitting" type="success" @click="handleSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createContractor,
  deleteContractor,
  fetchContractorDetail,
  fetchContractors,
  updateContractor,
} from "../api/contractor";
import { useAuthStore } from "../stores/auth";
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
const keyword = ref("");
const typeFilter = ref("");
const formRef = ref();
const activeMainTab = ref("base");
const activeMemberTab = ref("member-1");
let memberTabSeed = 0;

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
  familyMembers: [],
});

const form = reactive(createEmptyForm());

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

function resetForm() {
  Object.assign(form, createEmptyForm());
  activeMainTab.value = "base";
  activeMemberTab.value = "";
  formRef.value?.clearValidate();
}

function contractorTypeLabel(code) {
  return { 1: "农户", 2: "个人", 3: "单位" }[code] || code;
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
      keyword: keyword.value.trim() || undefined,
      typeCode: typeFilter.value || undefined,
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
  keyword.value = "";
  typeFilter.value = "";
  handleSearch();
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

loadData();
</script>
