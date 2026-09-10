export const surveyStatusMap = {
  not_surveyed: "未调查", not_started: "未调查", surveyed: "已调查",
  changed: "有变化", unchanged: "无变化", confirmed: "已确认", skipped: "已跳过",
};

export const resultStatusMap = {
  normal: "正常", added: "新增", removed: "已移除", extinct: "整户消亡",
  cancelled: "已注销", deregistered: "已注销", merged: "已合并",
  deceased: "死亡", urbanized: "转为城镇居民", little_or_no_land: "少地或无地",
};

export const changeTypeMap = {
  none: "无变化", info_change: "信息变更", change_head: "户主变更",
  member_maintain: "成员维护", deregister: "注销承包方", add_parcel: "新增地块",
  split_parcel: "地块分割", swap_parcels: "地块互换", remove_parcel: "移除地块",
  split_household: "分户", merge_household: "并户", household_extinct: "整户消亡户",
  household_urbanized: "整户转为城镇居民", little_or_no_land: "少地或无地户",
};

export const landUseTypeMap = {
  "011": "水田", "012": "水浇地", "013": "旱地", "021": "果园",
  "022": "茶园", "023": "其他园地", "031": "有林地", "032": "灌木林地",
  "033": "其他林地", "041": "天然牧草地", "042": "人工牧草地",
  "111": "设施农用地", "114": "坑塘水面",
};
