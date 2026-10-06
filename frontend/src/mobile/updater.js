/**
 * Web 资源热更（仅 Android 原生壳内生效）。
 *
 * ## 架构（与原生两侧的分工）
 *
 * - 原生侧（`MainActivity.load()` + `HotUpdatePlugin`）：
 *   - 冷启动时读 `filesDir/bundles/current.json`，若指向已下载的 bundle，
 *     直接 `bridge.setServerBasePath(path)` —— 单次启动即加载新版，无二次跳转；
 *   - `HotUpdate.apply({path})` 供 JS 在下载完成/回滚时切换加载目录并立即重载；
 *     `path` 为空 = 回到 APK 内置资源。
 * - JS 侧（本模块）：检查 → 下载 → sha256 校验 → 解压写盘 → 写指针。
 *   下一次冷启动由原生激活。
 *
 * ## 版本三元组
 *
 * - `__BUNDLE_VERSION__`：构建期注入（publish_web_update.py 经 VITE_BUNDLE_VERSION
 *   注入，保证与服务器清单一致）；
 * - 原生版本号：`App.getInfo().build`（即 android versionCode）；
 * - 清单里的 `min_native_version_code`：新 Web 依赖新原生插件时由发布者抬高，
 *   旧壳收到后**拒绝安装**该包（提示需升级客户端），防止「新 JS 配旧原生」。
 *
 * ## 回滚（热更安全的关键）
 *
 * - 每个版本启动时自增 `hu_boot_<v>` 计数；连续 >3 次启动 15 秒内没有写入
 *   `hu_bootok_<v>`（markBootOk，路由就绪后调用）⇒ 判定崩溃循环；
 * - 回滚 = 把指针写回 `prev`（上一个已验证 bundle），调 HotUpdate.apply 立即切回；
 * - prev 为空（内置资源）⇒ 清指针 + apply 空路径回内置。
 * - localStorage 的 origin 恒为 http://localhost，跨 bundle 共享，计数天然连续。
 *
 * ## 数据目录布局（Directory.Data = filesDir）
 *
 *   bundles/current.json        { version, path, prev? }   原生每冷启动读它
 *   bundles/<version>/...       完整 dist（含 index.html）
 *
 * ⛔ 所有网络/解压/写盘失败一律静默或提示，绝不阻塞 App 正常启动与使用。
 */
import { Capacitor, registerPlugin } from "@capacitor/core";

// __BUNDLE_VERSION__ 由 vite define 在构建期替换为字面量（见 vite.config.js）

const POINTER_PATH = "bundles/current.json";
// 冷启动每次都会发一次极小的 check 请求（几百字节），30 分钟节流只防「反复杀进程重开」；
// ⛔ 别改回小时级：节流太长会让旧包在「下次自动检查」前一直卡住，用户怎么重启都收不到更新。
const CHECK_THROTTLE_MS = 30 * 60 * 1000;
const BOOT_OK_TIMEOUT_MS = 15 * 1000; // 15 秒内没 markBootOk 视为启动失败
const MAX_BOOT_ATTEMPTS = 3;

const HotUpdate = registerPlugin("HotUpdate");

export function getBundleVersion() {
  return typeof __BUNDLE_VERSION__ === "string" ? __BUNDLE_VERSION__ : "dev";
}

function isNative() {
  return Capacitor.isNativePlatform();
}

/* ------------------------------------------------------------------ *
 * 指针读写（Directory.Data 下的 bundles/current.json）
 * ------------------------------------------------------------------ */

async function readFileText(path) {
  const { Filesystem, Directory, Encoding } = await import("@capacitor/filesystem");
  const result = await Filesystem.readFile({ path, directory: Directory.Data, encoding: Encoding.UTF8 });
  return typeof result.data === "string" ? result.data : "";
}

async function readPointer() {
  try {
    const pointer = JSON.parse(await readFileText(POINTER_PATH));
    return pointer && typeof pointer === "object" ? pointer : null;
  } catch {
    return null;
  }
}

async function writePointer(pointer) {
  const { Filesystem, Directory, Encoding } = await import("@capacitor/filesystem");
  await Filesystem.writeFile({
    path: POINTER_PATH,
    data: JSON.stringify(pointer),
    directory: Directory.Data,
    encoding: Encoding.UTF8,
    recursive: true,
  });
}

async function deletePointer() {
  const { Filesystem, Directory } = await import("@capacitor/filesystem");
  try {
    await Filesystem.deleteFile({ path: POINTER_PATH, directory: Directory.Data });
  } catch {
    /* 不存在即目标状态 */
  }
}

/** bundle 目录的绝对路径（原生 setServerBasePath 需要） */
async function bundleDirUri(version) {
  const { Filesystem, Directory } = await import("@capacitor/filesystem");
  const { uri } = await Filesystem.getUri({ path: `bundles/${version}`, directory: Directory.Data });
  return uri.replace(/^file:\/\//, "");
}

/* ------------------------------------------------------------------ *
 * 启动同步 + 崩溃循环回滚
 * ------------------------------------------------------------------ */

/**
 * main.js 最先调用。两种情况：
 * - 当前运行的就是指针指向的版本（原生冷启动已切换）→ 安装启动看门狗；
 * - 运行的还是旧版（原生切换失败等兜底）→ 通过 HotUpdate 插件再切一次。
 */
export async function bootSync() {
  if (!isNative()) return;
  const pointer = await readPointer();
  if (!pointer || !pointer.path) return;

  if (pointer.version === getBundleVersion()) {
    armBootWatchdog(pointer);
    return;
  }

  // 防切坏指针导致的无限 reload：一个页面会话里最多切 2 次
  const switches = Number(sessionStorage.getItem("hu_switches") || 0) + 1;
  sessionStorage.setItem("hu_switches", String(switches));
  if (switches > 2) {
    console.warn("[hot-update] 切换次数超限，放弃切换，按当前版本运行");
    return;
  }
  try {
    await HotUpdate.apply({ path: pointer.path });
    // apply 成功时原生已重载 WebView，后面不会执行
  } catch (error) {
    console.warn("[hot-update] 指针指向的 bundle 不可用，按内置版本运行", error);
  }
}

function armBootWatchdog(pointer) {
  const version = String(pointer.version);
  const bootKey = `hu_boot_${version}`;
  const okKey = `hu_bootok_${version}`;

  const attempts = Number(localStorage.getItem(bootKey) || "0") + 1;
  localStorage.setItem(bootKey, String(attempts));

  if (attempts > MAX_BOOT_ATTEMPTS) {
    console.warn(`[hot-update] v${version} 连续 ${attempts} 次启动失败，回滚`);
    void rollback(pointer, `v${version} 启动异常，已回退到上一个版本，请重试`);
    return;
  }

  setTimeout(() => {
    if (localStorage.getItem(okKey)) return;
    console.warn(`[hot-update] v${version} 启动 ${BOOT_OK_TIMEOUT_MS / 1000}s 未就绪，回滚`);
    void rollback(pointer, "新版本启动超时，已自动回退");
  }, BOOT_OK_TIMEOUT_MS);
}

/** 应用就绪后由 main.js 调用：给当前版本盖「启动成功」章 */
export function markBootOk() {
  if (!isNative()) return;
  const version = getBundleVersion();
  localStorage.setItem(`hu_bootok_${version}`, "1");
  localStorage.setItem(`hu_boot_${version}`, "0");
}

async function rollback(pointer, toastText) {
  const prev = pointer.prev && pointer.prev.path ? pointer.prev : null;
  try {
    if (prev) {
      await writePointer(prev);
      await HotUpdate.apply({ path: prev.path });
    } else {
      await deletePointer();
      await HotUpdate.apply({ path: "" }); // 空 path = 回到 APK 内置资源
    }
  } catch (error) {
    // apply 抛错只影响「本会话立即切回」；指针已回写，下次冷启动必然回到安全版本
    console.warn("[hot-update] 本会话回滚失败，已回写指针待冷启动生效", error);
  }
  void toastText;
  try {
    const { showToast } = await import("./ui.js");
    showToast(toastText);
  } catch {
    /* 忽略 */
  }
}

/* ------------------------------------------------------------------ *
 * 检查 + 下载 + 应用
 * ------------------------------------------------------------------ */

async function toast(text) {
  try {
    const { showToast } = await import("./ui.js");
    showToast(text);
  } catch {
    /* 忽略 */
  }
}

function resolveApiBaseSync() {
  // 动态 import 避免把 serverConfig 链路外的模块拖进入口 chunk；
  // 这里只取 resolveApiBase（纯同步函数）。
  // eslint-disable-next-line no-undef
  return import("../api/serverConfig.js").then((m) => m.resolveApiBase());
}

function base64FromBytes(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function sha256Hex(buffer) {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * 检查并应用更新（下载成功 = 已写好指针，下次冷启动生效）。
 *
 * @param {object} [options]
 * @param {boolean} [options.force=false] 「我的 → 检查更新」手动触发：跳过 6h 节流
 * @param {boolean} [options.activateNow=false] 下载完成后立即切到新包（手动检查时用，
 *   WebView 会重载一次；后台自动检查保持「下次冷启动生效」，不打断外业操作）
 * @returns {Promise<{status: string, activated?: boolean}>} status:
 *   not-native / throttled / up-to-date / unreachable / native-too-old / updated / error
 */
export async function checkForUpdates({ force = false, activateNow = false } = {}) {
  if (!isNative()) return { status: "not-native" };

  const lastKey = "hu_last_check";
  const now = Date.now();
  if (!force && now - Number(localStorage.getItem(lastKey) || "0") < CHECK_THROTTLE_MS) {
    return { status: "throttled" };
  }
  // ⛔ 节流时间戳**不在检查前写**：清存储后首次启动时后端地址还没配置、或服务器暂时
  // 不可达，检查必然失败 —— 若此时就盖章，会把手机锁在「节流期内不再检查」的死锁里
  // （旧包节流 6h，用户怎么清存储重登都没用，正是 2026-09-30 事故的根因）。
  // 只在拿到服务器有效响应后（无论是否有更新）才盖章。

  let apiBase;
  try {
    apiBase = await resolveApiBaseSync();
  } catch {
    return { status: "unreachable" };
  }

  // ---- 1. 检查 -------------------------------------------------------
  let bundle;
  try {
    const { App } = await import("@capacitor/app");
    const info = await App.getInfo();
    const query = new URLSearchParams({
      platform: "android",
      native_version_code: String(info.build),
      bundle_version: getBundleVersion(),
    });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10 * 1000);
    const resp = await fetch(`${apiBase}/app-updates/check?${query}`, { signal: controller.signal });
    clearTimeout(timer);
    if (!resp.ok) return { status: "unreachable" };
    const body = await resp.json();
    const payload = body && body.data ? body.data : body;
    // 服务器已应答：无论 action 是什么都算「检查成功」，此时才允许盖节流章
    localStorage.setItem(lastKey, String(now));
    if (!payload || payload.action !== "web" || !payload.bundle) {
      return { status: "up-to-date" };
    }
    bundle = payload.bundle;
  } catch {
    return { status: "unreachable" }; // 网络不通/后端没发布：静默，不盖节流章
  }

  // ---- 2. 原生能力门槛 -------------------------------------------------
  let nativeBuild = 0;
  try {
    const { App } = await import("@capacitor/app");
    nativeBuild = Number((await App.getInfo()).build) || 0;
  } catch {
    /* 保持 0，视为最老壳 */
  }
  const minNative = Number(bundle.min_native_version_code || 0);
  if (minNative > nativeBuild) {
    void toast("服务器有新版本，但需要升级 App 客户端后才能更新");
    return { status: "native-too-old" };
  }

  try {
    return await applyUpdate(bundle, apiBase, activateNow);
  } catch (error) {
    console.warn("[hot-update] 更新失败", error);
    void toast(force ? "更新下载失败，请检查网络后重试" : "更新下载失败，将在下次检查时重试");
    return { status: "error" };
  }
}

async function applyUpdate(bundle, apiBase, activateNow) {
  const version = String(bundle.version);

  // ---- 3. 下载 + 校验 -------------------------------------------------
  const resp = await fetch(`${apiBase}/app-updates/download`);
  if (!resp.ok) throw new Error(`download HTTP ${resp.status}`);
  const buffer = await resp.arrayBuffer();

  const actualSha = await sha256Hex(buffer);
  if (bundle.sha256 && actualSha.toLowerCase() !== String(bundle.sha256).toLowerCase()) {
    throw new Error(`sha256 mismatch: expect ${bundle.sha256}, got ${actualSha}`);
  }

  // ---- 4. 解压写盘 -----------------------------------------------------
  const { unzipSync } = await import("fflate");
  const files = unzipSync(new Uint8Array(buffer));
  const names = Object.keys(files).filter(
    (name) => !name.endsWith("/") && files[name].length > 0,
  );
  if (!names.includes("index.html")) throw new Error("包内缺 index.html，拒装");

  const { Filesystem, Directory } = await import("@capacitor/filesystem");
  let written = 0;
  for (const name of names) {
    await Filesystem.writeFile({
      path: `bundles/${version}/${name}`,
      data: base64FromBytes(files[name]),
      directory: Directory.Data,
      recursive: true,
    });
    written += 1;
  }

  // ---- 5. 写指针（下次冷启动生效），prev 留作回滚点 ---------------------
  const current = await readPointer();
  const prev =
    current && current.path && current.version !== version
      ? { version: current.version, path: current.path }
      : null;
  const bundlePath = await bundleDirUri(version);
  await writePointer({
    version,
    path: bundlePath,
    prev,
    installedAt: new Date().toISOString(),
  });

  if (activateNow) {
    // 手动「检查更新」：立即切到新包（原生 setServerBasePath 会重载 WebView，
    // 下面的代码不会执行；新包启动失败由回滚看门狗兜底）
    void toast("更新完成，正在切换新版本…");
    try {
      await HotUpdate.apply({ path: bundlePath });
    } catch (error) {
      console.warn("[hot-update] 立即切换失败，待冷启动生效", error);
      void toast("已下载完成，重启 App 后生效");
    }
    return { status: "updated", activated: true };
  }

  void toast(`更新完成（${written} 个文件），重启 App 后生效`);
  console.info(`[hot-update] 已就绪 v${version}，重启生效`);
  return { status: "updated", activated: false };
}
