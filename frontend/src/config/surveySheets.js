/**
 * 家庭成员变化摸底表的选项常量（2026-10-10 简化后仅成员摸底在用）。
 *
 * 《承包地变化摸底表》已改为纯现有数据推导（无录入界面、无独立存储），
 * 原 LAND_CHANGE_REASONS / FAMILY_CONTRACT_MODES 已随录入界面一并移除。
 *
 * ⛔ 与后端 `app/services/survey/sheet.py` 的常量同源（码值一致），改一处要改两处。
 */

/**
 * 表2 增减事件类型 —— 与纸质摸底表的 10 个事件列一一对应
 * （8新生/9婚入/10迁入/11其他 ｜ 12已补地人口 ｜ 13去世/14婚出/15迁出/16其他 ｜ 17抽回或放弃承包地；
 *   18~27 延包期同构）。
 * ⛔ 与后端 `app/services/survey/sheet.py::MEMBER_EVENT_TYPES` 同源（码值一致）；
 *   库里旧码（add_restore/sub_compensated）由后端 LEGACY_EVENT_MAP 兜底归一。
 */
export const MEMBER_EVENT_TYPES = [
  { value: "add_birth", label: "新生" },
  { value: "add_married_in", label: "婚入" },
  { value: "add_move_in", label: "迁入" },
  { value: "add_other", label: "其他增加" },
  { value: "compensated", label: "已补地人口" },
  { value: "sub_death", label: "去世" },
  { value: "sub_married_out", label: "婚出" },
  { value: "sub_move_out", label: "迁出" },
  { value: "sub_other", label: "其他减少" },
  { value: "withdraw", label: "抽回或放弃承包地" },
];

export const MEMBER_EVENT_MAP = Object.fromEntries(
  MEMBER_EVENT_TYPES.map((item) => [item.value, item.label])
);

/** 三态（是 / 否 / 未填）下拉的通用选项（摸底弹窗各勾选项共用） */
export const YES_NO_UNSET_OPTIONS = [
  { label: "是", value: true },
  { label: "否", value: false },
  { label: "未填", value: null },
];

/**
 * 成员行 sheet 子对象的空值形态（与后端 sheet.EMPTY_MEMBER_SHEET 同构）。
 * 三态布尔用 true/false/null 承载（null = 未填）。
 */
export function createEmptyMemberSheet() {
  return {
    isSecondRoundMember: null,
    srEventType: "",
    srEventDate: null,
    srNewPopulation: null,
    extEventType: "",
    extEventDate: null,
    extNewPopulation: null,
    restructureTime: null,
    hasChange: null,
    economicRelation: "",
    hukouPlace: "",
    residencePlace: "",
    isCivilServant: null,
    isInstitutionStaff: null,
    hasEstablishment: null,
    isActiveMilitary: null,
    hasBusinessLicense: null,
    isPublicServant: null,
    remark: "",
  };
}
