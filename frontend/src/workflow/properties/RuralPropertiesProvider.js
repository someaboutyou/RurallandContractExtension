import { TextFieldEntry, CheckboxEntry, SelectEntry, isTextFieldEntryEdited, isCheckboxEntryEdited, isSelectEntryEdited } from "@bpmn-io/properties-panel";
import { useService } from "bpmn-js-properties-panel";
import { getBusinessObject, is } from "bpmn-js/lib/util/ModelUtil";

const DATA_SCOPE_OPTIONS = [
  { value: "", label: "沿用账号数据范围" },
  { value: "all", label: "全部数据" },
  { value: "county", label: "县级范围" },
  { value: "town", label: "镇级范围" },
  { value: "village", label: "村级范围" },
  { value: "self", label: "仅本人相关" }
];

const CANDIDATE_MODE_OPTIONS = [
  { value: "", label: "按权限与数据范围自动匹配" },
  { value: "permission_scope", label: "按权限编码匹配" },
  { value: "role_scope", label: "按候选角色匹配" },
  { value: "manual_assign", label: "人工指定办理人" }
];

function getAttr(element, key, fallback = "") {
  return getBusinessObject(element).get(key) ?? fallback;
}

function setAttr(modeling, element, key, value) {
  modeling.updateProperties(element, {
    [key]: value === "" || value === null ? undefined : value
  });
}

function PermissionCodeEntry(props) {
  const { element } = props;
  const debounce = useService("debounceInput");
  const modeling = useService("modeling");

  return TextFieldEntry({
    element,
    id: "rural-permission-code",
    label: "权限编码",
    description: "示例：workflow.review.village",
    debounce,
    getValue: () => getAttr(element, "rural:permissionCode"),
    setValue: (value) => setAttr(modeling, element, "rural:permissionCode", value?.trim() || "")
  });
}

function DataScopeEntry(props) {
  const { element } = props;
  const modeling = useService("modeling");

  return SelectEntry({
    element,
    id: "rural-data-scope",
    label: "节点数据范围",
    description: "为空时表示沿用账号自身的数据权限范围",
    getValue: () => getAttr(element, "rural:dataScope"),
    getOptions: () => DATA_SCOPE_OPTIONS,
    setValue: (value) => setAttr(modeling, element, "rural:dataScope", value)
  });
}

function RequireCommentEntry(props) {
  const { element } = props;
  const modeling = useService("modeling");

  return CheckboxEntry({
    element,
    id: "rural-require-comment",
    label: "必须填写审核意见",
    getValue: () => Boolean(getAttr(element, "rural:requireComment", false)),
    setValue: (value) => {
      modeling.updateProperties(element, {
        "rural:requireComment": value || undefined
      });
    }
  });
}

function CandidateRoleCodesEntry(props) {
  const { element } = props;
  const debounce = useService("debounceInput");
  const modeling = useService("modeling");

  return TextFieldEntry({
    element,
    id: "rural-candidate-role-codes",
    label: "候选角色编码",
    description: "多个角色请用英文逗号分隔，如 village_auditor,town_auditor",
    debounce,
    getValue: () => getAttr(element, "rural:candidateRoleCodes"),
    setValue: (value) => setAttr(modeling, element, "rural:candidateRoleCodes", value?.trim() || "")
  });
}

function RequireAttachmentEntry(props) {
  const { element } = props;
  const modeling = useService("modeling");

  return CheckboxEntry({
    element,
    id: "rural-require-attachment",
    label: "当前节点要求上传附件",
    getValue: () => Boolean(getAttr(element, "rural:requireAttachment", false)),
    setValue: (value) => {
      modeling.updateProperties(element, {
        "rural:requireAttachment": value || undefined
      });
    }
  });
}

function AttachmentTypesEntry(props) {
  const { element } = props;
  const debounce = useService("debounceInput");
  const modeling = useService("modeling");

  return TextFieldEntry({
    element,
    id: "rural-attachment-types",
    label: "附件分类编码",
    description: "多个分类请用英文逗号分隔，例如：application_form,id_card,contract_scan",
    debounce,
    getValue: () => getAttr(element, "rural:attachmentTypes"),
    setValue: (value) => setAttr(modeling, element, "rural:attachmentTypes", value?.trim() || "")
  });
}

function CandidateUserModeEntry(props) {
  const { element } = props;
  const modeling = useService("modeling");

  return SelectEntry({
    element,
    id: "rural-candidate-user-mode",
    label: "办理人选择方式",
    description: "决定当前节点候选办理人的产生规则",
    getValue: () => getAttr(element, "rural:candidateUserMode"),
    getOptions: () => CANDIDATE_MODE_OPTIONS,
    setValue: (value) => setAttr(modeling, element, "rural:candidateUserMode", value)
  });
}

function createRuralBusinessGroup(element) {
  return {
    id: "rural-business",
    label: "业务配置",
    entries: [
      {
        id: "rural-permission-code",
        element,
        component: PermissionCodeEntry,
        isEdited: isTextFieldEntryEdited
      },
      {
        id: "rural-data-scope",
        element,
        component: DataScopeEntry,
        isEdited: isSelectEntryEdited
      },
      {
        id: "rural-require-comment",
        element,
        component: RequireCommentEntry,
        isEdited: isCheckboxEntryEdited
      },
      {
        id: "rural-require-attachment",
        element,
        component: RequireAttachmentEntry,
        isEdited: isCheckboxEntryEdited
      },
      {
        id: "rural-attachment-types",
        element,
        component: AttachmentTypesEntry,
        isEdited: isTextFieldEntryEdited
      },
      {
        id: "rural-candidate-role-codes",
        element,
        component: CandidateRoleCodesEntry,
        isEdited: isTextFieldEntryEdited
      },
      {
        id: "rural-candidate-user-mode",
        element,
        component: CandidateUserModeEntry,
        isEdited: isSelectEntryEdited
      }
    ]
  };
}

export default function RuralPropertiesProvider(propertiesPanel) {
  propertiesPanel.registerProvider(500, this);

  this.getGroups = function getGroups(element) {
    return function appendRuralGroups(groups) {
      if (!is(element, "bpmn:UserTask")) {
        return groups;
      }

      return [...groups, createRuralBusinessGroup(element)];
    };
  };
}

RuralPropertiesProvider.$inject = ["propertiesPanel"];
