/**
 * 运行时服务器地址配置。
 *
 * ## 为什么需要这个模块
 *
 * Capacitor「内置资源模式」下，页面的 origin 是 `http://localhost`（WebView 的本地服务器），
 * 相对路径 `/api/v1/...` 会打到**手机自己**身上，必然连不上后端。
 * 于是只能在构建时注入绝对地址（`VITE_API_BASE_URL`），但那是「构建期固化」：
 * 服务器一换地址，**已经装在调查员手机上的 APK 全部失效**，只能挨个通知重装。
 *
 * 这里把地址做成「运行时可改」：存在 localStorage，`http.js` 每次请求前解析一次。
 * 于是同一个 APK 可以装到不同环境的机器上，外业现场也随时能切地址。
 *
 * ## 三级优先级（高 → 低）
 *
 * | 优先级 | 来源 | 形态 | 谁改 |
 * |---|---|---|---|
 * | 1 | localStorage `rural_land_server_base` | `http://192.168.1.10:8000` | 用户在 App 内「服务器设置」里改 |
 * | 2 | 构建期 `VITE_API_BASE_URL` | `https://survey.example.cn/api/v1` | 打包的人（`.env` 文件） |
 * | 3 | 同源相对路径 `/api/v1` | `/api/v1` | PC 端 / Capacitor 在线模式，天然同源 |
 *
 * ⚠️ 注意第 2 项带 `/api/v1` 后缀、第 1 项**不带**（只到服务器根）。
 * 这是刻意的：用户在手机上只会知道"服务器地址是 192.168.1.10:8000"，
 * 让他手抄 `/api/v1` 是多余的出错点，所以由程序拼。
 */

const SERVER_KEY = "rural_land_server_base";

/** API 路径前缀，与后端路由挂载点一致（见 backend/app/main.py） */
const API_PREFIX = "/api/v1";

/** 用户输入里可能混进来的路径后缀 / 空白字符 */
const TRAILING_SLASH = /\/+$/;
const TRAILING_API_PREFIX = /\/api\/v1$/i;

/**
 * 规范化用户输入的服务器根地址。
 *
 * 容错三类常见输入：
 * - `192.168.1.10:8000`  → 补上 `http://`（外业手输时几乎不会写协议头）
 * - `http://x:8000/`     → 去掉尾部斜杠
 * - `http://x:8000/api/v1` → 去掉多写的 API 前缀（否则会拼成 `/api/v1/api/v1`）
 *
 * @returns {string} 规范化后的地址；输入为空时返回空串（表示"未设置"）
 */
export function normalizeServerBase(input) {
  let value = String(input ?? "").trim();
  if (!value) return "";

  // 只有省掉协议头的情况才补 http://；已有 https:// 的不能动
  if (!/^https?:\/\//i.test(value)) {
    value = `http://${value}`;
  }

  value = value.replace(TRAILING_SLASH, "").replace(TRAILING_API_PREFIX, "");
  value = value.replace(TRAILING_SLASH, "");

  return value;
}

/** 校验地址形态是否可用，返回错误文案（合法时返回空串） */
export function validateServerBase(input) {
  const raw = String(input ?? "").trim();
  if (!raw) return "";

  const normalized = normalizeServerBase(raw);
  let parsed;
  try {
    parsed = new URL(normalized);
  } catch {
    return "地址格式不正确";
  }

  if (!parsed.hostname) return "缺少主机名或 IP";
  return "";
}

/** 读取运行时设置的服务地址（未设置返回空串） */
export function getServerBase() {
  try {
    return normalizeServerBase(localStorage.getItem(SERVER_KEY));
  } catch {
    // 隐私模式 / 存储被禁（Capacitor 里极少见），退化为"未设置"
    return "";
  }
}

/**
 * 写入运行时服务地址。
 *
 * @param {string} value 服务器根地址；传空串表示「清除设置、回到构建期默认值」
 * @returns {string} 实际落盘的规范化地址
 */
export function setServerBase(value) {
  const normalized = normalizeServerBase(value);
  try {
    if (normalized) {
      localStorage.setItem(SERVER_KEY, normalized);
    } else {
      localStorage.removeItem(SERVER_KEY);
    }
  } catch {
    // 忽略写入失败；调用方可通过 getServerBase() 复核是否真的生效
  }
  return normalized;
}

/** 构建期注入的 API base（可能为空） */
export function getBuildTimeApiBase() {
  const raw = import.meta.env.VITE_API_BASE_URL;
  return typeof raw === "string" ? raw.replace(TRAILING_SLASH, "") : "";
}

/**
 * 解析出本次请求真正要用的 baseURL。
 *
 * 每次请求都调一次（而不是模块加载时算一次），这样用户在设置里改完地址
 * 立刻生效，不需要重启 App。
 */
export function resolveApiBase() {
  const runtimeBase = getServerBase();
  if (runtimeBase) {
    return `${runtimeBase}${API_PREFIX}`;
  }

  const buildTimeBase = getBuildTimeApiBase();
  if (buildTimeBase) {
    return buildTimeBase;
  }

  return API_PREFIX;
}

/**
 * 当前是否处于「地址未明确配置」的状态。
 *
 * 用于在移动端给出提示：此时 `resolveApiBase()` 会退化成 `/api/v1`，
 * 在 App 内置资源模式下等于打到手机自己 —— 必然连不上后端。
 */
export function isApiBaseConfigured() {
  return Boolean(getServerBase() || getBuildTimeApiBase());
}

/** 把后端返回的相对路径（如 `/api/v1/xxx/download`）拼成绝对地址，供 <img>/下载用 */
export function resolveServerUrl(path) {
  const raw = String(path ?? "");
  if (!raw) return "";
  if (/^(https?:|blob:|data:)/i.test(raw)) return raw;

  const runtimeBase = getServerBase();
  const origin = runtimeBase || getBuildTimeApiBase().replace(`${API_PREFIX}`, "");
  if (!origin) return raw;

  return `${origin.replace(TRAILING_SLASH, "")}${raw.startsWith("/") ? raw : `/${raw}`}`;
}
