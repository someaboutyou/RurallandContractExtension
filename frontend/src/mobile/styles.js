/**
 * 移动端共享样式入口。
 *
 * ## 为什么要有这个文件
 *
 * vant 的样式必须在**每个移动端入口**都能拿到，但入口不止一个：
 * - `/m/*`（除登录页外）→ 走 `MobileLayout.vue`
 * - `/m/login` → **独立路由，不在 MobileLayout 下**
 *
 * 所以样式不能只挂在 MobileLayout 里，否则登录页是"裸奔"的（能点但没样式）。
 *
 * ## 为什么用动态 import
 *
 * `import("vant/lib/index.css")`（而不是顶层静态 `import`）是刻意的：
 * 静态引入时，若宿主文件被 Rollup 内联进入口 chunk，vant 的全量样式（约 199KB）
 * 会被并入入口 CSS，**导致每个 PC 页面都白下载一份移动端样式**（2026-09-22 实测过：
 * 入口 CSS 一度从 61.7KB 涨到 260.9KB）。
 * 动态引入则始终生成独立的按需 CSS chunk，无论宿主 chunk 怎么合并都不会污染入口。
 *
 * 触发即加载、不 await ⇒ 首屏会有极短的无样式窗口，与上一版行为一致。
 */
import("vant/lib/index.css");
