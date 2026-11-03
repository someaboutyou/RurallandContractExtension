<template>
  <div class="contractor-member-panel">
    <!-- 变化提示 -->
    <el-alert
      v-if="result.isChanged"
      title="承包方信息已发生变化"
      type="warning"
      :closable="false"
      show-icon
      class="change-alert"
    >
      <template #default>
        <el-button link type="warning" size="small" @click="diffViewer?.open(batchId, contractorUid)">
          查看变化详情
        </el-button>
      </template>
    </el-alert>

    <!-- 承包方基本信息（可编辑） -->
    <div class="section-heading">
      <span class="section-title">承包方信息</span>
      <el-tag v-if="isAddedContractor" type="success" effect="dark" size="small" class="new-tag">NEW</el-tag>
    </div>
    <el-form :model="result" label-position="left" label-width="118px" class="contractor-form" :disabled="readonly">
      <div class="form-grid-3">
        <el-form-item label="承包方编码" required :class="changedClass('code')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('code'), beforeValueText('code'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input :model-value="result.code" placeholder="18位编码" maxlength="18" readonly @input="handleCodeInput">
              <template v-if="canGenerateCode" #append>
                <el-button @click="emit('generate-code')">生成</el-button>
              </template>
            </el-input>
          </div>
        </el-form-item>
        <el-form-item label="承包方名称" required :class="changedClass('name')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('name'), beforeValueText('name'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.name" placeholder="承包方名称" maxlength="50" />
          </div>
        </el-form-item>
        <el-form-item label="承包方类型" required :class="changedClass('typeCode')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('typeCode'), beforeValueText('typeCode'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="result.typeCode">
              <el-option label="农户" value="1" />
              <el-option label="个人" value="2" />
              <el-option label="单位" value="3" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="证件类型" required :class="changedClass('idType')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('idType'), beforeValueText('idType'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="result.idType">
              <el-option label="居民身份证" value="1" />
              <el-option label="户口簿" value="2" />
              <el-option label="军官证" value="3" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item label="证件号码" required :class="changedClass('idNo')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('idNo'), beforeValueText('idNo'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <div class="idno-field" :class="idNoFieldClass(contractorIdNoIssue)">
              <el-input v-model="result.idNo" placeholder="证件号码" :maxlength="ID_NO_MAX_LENGTH" />
              <div v-if="contractorIdNoIssue" class="idno-field__tip">{{ contractorIdNoIssue.message }}</div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="联系电话" :class="changedClass('mobile')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('mobile'), beforeValueText('mobile'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.mobile" placeholder="联系电话" maxlength="20" />
          </div>
        </el-form-item>
        <el-form-item label="承包方成员数量" :class="changedClass('memberCount')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('memberCount'), beforeValueText('memberCount'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input :model-value="currentMemberCount" readonly />
          </div>
        </el-form-item>
      </div>
      <el-form-item class="form-span-3" label="承包方地址" required :class="changedClass('address')">
        <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('address'), beforeValueText('address'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
          <el-input v-model="result.address" placeholder="详细地址" maxlength="100" />
        </div>
      </el-form-item>
      <div class="form-grid-2">
        <el-form-item label="邮政编码" required :class="changedClass('postcode')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('postcode'), beforeValueText('postcode'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.postcode" placeholder="6位邮编" maxlength="6" />
          </div>
        </el-form-item>
        <el-form-item label="村民小组" :class="changedClass('groupRegionName')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('groupRegionName'), beforeValueText('groupRegionName'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.groupRegionName" placeholder="村民小组" maxlength="120" />
          </div>
        </el-form-item>
      </div>
      <div class="section-subtitle">调查信息</div>
      <div class="form-grid-2">
        <el-form-item label="承包方调查员" :class="changedClass('surveyorName')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('surveyorName'), beforeValueText('surveyorName'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.surveyorName" placeholder="调查员姓名" maxlength="50" />
          </div>
        </el-form-item>
        <el-form-item label="承包方调查日期" :class="changedClass('surveyDate')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('surveyDate'), beforeValueText('surveyDate'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-date-picker
              v-model="result.surveyDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              placeholder="选择调查日期"
              style="width: 100%"
            />
          </div>
        </el-form-item>
      </div>
      <el-form-item class="form-span-2" label="承包方调查记事" :class="changedClass('surveyNote')">
        <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('surveyNote'), beforeValueText('surveyNote'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
          <el-input
            v-model="result.surveyNote"
            type="textarea"
            :rows="2"
            placeholder="调查记事"
            maxlength="254"
            show-word-limit
          />
        </div>
      </el-form-item>
      <div class="section-subtitle">公示审核信息</div>
      <el-form-item class="form-span-2" label="公示记事" :class="changedClass('publicNoticeNote')">
        <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeNote'), beforeValueText('publicNoticeNote'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
          <el-input
            v-model="result.publicNoticeNote"
            type="textarea"
            :rows="2"
            placeholder="公示记事"
            maxlength="254"
            show-word-limit
          />
        </div>
      </el-form-item>
      <div class="form-grid-3">
        <el-form-item label="公示记事人" :class="changedClass('publicNoticeRecorder')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeRecorder'), beforeValueText('publicNoticeRecorder'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.publicNoticeRecorder" placeholder="公示记事人" maxlength="50" />
          </div>
        </el-form-item>
        <el-form-item label="公示审核日期" :class="changedClass('publicNoticeReviewDate')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeReviewDate'), beforeValueText('publicNoticeReviewDate'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-date-picker
              v-model="result.publicNoticeReviewDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              placeholder="选择审核日期"
              style="width: 100%"
            />
          </div>
        </el-form-item>
        <el-form-item label="公示审核人" :class="changedClass('publicNoticeReviewer')">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isContractorFieldChanged('publicNoticeReviewer'), beforeValueText('publicNoticeReviewer'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="result.publicNoticeReviewer" placeholder="公示审核人" maxlength="50" />
          </div>
        </el-form-item>
      </div>
      <!-- 变化原因 / 政策依据
           只在「这一户存在变化」时出现：is_changed 或 change_type 非 none。
           ⛔ 这两项是「确认调查结果」的硬闸门（后端 _validate_confirmable），
           以往界面上没有任何录入入口，导致合户/分户生成的户、以及改过任意字段的户
           永远确认不了。这里补上入口。
           「变化原因」现在大多由系统预填：合户/分户生成的新户与成员，后端按操作
           类型自动写入（如「因合户设立新户」），此处留空不会导致确认失败 —— 只有
           需要覆盖系统文案时才填。「政策依据」是政策法规凭据，**选填**（不再强制）。
           故意不做 diff 高亮：它们是新增的补充说明，不是从基线改过来的字段。 -->
      <template v-if="showChangeFields">
        <div class="section-subtitle">变化信息</div>
        <div class="form-grid-2">
          <el-form-item label="变化原因" :required="showChangeFields">
            <el-input
              v-model="result.changeReason"
              type="textarea"
              :rows="2"
              placeholder="留空将由系统按操作类型自动填写（如「因合户设立新户」）"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="政策依据">
            <el-input
              v-model="result.policyBasis"
              type="textarea"
              :rows="2"
              placeholder="选填：政策法规依据，如 XX 文件 / 村组决议"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
        </div>
      </template>
    </el-form>

    <el-divider />

    <!-- 家庭成员（可编辑表格） -->
    <div class="section-header">
      <span class="section-title">家庭成员（{{ visibleMembers.length }} 人）</span>
      <el-button type="primary" plain size="small" :disabled="readonly" @click="addMember">+ 添加成员</el-button>
    </div>

    <el-table :data="visibleMembers" border size="small" class="member-table">
      <!-- 状态 -->
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag v-if="isNewRow(row)" type="success" size="small">新增</el-tag>
          <el-tag v-else-if="isModifiedRow(row)" type="warning" size="small">已修改</el-tag>
          <el-tag v-else-if="row._deleted" type="danger" size="small">待删除</el-tag>
          <el-tag v-else type="info" size="small">正常</el-tag>
        </template>
      </el-table-column>

      <!-- 姓名 -->
      <el-table-column label="姓名" min-width="100">
        <template #header><span class="req-star">*</span>姓名</template>
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'name'), memberBeforeValueText(row, 'name'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="row.name" size="small" :disabled="readonly || row._deleted" :class="memberChangedClass(row, 'name')" />
          </div>
        </template>
      </el-table-column>

      <!-- 性别 -->
      <el-table-column label="性别" width="80">
        <template #header><span class="req-star">*</span>性别</template>
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'gender'), memberBeforeValueText(row, 'gender'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="row.gender" size="small" :disabled="readonly || row._deleted" :class="memberChangedClass(row, 'gender')">
              <el-option label="男" value="1" />
              <el-option label="女" value="2" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 证件类型 -->
      <el-table-column label="证件类型" width="100">
        <template #header><span class="req-star">*</span>证件类型</template>
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'idType'), memberBeforeValueText(row, 'idType'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="row.idType" size="small" :disabled="readonly || row._deleted" :class="memberChangedClass(row, 'idType')">
              <el-option label="身份证" value="1" />
              <el-option label="户口簿" value="2" />
              <el-option label="军官证" value="3" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 证件号码 -->
      <el-table-column label="证件号码" min-width="180">
        <template #header><span class="req-star">*</span>证件号码</template>
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'idNo'), memberBeforeValueText(row, 'idNo'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <div class="idno-field" :class="idNoFieldClass(memberIdNoIssue(row))">
              <el-input v-model="row.idNo" size="small" :maxlength="ID_NO_MAX_LENGTH" :disabled="readonly || row._deleted" :class="memberChangedClass(row, 'idNo')" />
              <div v-if="memberIdNoIssue(row)" class="idno-field__tip">{{ memberIdNoIssue(row).message }}</div>
            </div>
          </div>
        </template>
      </el-table-column>

      <!-- 与户主关系 -->
      <el-table-column label="与户主关系" width="130">
        <template #header><span class="req-star">*</span>与户主关系</template>
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'relationToHead'), memberBeforeValueText(row, 'relationToHead'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select
              v-model="row.relationToHead"
              size="small"
              filterable
              :disabled="readonly || row._deleted"
              :class="memberChangedClass(row, 'relationToHead')"
              @change="handleRelationChange(row)"
            >
              <el-option
                v-for="opt in relationOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 共有人 -->
      <el-table-column label="共有人" width="80">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'isCoOwner'), memberBeforeValueText(row, 'isCoOwner'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-select v-model="row.isCoOwner" size="small" :disabled="readonly || row._deleted" :class="memberChangedClass(row, 'isCoOwner')">
              <el-option label="是" value="1" />
              <el-option label="否" value="0" />
            </el-select>
          </div>
        </template>
      </el-table-column>

      <!-- 户主标记与操作 -->
      <el-table-column label="户主" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.isHouseholdHead" type="danger" size="small" effect="dark">户主</el-tag>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <div class="diff-trigger" @mouseenter="showDiffTooltip(isMemberFieldChanged(row, 'note'), memberBeforeValueText(row, 'note'), $event)" @mousemove="moveDiffTooltip" @mouseleave="hideDiffTooltip">
            <el-input v-model="row.note" size="small" :disabled="readonly || row._deleted" :class="memberChangedClass(row, 'note')" />
          </div>
        </template>
      </el-table-column>

      <el-table-column label="变化原因" min-width="130">
        <template #header><span v-if="hasMemberChangeRequired" class="req-star">*</span>变化原因</template>
        <template #default="{ row }">
          <el-select
            v-if="isNewRow(row)"
            v-model="row.changeReason"
            size="small"
            placeholder="新增原因"
          >
            <el-option label="新生" value="新生" />
            <el-option label="婚进" value="婚进" />
            <el-option label="其他" value="其他" />
          </el-select>
          <el-select
            v-else-if="row._deleted"
            v-model="row.changeReason"
            size="small"
            placeholder="删除原因"
          >
            <el-option label="去世" value="去世" />
            <el-option label="婚出" value="婚出" />
            <el-option label="迁出" value="迁出" />
            <el-option label="其他" value="其他" />
          </el-select>
          <el-input
            v-else
            v-model="row.changeReason"
            size="small"
            placeholder="变化说明（系统操作产生的变化会自动填写）"
            maxlength="500"
          />
        </template>
      </el-table-column>

      <!-- 操作 -->
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            size="small"
            :disabled="row._deleted"
            @click="openSheetDialog(row)"
          >
            摸底
          </el-button>
          <el-button
            v-if="!readonly && !row._deleted && !row.isHouseholdHead"
            link
            type="danger"
            size="small"
            @click="toggleDelete(row)"
          >
            删除
          </el-button>
          <el-button
            v-if="!readonly && row._deleted"
            link
            type="primary"
            size="small"
            @click="toggleDelete(row)"
          >
            恢复
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 成员摸底信息（家庭成员变化摸底表的填写入口，随「保存调查结果」一并提交）
         2026-10-15 界面重构（用户要求：去掉「列 N」术语、布局舒适）：
         ① 一、1996 年时点：是否本户家庭成员；二、三 = 两个承包期，每期 =
           事件下拉（仅进出 8 类，按在户状态过滤）+ 事件时间 + 「已补地」「被抽回
           或放弃承包地」两个独立复选框（与事件正交可同时成立）；
         ② 四、成员属性；五、身份标识与备注；
         ③ 打印表中的「成员增减变动时间」由两期事件时间自动取最后者，无需填写；
         ④ 事件下拉若已有值与当前在户状态矛盾（历史数据），以「（与状态矛盾）」
           后缀兜底显示，保存时会被状态机拦截并逐条点名。 -->
    <el-dialog
      v-model="sheetDialogVisible"
      :title="`成员摸底信息 — ${sheetEditRow?.name || '未命名成员'}`"
      width="680px"
      append-to-body
      destroy-on-close
    >
      <el-form v-if="sheetEditRow" label-position="top" :disabled="readonly" class="sheet-form">
        <div class="sheet-section">一、1996 年二轮承包时点</div>
        <div class="sheet-grid">
          <el-form-item label="当时是否本户家庭成员">
            <el-select v-model="sheetEditRow.sheet.isSecondRoundMember" size="small" @change="reconcileSheetEvents">
              <el-option v-for="opt in YES_NO_UNSET_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
          <div class="sheet-hint">
            「参与二轮承包人口」「确权登记家庭成员」由系统按摸底表口径自动推导，无需在此填写。
          </div>
        </div>

        <div class="sheet-section">二、二轮承包期 · 1996 — 2018（确权颁证前）</div>
        <div class="sheet-grid">
          <el-form-item label="期内事件">
            <el-select v-model="sheetEditRow.sheet.srEventType" size="small" filterable clearable placeholder="未填" @change="reconcileSheetEvents">
              <el-option v-for="opt in srOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="事件时间">
            <el-date-picker v-model="sheetEditRow.sheet.srEventDate" type="date" size="small" format="YYYY-MM-DD" value-format="YYYY-MM-DD" placeholder="选择日期" :disabled-date="disableSrDate" />
          </el-form-item>
          <el-form-item label="补地与承包地处置" class="sheet-span-2">
            <div class="sheet-checks">
              <el-checkbox v-model="sheetEditRow.sheet.srCompensated">已补地</el-checkbox>
              <el-checkbox v-model="sheetEditRow.sheet.srWithdraw">被抽回或放弃承包地</el-checkbox>
            </div>
          </el-form-item>
        </div>

        <div class="sheet-section">三、延包期 · 2018 — 2026（确权颁证后）</div>
        <div class="sheet-grid">
          <el-form-item label="期内事件">
            <el-select v-model="sheetEditRow.sheet.extEventType" size="small" filterable clearable placeholder="未填" @change="reconcileSheetEvents">
              <el-option v-for="opt in extOpts" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="事件时间">
            <el-date-picker v-model="sheetEditRow.sheet.extEventDate" type="date" size="small" format="YYYY-MM-DD" value-format="YYYY-MM-DD" placeholder="选择日期" :disabled-date="disableExtDate" />
          </el-form-item>
          <el-form-item label="补地与承包地处置" class="sheet-span-2">
            <div class="sheet-checks">
              <el-checkbox v-model="sheetEditRow.sheet.extCompensated">已补地</el-checkbox>
              <el-checkbox v-model="sheetEditRow.sheet.extWithdraw">被抽回或放弃承包地</el-checkbox>
            </div>
          </el-form-item>
        </div>

        <div class="sheet-section">四、成员属性</div>
        <div class="sheet-grid">
          <el-form-item label="是否为本集体经济组织成员">
            <el-select v-model="sheetEditRow.sheet.economicRelation" size="small">
              <el-option label="是" value="1" />
              <el-option label="否" value="0" />
              <el-option label="未填" value="" />
            </el-select>
          </el-form-item>
          <el-form-item label="现户口所在地">
            <el-input v-model="sheetEditRow.sheet.hukouPlace" size="small" maxlength="200" placeholder="如：泗阳县××镇××村" />
          </el-form-item>
          <el-form-item label="现居住地" class="sheet-span-2">
            <el-input v-model="sheetEditRow.sheet.residencePlace" size="small" maxlength="200" placeholder="如：泗阳县××镇××村××组" />
          </el-form-item>
        </div>

        <div class="sheet-section">五、身份标识</div>
        <div class="sheet-grid">
          <el-form-item label="财政供养人员（国企正式编制、部队军官等）">
            <el-select v-model="sheetEditRow.sheet.isInstitutionStaff" size="small">
              <el-option v-for="opt in YES_NO_UNSET_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="其中：为国家公务员">
            <el-select v-model="sheetEditRow.sheet.isCivilServant" size="small" @change="handleCivilServantChange">
              <el-option v-for="opt in YES_NO_UNSET_OPTIONS" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="备注（公职单位、补地 / 抽回原因等）" class="sheet-span-2">
            <el-input v-model="sheetEditRow.sheet.remark" type="textarea" :rows="2" maxlength="500" show-word-limit />
          </el-form-item>
        </div>
        <div class="sheet-hint">
          打印表中的「成员增减变动时间」由两期「事件时间」自动取最后者，无需填写。事件留空也可以保存。
        </div>
      </el-form>
      <template #footer>
        <el-button @click="sheetDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <ChangeDiffViewer ref="diffViewer" />
    <div
      v-if="diffTooltip.visible"
      class="floating-diff-tooltip"
      :style="{ left: `${diffTooltip.x}px`, top: `${diffTooltip.y}px` }"
    >
      {{ diffTooltip.text }}
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import ChangeDiffViewer from "./ChangeDiffViewer.vue";
import { useDictionary } from "../../composables/useDictionary";
import { evaluateIdNoIssue, ID_NO_MAX_LENGTH } from "../../utils/validators";
import { MEMBER_EVENT_MAP, YES_NO_UNSET_OPTIONS, createEmptyMemberSheet, srEventOptions, extEventOptions } from "../../config/surveySheets";

const props = defineProps({
  readonly: { type: Boolean, default: false },
  batchId: { type: Number, required: true },
  contractorUid: { type: String, required: true },
  result: { type: Object, required: true },
  changedFields: { type: Array, default: () => [] },
  canGenerateCode: { type: Boolean, default: false },
});

const emit = defineEmits(["update:result", "generate-code"]);

const { options: relationOptions } = useDictionary("nyt2539_c20_relation_to_head");

const diffViewer = ref(null);
const diffTooltip = ref({
  visible: false,
  text: "",
  x: 0,
  y: 0,
});
const isAddedContractor = computed(() => props.result.resultStatus === "added");
// 是否展示「变化原因 / 政策依据」。口径与后端 _validate_confirmable 的触发条件一致：
// 只要有变化（is_changed）或 change_type 不是 none，确认时就要求这两项非空。
// 新建承包方（changeType=add_contractor）同样命中，故一并展示。
const showChangeFields = computed(
  () => Boolean(props.result.isChanged) || (props.result.changeType || "none") !== "none",
);
const typeLabelMap = { "1": "农户", "2": "个人", "3": "单位" };
const idTypeLabelMap = { "1": "居民身份证", "2": "户口簿", "3": "军官证" };
const genderLabelMap = { "1": "男", "2": "女" };
const yesNoLabelMap = { "1": "是", "0": "否" };
const dateFields = new Set(["surveyDate", "publicNoticeReviewDate"]);

function normalizeInput(value) {
  return String(value || "").trim();
}

function normalizeDigits(value) {
  return String(value || "").replace(/\D/g, "");
}

function handleCodeInput(value) {
  props.result.code = normalizeDigits(value).slice(0, 18);
}

function tooltipPosition(event) {
  const margin = 12;
  const tooltipWidth = Math.min(360, window.innerWidth - margin * 2);
  return {
    x: Math.max(margin, Math.min(event.clientX + margin, window.innerWidth - tooltipWidth - margin)),
    y: Math.max(margin, Math.min(event.clientY + margin, window.innerHeight - 80)),
  };
}

function showDiffTooltip(enabled, text, event) {
  if (!enabled) return;
  const position = tooltipPosition(event);
  diffTooltip.value = {
    visible: true,
    text,
    ...position,
  };
}

function moveDiffTooltip(event) {
  if (!diffTooltip.value.visible) return;
  Object.assign(diffTooltip.value, tooltipPosition(event));
}

function hideDiffTooltip() {
  diffTooltip.value.visible = false;
}

// 记录初始快照用于判断修改
const initialSnapshots = ref(new Map());

watch(
  () => props.result?.familyMembers,
  (members) => {
    initialSnapshots.value = new Map();
    if (!members) return;
    for (const m of members) {
      // 为新加载的成员初始化 UI 标记字段
      if (m._deleted === undefined) m._deleted = false;
      if (m._isNew === undefined) m._isNew = false;
      // 成员摸底数据（家庭成员变化摸底表）：后端缺失/老数据补全空对象。
      // 「是否二轮家庭成员」的默认值由后端 attach_member_sheet_info 按
      // "无摸底行 → 历史导入成员=是 / 系统新增(added)=否" 注入（2026-10-11 口径），
      // 前端不按 null 兜底，避免覆盖用户显式选的"未填"；这里只防 sheet 对象整体缺失。
      if (!m.sheet || typeof m.sheet !== "object") {
        m.sheet = { ...createEmptyMemberSheet(), isSecondRoundMember: isAddedMemberRow(m) ? false : true };
      }
      if (m.memberUid) {
        initialSnapshots.value.set(m.memberUid, {
          name: normalizeInput(m.name),
          gender: normalizeInput(m.gender),
          idType: normalizeInput(m.idType),
          idNo: normalizeInput(m.idNo),
          relationToHead: normalizeInput(m.relationToHead),
          isCoOwner: normalizeInput(m.isCoOwner),
          note: normalizeInput(m.note),
        });
      }
    }
  },
  { immediate: true },
);

// 直接返回原始数组，避免展开拷贝导致 v-model 和回调失效
const visibleMembers = computed(() => props.result.familyMembers || []);
const currentMemberCount = computed(() => visibleMembers.value.filter((m) => !m._deleted).length);
// 成员「变化原因」是条件必填：只要有新增 / 待删除 / 已修改的成员，就必须给这些行填原因
// （口径同 backend/app/services/survey/base.py::_validate_confirmable 与
//   ContractorResultDialog.vue::collectConfirmBlockers）。
const hasMemberChangeRequired = computed(() =>
  visibleMembers.value.some((row) => isNewRow(row) || row._deleted || isModifiedRow(row)),
);
const baseMembersByUid = computed(() => {
  const pairs = (props.result.baseContractor?.familyMembers || []).map((member) => [member.memberUid, member]);
  return new Map(pairs);
});

function isNewRow(row) {
  return row._isNew || (!row.memberUid && row.memberResultStatus === "added");
}

// 「是否二轮家庭成员」默认值判据：与 isNewRow 不同——已保存的新增行（有 memberUid、
// 状态仍是 "added"）也算"系统新增"，不该回默认"是"（那是历史导入成员的口径）。
function isAddedMemberRow(row) {
  return row._isNew || row.memberResultStatus === "added";
}

function isModifiedRow(row) {
  if (row._deleted || isNewRow(row)) return false;
  const snap = getBaseMember(row);
  if (!snap) return row.isChanged;
  return ["name", "gender", "idType", "idNo", "relationToHead", "isCoOwner", "note"].some((field) =>
    isMemberFieldChanged(row, field),
  );
}

function addMember() {
  props.result.familyMembers.push({
    memberUid: "",
    name: "",
    gender: "1",
    idType: "1",
    idNo: "",
    relationToHead: "09",
    noteCode: "",
    isCoOwner: "0",
    note: "",
    memberResultStatus: "added",
    surveyStatus: "surveyed",
    isHouseholdHead: false,
    isUrbanSettled: false,
    isMarriedOutWoman: false,
    isDeceased: false,
    isFiveGuarantees: false,
    changeReason: "新生",
    policyBasis: "",
    rightsDisposition: "",
    remark: "",
    // 新增成员：是否二轮家庭成员默认"否"（历史导入成员才默认"是"）
    sheet: { ...createEmptyMemberSheet(), isSecondRoundMember: false },
    _isNew: true,
  });
}

// ── 成员摸底信息弹窗（家庭成员变化摸底表填写入口） ──────────────────────
// 编辑直接绑定 row.sheet（结果对象的成员行），随「保存调查结果」一并提交，
// 无独立保存按钮 —— 数据落库由 update_result 的 upsert_member_sheets 完成。
const sheetDialogVisible = ref(false);
const sheetEditRow = ref(null);

// 两期事件下拉按「在户状态机」过滤：期初在户只能选减少类，期初不在户只能选增加类
// （列7 未填时不限制）。判据与 config/surveySheets.js、后端 sheet.py 同源。
// ⚠️ 兜底显示：已有值若与当前状态矛盾（历史数据），仍以中文文案
// 「（与状态矛盾）」后缀进选项 —— 否则 el-select 会露出原始码值（如 add_move_in）。
function withCurrentValue(value, options) {
  if (value && !options.some((opt) => opt.value === value)) {
    return [...options, { value, label: `${MEMBER_EVENT_MAP[value] || value}（与在户状态矛盾）` }];
  }
  return options;
}
const srOpts = computed(() => withCurrentValue(sheetEditRow.value?.sheet?.srEventType || "", srEventOptions(sheetEditRow.value?.sheet)));
const extOpts = computed(() => withCurrentValue(sheetEditRow.value?.sheet?.extEventType || "", extEventOptions(sheetEditRow.value?.sheet)));

// 事件时间边界（2026-10-15 用户口径）：二轮期 ≤ 2018-12-31，延包期 ≥ 2019-01-01
// （判据常量与 config/surveySheets.js、后端 sheet.py 同源；历史越界值由保存闸门点名）
function disableSrDate(d) {
  return d.getTime() > new Date(2018, 11, 31).getTime();
}
function disableExtDate(d) {
  return d.getTime() < new Date(2019, 0, 1).getTime();
}

// 列7 / 二轮期事件变化后，若另一期已选事件与新状态矛盾，自动清空并提示
function reconcileSheetEvents() {
  const s = sheetEditRow.value?.sheet;
  if (!s) return;
  if (s.srEventType && !srOpts.value.some((opt) => opt.value === s.srEventType)) {
    ElMessage.warning("二轮期事件与「1996 年是否家庭成员」矛盾，已清空（必须有进才有出）");
    s.srEventType = "";
    s.srEventDate = null;
  }
  if (s.extEventType && !extOpts.value.some((opt) => opt.value === s.extEventType)) {
    ElMessage.warning("延包期事件与前期在户状态矛盾，已清空（出了还可以再进，反之须先出）");
    s.extEventType = "";
    s.extEventDate = null;
  }
}

function openSheetDialog(row) {
  if (!row) return;
  if (!row.sheet || typeof row.sheet !== "object") {
    row.sheet = {
      ...createEmptyMemberSheet(),
      isSecondRoundMember: isAddedMemberRow(row) ? false : true,
    };
  }
  sheetEditRow.value = row;
  sheetDialogVisible.value = true;
}

// 列 34 ⊂ 列 33（纸质表口径）：选了"为国家公务员"，财政供养人口必然点亮
function handleCivilServantChange(value) {
  if (value === true && sheetEditRow.value?.sheet) {
    sheetEditRow.value.sheet.isInstitutionStaff = true;
  }
}

function setAsHead(row) {
  // 取消所有成员的户主标记
  for (const m of props.result.familyMembers) {
    m.isHouseholdHead = false;
  }
  // 设置目标为户主
  row.isHouseholdHead = true;
  // ⛔ 户主的关系码是字典里的 "02"（户主），不是 "01"（本人）。
  // 旧实现写 "01"，与存量户的 "02" 并存 ⇒ 一个户里出现两个"户主"（2026-09-25 修）。
  // 注：本函数同时用于「点选 设为户主」与「关系下拉选到户主类码」两条路径。
  row.relationToHead = "02";
  // 承包方名称默认随户主名称
  if (row.name) {
    props.result.name = row.name;
  }
}

function isHeadRelation(value) {
  if (value === "01") return true;
  const label = relationOptions.value.find((item) => item.value === value)?.label || "";
  return label.includes("本人") || label.includes("户主");
}

function handleRelationChange(row) {
  if (isHeadRelation(row.relationToHead)) {
    setAsHead(row);
    return;
  }
  if (row.isHouseholdHead) {
    row.isHouseholdHead = false;
  }
}

function toggleDelete(row) {
  if (!row._deleted && !getBaseMember(row)) {
    const index = props.result.familyMembers.indexOf(row);
    if (index >= 0) {
      props.result.familyMembers.splice(index, 1);
    }
    return;
  }
  row._deleted = !row._deleted;
  if (row._deleted) {
    row.memberResultStatus = "deleted";
    row.changeReason = row.changeReason || "去世";
  } else {
    row.memberResultStatus = isNewRow(row) ? "added" : "normal";
    if (!isNewRow(row)) row.changeReason = "";
  }
}

// 获取有效成员（排除被标记删除的）
function getValidMembers() {
  return (props.result.familyMembers || []).filter((m) => !m._deleted);
}

// 变化高亮
function displayValue(field, value) {
  if (value === undefined || value === null || value === "") {
    return "空";
  }
  if (dateFields.has(field)) {
    return formatDateValue(value);
  }
  if (field === "typeCode") return typeLabelMap[value] || value;
  if (field === "idType") return idTypeLabelMap[value] || value;
  if (field === "gender") return genderLabelMap[value] || value;
  if (field === "isCoOwner") return yesNoLabelMap[value] || value;
  if (field === "relationToHead") {
    return relationOptions.value.find((item) => item.value === value)?.label || value;
  }
  return String(value);
}

function formatDateValue(value) {
  if (!value) return "空";
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString().slice(0, 10);
  }
  return String(value).slice(0, 10);
}

function contractorCurrentValue(field) {
  return field === "memberCount" ? currentMemberCount.value : props.result[field];
}

function contractorBaseValue(field) {
  return props.result.baseContractor?.[field];
}

function isContractorFieldChanged(field) {
  if (isAddedContractor.value || !props.result.baseContractor) {
    return false;
  }
  if (dateFields.has(field)) {
    return formatDateValue(contractorCurrentValue(field)) !== formatDateValue(contractorBaseValue(field));
  }
  return normalizeInput(contractorCurrentValue(field)) !== normalizeInput(contractorBaseValue(field));
}

function beforeValueText(field) {
  return `变更前：${displayValue(field, contractorBaseValue(field))}`;
}

function getBaseMember(row) {
  if (!row?.memberUid) return null;
  return baseMembersByUid.value.get(row.memberUid) || null;
}

function isMemberFieldChanged(row, field) {
  if (row._deleted || isNewRow(row)) {
    return false;
  }
  const base = getBaseMember(row);
  if (!base) {
    return false;
  }
  return normalizeInput(row[field]) !== normalizeInput(base[field]);
}

function memberChangedClass(row, field) {
  return isMemberFieldChanged(row, field) ? "cell-field-changed" : "";
}

function memberBeforeValueText(row, field) {
  return `变更前：${displayValue(field, getBaseMember(row)?.[field])}`;
}

function changedClass(field) {
  return isContractorFieldChanged(field) ? "field-changed" : "";
}

// ---- 证件号码校验 ----
// 判定口径（含"本次新录入的值从严、库内历史值降级为提示"的分档）在
// utils/validators.js 的 evaluateIdNoIssue 里；这里只负责挑出"是否属于本次
// 录入或改动"并驱动界面提示。
function idNoFieldClass(issue) {
  if (!issue) return "";
  return issue.level === "error" ? "is-invalid" : "is-warn";
}

// 是否属于"本次录入或改动过"的证件号码：新增承包方、新增成员、或值发生过变化。
function isContractorIdNoChanged() {
  return isAddedContractor.value || isContractorFieldChanged("idNo");
}

function isMemberIdNoChanged(row) {
  return isNewRow(row) || isMemberFieldChanged(row, "idNo");
}

const contractorIdNoIssue = computed(() =>
  evaluateIdNoIssue(props.result.idType, props.result.idNo, { changed: isContractorIdNoChanged(), incompleteOk: true }),
);

function memberIdNoIssue(row) {
  if (row?._deleted) return null;
  return evaluateIdNoIssue(row?.idType, row?.idNo, { changed: isMemberIdNoChanged(row), incompleteOk: true });
}

/**
 * 保存前的证件号码全量校验（严格口径：必填 + 完整格式/校验位）。
 * @returns {string} 空串表示全部通过，否则为逐条问题描述（换行分隔）。
 */
function validateIdNos() {
  const problems = [];
  const contractorIssue = evaluateIdNoIssue(props.result.idType, props.result.idNo, {
    requireValue: true,
    changed: isContractorIdNoChanged(),
  });
  if (contractorIssue?.level === "error") {
    problems.push(`承包方证件号码：${contractorIssue.message}`);
  }
  for (const row of props.result.familyMembers || []) {
    if (row?._deleted) continue;
    const label = String(row?.name ?? "").trim() || "未命名成员";
    const issue = evaluateIdNoIssue(row?.idType, row?.idNo, {
      requireValue: true,
      changed: isMemberIdNoChanged(row),
    });
    if (issue?.level === "error") {
      problems.push(`家庭成员“${label}”的证件号码：${issue.message}`);
    }
  }
  return problems.join("\n");
}

defineExpose({ getValidMembers, validateIdNos });
</script>

<style scoped>
.contractor-member-panel { min-height: 200px; }
.change-alert { margin-bottom: 12px; }

/* 必填标记：与 el-form-item 的 required 星号同色（Element Plus 默认 #f56c6c）。
   el-table-column 没有 required 属性，列头只能靠 #header 插槽自渲染。 */
.req-star {
  color: #f56c6c;
  margin-right: 2px;
  font-weight: 700;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}
.section-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.section-heading .section-title {
  margin-bottom: 0;
}
.new-tag {
  flex: 0 0 auto;
}
.section-subtitle {
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin: 4px 0 8px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.contractor-form {
  margin-bottom: 0;
  max-width: 1480px;
}
.contractor-form :deep(.el-form-item) {
  min-width: 0;
  margin-bottom: 10px;
  align-items: center;
}
.contractor-form :deep(.el-form-item__label) {
  height: 34px;
  line-height: 34px;
  justify-content: flex-start;
  padding-right: 10px;
  color: #606266;
}
.contractor-form :deep(.el-form-item__content) {
  min-width: 0;
  width: 100%;
  display: flex;
  flex: 1 1 auto;
}
.diff-trigger {
  display: block;
  width: 100%;
  min-width: 0;
}
.contractor-form :deep(.el-input),
.contractor-form :deep(.el-select),
.contractor-form :deep(.el-date-editor),
.contractor-form :deep(.el-textarea),
.member-table :deep(.el-input),
.member-table :deep(.el-select) {
  width: 100% !important;
}
.contractor-form :deep(.el-input__wrapper),
.contractor-form :deep(.el-select__wrapper),
.member-table :deep(.el-input__wrapper),
.member-table :deep(.el-select__wrapper) {
  width: 100%;
  box-sizing: border-box;
}
.form-grid-3 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 18px;
  align-items: start;
}
.form-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
  align-items: start;
}
.form-span-2 {
  grid-column: span 2;
}
.form-span-3 {
  grid-column: 1 / -1;
}

.member-table { margin-top: 0; }

/* 成员摸底信息弹窗（2026-10-15 重构：顶部标签 + 两列网格，杜绝标签溢出换行） */
.sheet-section {
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin: 12px 0 6px;
  padding: 2px 0 2px 8px;
  border-left: 3px solid #409eff;
  line-height: 1.4;
}
.sheet-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
.sheet-form :deep(.el-form-item__label) {
  padding-bottom: 2px;
  line-height: 1.4;
  font-size: 12.5px;
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sheet-form :deep(.el-select),
.sheet-form :deep(.el-date-editor.el-input),
.sheet-form :deep(.el-date-editor.el-date-editor--date),
.sheet-form :deep(.el-input) {
  width: 100%;
}
.sheet-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
  align-items: start;
}
.sheet-span-2 {
  grid-column: 1 / -1;
}
.sheet-hint {
  grid-column: 1 / -1;
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.7;
  color: #909399;
}
.sheet-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 28px;
  padding: 4px 0 2px;
}
.sheet-checks :deep(.el-checkbox) {
  margin-right: 0;
  height: 24px;
}

.field-changed :deep(.el-input__wrapper),
.field-changed :deep(.el-select__wrapper),
.field-changed :deep(.el-textarea__inner),
.cell-field-changed :deep(.el-input__wrapper),
.cell-field-changed :deep(.el-select__wrapper) {
  background-color: #fdf6ec;
  box-shadow: 0 0 0 1px #e6a23c inset;
}
.field-changed {
  position: relative;
}

/* 证件号码校验：error 红框拦住保存，warn 橙框只提示（库内历史值校验位有误时的降级）。 */
.idno-field {
  width: 100%;
  min-width: 0;
}
.idno-field.is-invalid :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #f56c6c inset;
}
.idno-field.is-warn :deep(.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}
.idno-field__tip {
  margin-top: 2px;
  color: #f56c6c;
  font-size: 12px;
  line-height: 1.3;
}
.idno-field.is-warn .idno-field__tip {
  color: #e6a23c;
}
.floating-diff-tooltip {
  position: fixed;
  z-index: 3000;
  pointer-events: none;
  max-width: min(360px, calc(100vw - 24px));
  padding: 6px 8px;
  color: #fff;
  font-size: 12px;
  line-height: 1.4;
  white-space: normal;
  background: #303133;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.16);
}
@media (max-width: 1180px) {
  .form-grid-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 860px) {
  .form-grid-3,
  .form-grid-2 {
    grid-template-columns: 1fr;
  }
}
</style>
