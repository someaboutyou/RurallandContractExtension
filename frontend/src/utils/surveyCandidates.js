import { fetchSurveyTasks } from "../api/survey";

// 后端 /surveys/batches/{id}/tasks 的 page_size 上限是 200（超出会 422）。
const PAGE_SIZE = 200;
const MAX_PAGES = 50;

/**
 * 承包方所属村组码：优先用后端返回的 groupRegionCode，兜底取业务编码前 14 位。
 */
export function taskGroupCode(task) {
  const raw = task?.groupRegionCode || task?.cbfbm || task?.code || "";
  return String(raw).slice(0, 14);
}

/**
 * 循环分页拉取全批次任务。
 *
 * 任务列表页固定 page=1&page_size=100，批次超过 100 户时后面的户取不到；
 * 凡是「需要全批次数据」的场景（候选池兜底、编码去重）都要走这里。
 */
export async function fetchAllBatchTasks(batchId, extraParams = {}) {
  const rows = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const { data } = await fetchSurveyTasks(batchId, { page, page_size: PAGE_SIZE, ...extraParams });
    const items = data?.data?.items || [];
    rows.push(...items);
    const total = data?.data?.total || 0;
    if (items.length < PAGE_SIZE || rows.length >= total) break;
  }
  return rows;
}

/**
 * 候选接口不可用时的兜底：拉全批次后按当前户的村组过滤，并保证当前户在场。
 */
export async function fallbackSameGroupTasks(batchId, currentUid, extraParams = {}) {
  const rows = await fetchAllBatchTasks(batchId, extraParams);
  const current = rows.find((task) => task.contractorUid === currentUid);
  const groupKey = current ? taskGroupCode(current) : "";
  const sameGroup = groupKey ? rows.filter((task) => taskGroupCode(task) === groupKey) : rows;
  if (current && !sameGroup.some((task) => task.contractorUid === currentUid)) {
    return [current, ...sameGroup];
  }
  return sameGroup;
}

/**
 * 已占用的承包方编码（纯数字）。传入 tasks 时先本地算一份，接口返回后覆盖。
 */
export function collectContractorCodes(rows) {
  return (rows || [])
    .map((item) => String(item?.cbfbm ?? item ?? "").replace(/\D/g, ""))
    .filter(Boolean);
}
