/**
 * 「我的待调查」列表页的跨页脏标记。
 *
 * ## 为什么需要
 *
 * 列表页（MobileTaskListView）被 keep-alive 缓存后，从详情/作业页返回**不再重新挂载**，
 * 也就不会重复拉批次 + 任务列表 —— 这是本机制的初衷（减少请求次数）。
 *
 * 但缓存带来一个反面：如果用户在子页面对这户做了会改变列表展示的操作
 * （改调查状态、确认/跳过、合户/分户/注销等），返回后列表还是旧状态。
 *
 * 约定：**子页面凡是「改了会影响列表行的数据」且保存成功后，调 `markTaskListDirty()`**；
 * 列表页 onActivated 时只在标记为脏时才 reload。普通浏览（只读详情、拍照上传附件）
 * 不打标记 ⇒ 返回零请求。
 *
 * （附件上传/删除目前不影响列表行展示，刻意不打标记；以后若列表要显示附件数，
 * 再在 MobileAttachmentView 的成功回调里补 markTaskListDirty() 即可。）
 */

let dirty = false;

/** 子页面保存成功后调用：下一次列表页激活时强制刷新一次 */
export function markTaskListDirty() {
  dirty = true;
}

/** 列表页激活时调用：返回「是否需要刷新」并清除标记（一次性消费） */
export function consumeTaskListDirty() {
  const wasDirty = dirty;
  dirty = false;
  return wasDirty;
}
