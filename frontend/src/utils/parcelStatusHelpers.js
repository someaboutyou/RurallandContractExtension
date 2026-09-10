/**
 * Pure utility helpers for parcel status display, classification and formatting.
 * Extracted from ParcelInfoPanel.vue to reduce component size.
 */

export const dklbMap = { "01": "耕地", "02": "园地", "03": "林地", "04": "草地", "05": "养殖水面", "09": "其他" };

export const tdlylxMap = {
  "011": "水田", "012": "水浇地", "013": "旱地",
  "021": "果园", "022": "茶园", "023": "其他园地",
  "031": "有林地", "032": "灌木林地", "033": "其他林地",
  "041": "天然牧草地", "042": "人工牧草地",
  "111": "设施农用地", "114": "坑塘水面",
};

export function formatArea(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)} 亩`;
}

export function isRemovedParcel(parcel) {
  return parcel?.resultStatus === "removed";
}

export function isHistoricalParcel(parcel) {
  return ["removed", "split_source"].includes(parcel?.resultStatus);
}

export function isCurrentParcel(parcel) {
  return !isHistoricalParcel(parcel);
}

export function isSwappedOutParcel(parcel) {
  return isRemovedParcel(parcel) && parcel?.changeType === "swap_parcels";
}

export function isSwappedInParcel(parcel) {
  return !isRemovedParcel(parcel) && parcel?.changeType === "swap_parcels";
}

export function isSplitSourceParcel(parcel) {
  return parcel?.resultStatus === "split_source";
}

export function isSplitGeneratedParcel(parcel) {
  return isCurrentParcel(parcel) && parcel?.resultStatus === "split_generated";
}

export function isAddedParcel(parcel) {
  return (
    isCurrentParcel(parcel) &&
    (
      parcel?.resultStatus === "added" ||
      parcel?.changeType === "add_parcel"
    )
  );
}

export function parcelStatusLabel(parcel) {
  if (isSplitSourceParcel(parcel)) return "被切割";
  if (isSplitGeneratedParcel(parcel)) return "切割生成";
  if (isSwappedOutParcel(parcel)) return "已换出";
  if (isSwappedInParcel(parcel)) return "已换入";
  if (isAddedParcel(parcel)) return "新增";
  if (isRemovedParcel(parcel)) return "已移除";
  if (parcel?.isChanged) return "变更";
  return "正常";
}

export function parcelStatusType(parcel) {
  if (isSplitSourceParcel(parcel)) return "warning";
  if (isSplitGeneratedParcel(parcel)) return "success";
  if (isSwappedOutParcel(parcel)) return "info";
  if (isSwappedInParcel(parcel)) return "warning";
  if (isAddedParcel(parcel)) return "success";
  if (isRemovedParcel(parcel)) return "danger";
  if (parcel?.isChanged) return "warning";
  return "success";
}

export function parcelRowClassName({ row }) {
  return isHistoricalParcel(row) ? "parcel-row-removed" : "";
}

export function parcelChangedClass(row) {
  return row.isChanged ? "field-changed" : "";
}
