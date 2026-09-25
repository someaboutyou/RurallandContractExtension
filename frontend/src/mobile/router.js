/**
 * 移动端路由表，由 `src/router/index.js` 合并进主路由。
 *
 * 约定：移动端一律挂在 `/m/*` 下，与 PC 端 `/`（AppLayout 下的 17 个页面）并存互不干扰。
 * 布局与权限守卫复用主路由那一套（`meta.requiresAuth` + `meta.permissions`，
 * 守卫逻辑在 `src/router/index.js`，这里只声明元信息）。
 *
 * 页面级 meta：
 * - `mobileTitle`  顶部标题栏文字
 * - `mobileTabbar` 是否显示底部导航（二级页设 false）
 * - `mobileBack`   是否显示返回箭头（一级页设 false）
 */

// ⚠️ 必须是「动态引入」：MobileLayout.vue 里 `import "vant/lib/index.css"`，
// 若这里静态引入，整个 vant 全量样式会被打进主 CSS chunk，PC 端路由也会被动加载。
// 改成 `() => import(...)` 后 vant 只在访问 /m/* 时按需加载（别改回静态写法）。
const MobileLayout = () => import("./layout/MobileLayout.vue");

const MobileLoginView = () => import("./views/MobileLoginView.vue");
const MobileTaskListView = () => import("./views/MobileTaskListView.vue");
const MobileTaskDetailView = () => import("./views/MobileTaskDetailView.vue");
const MobileParcelView = () => import("./views/MobileParcelView.vue");
const MobileAttachmentView = () => import("./views/MobileAttachmentView.vue");
const MobileProfileView = () => import("./views/MobileProfileView.vue");

export const mobileRoutes = [
  {
    path: "/m/login",
    name: "mobile-login",
    component: MobileLoginView,
    meta: { requiresAuth: false, mobileTitle: "登录", mobileTabbar: false, mobileBack: false },
  },
  {
    path: "/m",
    component: MobileLayout,
    redirect: { name: "mobile-tasks" },
    meta: { requiresAuth: true },
    children: [
      {
        path: "tasks",
        name: "mobile-tasks",
        component: MobileTaskListView,
        meta: {
          requiresAuth: true,
          permissions: ["contractors.view"],
          mobileTitle: "我的待调查",
          mobileBack: false,
        },
      },
      {
        path: "tasks/:batchId/:contractorUid",
        name: "mobile-task-detail",
        component: MobileTaskDetailView,
        meta: {
          requiresAuth: true,
          permissions: ["contractors.view"],
          mobileTitle: "调查录入",
          mobileTabbar: false,
        },
      },
      {
        path: "tasks/:batchId/:contractorUid/parcels",
        name: "mobile-task-parcels",
        component: MobileParcelView,
        meta: {
          requiresAuth: true,
          permissions: ["contractors.view"],
          mobileTitle: "地块与勾绘",
          mobileTabbar: false,
        },
      },
      {
        path: "tasks/:batchId/:contractorUid/attachments",
        name: "mobile-task-attachments",
        component: MobileAttachmentView,
        meta: {
          requiresAuth: true,
          permissions: ["contractors.view"],
          mobileTitle: "拍照附件",
          mobileTabbar: false,
        },
      },
      {
        path: "profile",
        name: "mobile-profile",
        component: MobileProfileView,
        meta: { requiresAuth: true, mobileTitle: "我的", mobileBack: false },
      },
    ],
  },
];
