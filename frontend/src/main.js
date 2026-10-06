import { createApp } from "vue";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

import { Capacitor } from "@capacitor/core";

import App from "./App.vue";
import router from "./router";
import pinia from "./stores";
import "./styles.css";

createApp(App).use(pinia).use(router).use(ElementPlus).mount("#app");

/**
 * Web 资源热更（仅 Android 原生壳，见 src/mobile/updater.js）。
 *
 * bootSync 必须在 App 逻辑之前跑：当前加载的如果是「指针指向的版本」，
 * 要立刻安装崩溃回滚看门狗；若原生冷启动切换失败，这里兜底再切一次。
 * 任何异常都不能阻塞正常启动。
 */
if (Capacitor.isNativePlatform()) {
  import("./mobile/updater.js")
    .then((updater) => updater.bootSync())
    .catch((error) => console.warn("[hot-update] bootSync 失败", error));

  // 路由就绪（首屏组件挂载）后标记启动成功 + 节流检查更新
  router.isReady().then(() => {
    setTimeout(() => {
      import("./mobile/updater.js")
        .then((updater) => {
          updater.markBootOk();
          void updater.checkForUpdates();
        })
        .catch(() => {});
    }, 2000);
  });
}

/**
 * Android 返回手势 / 返回键（边缘左滑、右滑、三键导航的返回）。
 *
 * 没有这段时，Capacitor 壳对返回手势没有任何处理 —— 系统默认行为是 finish()
 * Activity，所以在任何页面边缘一滑，整个 App 直接退出。
 *
 * 装上 @capacitor/app 后，插件会用 OnBackPressedDispatcher 接管返回事件；
 * 这里注册 backButton 监听后走 JS 分支（AppPlugin.hasListeners）：
 * - 在根页面（登录页 / 待调查 / PC 的 gis）→ 退出 App（与一般 Android 软件一致）；
 * - 非根页面且 WebView 有历史 → 返回上一页；
 * - 兜底：无历史也退出。
 *
 * ⛔ 判据必须是「当前路由是否根页面」，不能只看 canGoBack：
 *   退出登录后历史栈是 [待调查 → 登录页]，canGoBack=true，走 history.back() 会
 *   回到待调查 → 守卫发现未登录又弹回登录页 ⇒ 「能回退但回退无效」，永远到不了
 *   exitApp 分支，右滑多少次都退不出 App（2026-10-04 用户实测）。
 *   登录后在待调查页同理：back 回登录页会被 `mobile-login && isAuthenticated`
 *   重定向回待调查，等于原地踏步。
 *
 * ⛔ 仅原生壳注册：浏览器里没有系统返回键，且动态 import 保证 @capacitor/app
 * 不会被打进 PC 端 bundle。
 */
if (Capacitor.isNativePlatform()) {
  import("@capacitor/app").then(({ App }) => {
    // 根页面 = 返回手势应当退出 App 的页面：移动端登录页 / 待调查列表，
    // PC 端登录页与首屏 gis（AppLayout 的 redirect 落点）。
    const ROOT_ROUTE_NAMES = new Set(["mobile-login", "mobile-tasks", "login", "gis"]);

    App.addListener("backButton", ({ canGoBack }) => {
      const currentName = router.currentRoute.value.name;
      if (ROOT_ROUTE_NAMES.has(currentName) || !canGoBack) {
        App.exitApp();
        return;
      }
      window.history.back();
    });
  });
}
