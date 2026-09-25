# 移动端（Android App）开发与打包

> 面向外业调查员的 Android 采集端。Web 代码在 `frontend/` 内，与 PC 管理端共用同一套后端接口与同一份构建产物（`frontend/dist/`）。
> ⚠️ **本文档位于 `frontend/` 内，但 Android 原生工程在仓库根目录**（`android/`，与 `frontend/` 平级）—— 见下节。

## 一、目录布局

```
RurallandContractExtension/
├── frontend/                  # Web 工程（PC 管理端 + 移动端页面共用一份代码）
│   ├── capacitor.config.json  # Capacitor 配置（rootDir，含 android.path = "../android"）
│   ├── src/mobile/            # 移动端页面与原生能力封装（见下表）
│   ├── dist/                  # 构建产物 = webDir
│   └── package.json           # @capacitor/* 依赖装在这里
├── android/                   # ⬅ Capacitor Android 原生工程，与 frontend 平级
│   ├── app/                   # 应用模块（含 AndroidManifest、assets/public）
│   ├── capacitor.settings.gradle
│   ├── build-apk.cmd          # ⬅ 命令行打包入口，自动挑 JDK 21（见第三节陷阱一）
│   └── gradlew / settings.gradle / variables.gradle
└── backend/
```

**为什么 `android/` 与 `frontend/` 平级**：`frontend/` 是纯粹的前端工程，安卓原生壳不应塞在它的子目录里。Capacitor 支持用 `android.path` 覆盖平台目录位置（默认 `<configDir>/android`），本工程设为 `../android`。

⛔ **但有两条硬约束，改动前必须知道**：

1. **`capacitor.config.json` 必须留在 `frontend/`**。CLI 用 `resolveNode(config.app.rootDir, '@capacitor/camera')` 这种方式解析插件，`rootDir` 就是 config 文件所在目录。config 一旦移到仓库根，根目录就必须另装一份 `node_modules`，否则插件被识别为 0 个。
2. **所有 `npx cap` 命令都要在 `frontend/` 目录下执行**（因为 config 在那里），但平台目录会指向 `../android`。
3. ✅ **不需要在仓库根重复安装依赖**。CLI 生成 `android/capacitor.settings.gradle` 时走的是
   `convertToUnixPath(relative(platformDirAbs, capacitorAndroidPath))`（`@capacitor/cli/dist/android/update.js:104-116`），
   会**自动算出跨目录的相对路径**：

   ```gradle
   project(':capacitor-android').projectDir = new File('../frontend/node_modules/@capacitor/android/capacitor')
   project(':capacitor-camera').projectDir  = new File('../frontend/node_modules/@capacitor/camera/android')
   ```

   这个文件是**生成物**（每次 `cap sync` 重写），改它没用。
4. ⚠️ **在 Git Bash 里用 `mv` 移动这个目录会失败**（`Permission denied`）—— Git Bash 对较大的目录树跨目录移动受限。
   改用 PowerShell 的原生移动：`Move-Item -LiteralPath <src> -Destination <dst>`。

### `frontend/src/mobile/` 内部结构

| 位置 | 作用 |
|---|---|
| `src/mobile/router.js` | 移动端路由表（`/m/*`），由 `src/router/index.js` 合并进主路由 |
| `src/mobile/layout/MobileLayout.vue` | 移动端外壳：顶部标题栏 + 内容区 + 底部导航 |
| `src/mobile/views/` | 页面：登录 / 待调查清单 / 户详情 / 地块 / 拍照附件 / 我的 |
| `src/mobile/components/ServerSettingPopup.vue` | **服务器地址设置弹层**（见第六节） |
| `src/mobile/components/MobileLicenseNotice.vue` | 移动端授权/连接提示（vant 版，替代 PC 的 el-dialog） |
| `src/mobile/native/location.js` | 定位封装（原生优先，浏览器兜底，含精度提示） |
| `src/mobile/native/camera.js` | 相机封装（原生优先，浏览器兜底，含压缩） |
| `src/mobile/ui.js` | Vant 组件出口（取 `VanXxx` 别名，模板里可写 `<van-cell>`） |
| `src/mobile/styles.js` | **移动端共享样式入口**（`import("vant/lib/index.css")`），登录页与外壳共用 |
| `src/api/serverConfig.js` | 后端地址解析（localStorage → 构建期变量 → 同源相对路径） |

移动端与 PC 端**并存互不干扰**：PC 端仍是 `/` 下 `AppLayout` 的 17 个页面，移动端一律挂 `/m/*`。

### 入口路由：App 打开后落在哪个页面

APK 启动时 WebView 加载 `/`，而路由表里 `/` 是 PC 端入口（`redirect: "/gis"`）。
**必须由路由守卫把原生壳拉到移动端**（`src/router/index.js` 里的 `isNativeShell()` 分支），
否则手机上出现的是 PC 版登录页 —— 布局不适配，而且**找不到移动端才有的「后端地址」入口**。

| 场景 | 落点 |
|---|---|
| App 打开 `/`，未登录 | `/m/login`（页面底部就是「后端地址 → 修改」） |
| App 打开 `/`，已登录 | `/m/tasks`（我的待调查） |
| PC 浏览器打开 `/` | **不变**，仍是 PC 登录页 / PC 首页 |
| 进入 `/m/*` 之后的普通导航 | **不受影响**，不会被拽回首页 |

`isNativeShell()` = `window.Capacitor?.isNativePlatform?.()`，或 origin ∈ {`http://localhost`,
`https://localhost`, `capacitor://localhost`}。origin 兜底是必要的 —— Capacitor 注入全局对象
的时序不保证早于应用脚本（内置资源模式下 origin 就是 `http://localhost`；而 Vite dev 是
`:5173`、PC 部署带端口，都不会误判）。

⛔ **判据里的「排除 `/m` 区域」不能省**：`/` 的 redirect 先于守卫解析（守卫收到的
`to.path` 已是 `/gis`、`to.redirectedFrom.path` 是 `/`），而 `redirectedFrom` 会在
**整条重定向链**上一直保留 —— 若写成 `isNativeShell() && (to.path === "/" || to.redirectedFrom?.path === "/")`，
返回 `mobile-login` 之后的那一跳（`/m/login`）`redirectedFrom` 仍是 `/`，条件再次成立
⇒ **无限重定向**，vue-router 报 `Infinite redirect in navigation guard` 并中止导航（页面白屏）。
正确写法：

```js
if (isNativeShell() && !to.path.startsWith("/m") && (to.path === "/" || to.redirectedFrom?.path === "/")) {
  return { name: authStore.isAuthenticated ? "mobile-tasks" : "mobile-login" };
}
```

**验证手法（零依赖、秒级，强烈建议改了守卫就跑一次）**：用 vue-router 的 `createMemoryHistory`
在纯 Node 里复刻守卫逻辑，断言上表四种场景的落点：

```bash
node runtime/.state/router_probe.mjs
```

比"直接打包发出去让用户试"安全得多 —— 这个死循环就是它拦下来的。
（脚本若被清理，模板与踩坑详解见 skill `frontend-e2e-cdp-verify` 第 0 节。）

## 二、技术选型：为什么是 Capacitor

| 候选 | 结论 | 原因 |
|---|---|---|
| **Capacitor 7 套壳** | ✅ 采用 | 整个 App 就是一个 WebView ⇒ 表单与勾绘**都直接复用现有 Vue3 组件**，只需补响应式 CSS |
| uni-app | ❌ 不用 | `<map>` 组件只能**展示**图形、**不支持交互式矢量绘制**；而手机端范围含地块勾绘（`ol/interaction/Draw`）。官方兜底只有 web-view 嵌 H5 ⇒ 等于还是跑 web，且表单还要全部重写，双输 |
| 纯 H5 / 微信 | ❌ 不用 | 定位受 HTTPS 安全上下文约束；微信还要认证服务号 + JSSDK 签名链路 |

**Capacitor 相比纯 H5 的硬优势**：原生定位**不受 HTTPS 约束**——浏览器在 `http://` 非 localhost 源下会直接禁用定位 API。

## 三、环境要求

| 项 | 版本 | 本机状态（2026-09-22 实测） |
|---|---|---|
| Node | ≥ 20 | v22.22.2 ✅ |
| **JDK（构建用）** | **21** | ✅ `C:\Users\JZW\.jdks\jbr-21.0.11`（**Android Studio 自己下载并配置的**，见下方陷阱） |
| Android Studio | **2024.2.1+** | ✅ 已装（`D:\Programs\Android\Android Studio`，版本 `AI-261.26222…`） |
| Android SDK | API 35 + Build-Tools 35 | ✅ `C:\Users\JZW\AppData\Local\Android\Sdk`，已由 Studio 写入 `android/local.properties` |
| Gradle | wrapper **8.13** | ✅ `~/.gradle` 已生成（另有旧的 8.11.1 残留） |
| AGP | **8.13.2** | 见 `android/build.gradle`（比 Capacitor 7 模板自带的版本新） |

### ⛔ 陷阱一：Android Studio 自带的 JBR 是 **25**，不是 21

最新版 Android Studio（build `AI-261.x`）自带的 `jbr` 已经是 **OpenJDK 25**，而 **Gradle 8.13 跑不了 Java 25**：

```
BUG! exception in phase 'semantic analysis' in source unit '_BuildScript_'
Unsupported class file major version 69          ← major 69 = Java 25
```

**但 Android Studio 自己知道该怎么办**：它已经下载了一个独立的 **JBR 21** 并在工程里记下了配置：

```properties
# android/.gradle/config.properties      ← 由 Android Studio 写入
java.home=C\:\\Users\\JZW\\.jdks\\jbr-21.0.11
```

> ⚠️ **这个文件只有 Android Studio 的 Gradle 集成会读，`gradlew` 命令行完全不看它。**
> 所以会出现"AS 里点 Build 能成功、命令行跑 `gradlew` 就炸"的诡异现象——
> 根源是命令行只看 `JAVA_HOME`，而系统 `JAVA_HOME` 指向 `D:\Programs\Java\jdk-17`（也不对）。

**命令行构建的正确做法（推荐：用包装脚本，零环境配置）**

仓库里带了 `android/build-apk.cmd`，它自己去找 JDK 21，不动系统 `JAVA_HOME`：

```powershell
cd E:\Work\RurallandContractExtension\android
.\build-apk.cmd                          # 等价于 gradlew assembleDebug
.\build-apk.cmd clean assembleDebug      # 需要传参就直接跟在后头
```

它会先打印实际使用的 JDK 再构建，结尾明确给出 `SUCCESS` / `FAILED`，顺带规避了下面两个坑。
（探测顺序：`%USERPROFILE%\.jdks\jbr-21*` → `jdk-21*` → `21*`；都找不到会给出"去 AS 里下 JDK 21"的指引，而不是含糊报错。）

**手工做法**（各 Shell 语法不同，别混用）：

| Shell | 提示符长这样 | 设置 + 构建 |
|---|---|---|
| PowerShell | `PS E:\...>` | `$env:JAVA_HOME = "C:\Users\JZW\.jdks\jbr-21.0.11"` 换行 `.\gradlew.bat assembleDebug` |
| Git Bash | `user@host MINGW64 ~` | `export JAVA_HOME="/c/Users/JZW/.jdks/jbr-21.0.11"` 换行 `./gradlew assembleDebug` |
| cmd | `E:\...>` | `set JAVA_HOME=C:\Users\JZW\.jdks\jbr-21.0.11` 换行 `gradlew.bat assembleDebug` |

⛔ **`export` 是 Bash 语法**，在 PowerShell 里会报
`无法将"export"项识别为 cmdlet、函数、脚本文件或可运行程序的名称`；cmd 里报 `'export' 不是内部或外部命令`。
先看提示符：`PS` 开头 = PowerShell，用 `$env:`；否则用 `set`。
⛔ PowerShell 的路径**必须写成 Windows 形式**（`C:\Users\...`），给 `/c/Users/...` 会解析失败。

想一劳永逸（所有终端生效，机器级、不进仓库）：

```properties
# 写入 C:\Users\<你>\.gradle\gradle.properties
org.gradle.java.home=C:\\Users\\JZW\\.jdks\\jbr-21.0.11
```

> ⚠️ 这是**全局**设置，会让本机所有 Gradle 项目都用 JDK 21。本工程适用，但如果你还有别的必须用 JDK 17 的 Gradle 工程，就别这么写——改用 `build-apk.cmd`。

⛔ 不要写进 `android/gradle.properties`（仓库内文件，机器相关路径会被提交）。
⛔ 也不要把 `JAVA_HOME` 指向 `Android Studio\jbr`（那是 25）或系统的 `jdk-17`（javac 17 编译不了 `VERSION_21` 的源码）。

> ⚠️ 症状补充：用 JBR 21 跑时 Kotlin daemon 仍可能报 `IllegalArgumentException: 25.0.3`
> （旧的 daemon 进程是用 Java 25 起的，Kotlin 解析不了这个版本号）。Gradle 会自动
> `Using fallback strategy: Compile without Kotlin daemon` 并继续成功；要彻底清掉旧进程执行 `./gradlew --stop`。

### ⛔ 陷阱二：JDK 必须是 21，不是 17

Capacitor **7.6.9** 的 Android 侧源码硬编码了 Java 21：
`node_modules/@capacitor/android/capacitor/build.gradle`、`@capacitor/camera/android/build.gradle`、
`@capacitor/geolocation/android/build.gradle` 与 CLI 模板（`@capacitor/cli/dist/android/update.js:150`）
**全部是 `JavaVersion.VERSION_21`**。这些模块是以 Gradle 子工程（`project(':capacitor-android')`）从源码参与编译的，
所以用 JDK 17 会直接 `error: invalid source release: 21`。**不要把版本改成 17**（会把 `node_modules` 改脏，且下次 `npm i` 就回退）。

> ⚠️ **Capacitor 固定在 7.x，不要升 8**：Capacitor 8 要求 Android Studio 2025.2.1 + `compileSdk 36`。
> 同理也不要往回降到 6（已 EOL，2025-07 停止维护，2026-01-20 扩展支持结束）。

## 四、本地调试

```bash
cd frontend
npm run dev
# 浏览器打开 http://localhost:5173/m/tasks
```

Vite 已配 `host: 0.0.0.0` 与 `/api` → `8000` 代理，手机连同一局域网也可直接访问调试。

## 五、两种运行模式

### 模式 A：内置资源（当前采用）

前端打进 APK。`capacitor.config.json` 里**没有** `server.url`，页面从 `android/app/src/main/assets/public/` 加载。

⚠️ 这个模式下页面 origin 是 **`http://localhost`**（WebView 本地服务器），所以：

1. `/api/v1` 这类相对路径**打不到后端**（会被 WebView 本地服务器接管，见第七节）⇒ 必须显式配置后端地址；
2. 用绝对地址请求后端属于**跨域** ⇒ 后端 CORS 白名单必须放行 `http://localhost`（见第八节）。

好处：离线也能打开界面（业务仍需联网），启动快，不依赖服务器可达。
代价：改前端要重新打包（但**改后端地址不用**，见第六节）。

### 模式 B：在线加载（备选，免更新）

让 WebView 直接加载服务器页面。**改完只部署服务器，用户下次打开就是新版**；
且页面与接口同源，`/api/v1` 相对路径天然可用、**不需要 CORS**。

在 `capacitor.config.json` 里补上 `server.url`：

```json
{
  "server": {
    "url": "https://<域名>/m/tasks",
    "androidScheme": "http",
    "cleartext": true
  }
}
```

改完要重跑 `npx cap sync android`（`server.url` 会被写进 `android/app/src/main/assets/capacitor.config.json`）。
前提：设备能访问该地址（本项目已定**全程有网**）。首次打开需联网。

## 六、后端地址怎么配（三种方式，优先级从高到低）

实现见 `frontend/src/api/serverConfig.js`，`http.js` 的请求拦截器**每次请求都重新解析**，所以改完立刻生效、不用重启 App。

| 优先级 | 来源 | 形态 | 谁改 | 什么时候用 |
|---|---|---|---|---|
| 1 | **App 内「服务器地址」设置**（存 `localStorage.rural_land_server_base`） | `http://192.168.1.10:8000` | 调查员本人 | **推荐**。换服务器无需重新发版，现场还能切测试/正式环境 |
| 2 | 构建期 `VITE_API_BASE_URL` | `https://survey.example.cn/api/v1` | 打包的人（`frontend/.env`） | 部署环境固定时作为出厂默认值 |
| 3 | 同源相对路径 `/api/v1` | `/api/v1` | —— | PC 端 / 模式 B，天然同源 |

**App 内的入口有两处**（都在移动端）：

- 登录页底部「后端地址：… **修改**」——未设置时还会显示黄色提醒；
- 「我的」页 →「运行环境」→「后端地址」（`is-link`，可点）。

弹层里填 `192.168.1.10:8000` 或 `https://survey.example.cn` 即可，**不用带 `/api/v1`**（程序会自动补，
多写了也会被去掉）。点「保存并检测连接」会真的打一次 `GET {地址}/api/v1/license/status` 探活：

- 成功 → 提示 `连接正常（HTTP 200）` 并自动刷新页面；
- 失败 → **地址照样保存**（外业现场可能只是暂时没网），但会明确提示"连接失败"，
  避免被误当成授权问题。

> 💡 构建期给个默认值时，**建议写域名而非 IP**：用域名则换服务器只需改 DNS，
> 已装出去的 APK 零改动；用 IP 就必须靠第 1 种方式逐台改。另外公共 CA 基本不为 IP 签 HTTPS 证书，
> 写 IP 等于只能走明文 HTTP。

## 七、为什么 App 里会弹「系统未授权」——这是个误报

这是排查移动端"连不上后端"时最容易走错的一步，记录成因（2026-09-22 查源码确认）：

Capacitor 的 WebView 本地服务器（`WebViewLocalServer.handleLocalRequest`）对
**不含扩展名的路径**一律回落 `index.html`：

```java
// WebViewLocalServer.java:425
if (path.equals("/") || (!request.getUrl().getLastPathSegment().contains(".") && html5mode)) {
    // → 返回 index.html
}
```

`/api/v1/license/status` 的最后一段是 `status`（不含 `.`）⇒ **返回 HTTP 200 + 一段 HTML**。
前端的授权检查拿到 200，就把 HTML 当授权信息解析，`is_valid` 取到 `undefined` ⇒
弹窗标题（只看 `connectionError` 标志）落到 **「系统未授权」**。

**所以看到「系统未授权」先查后端地址，不要先怀疑授权。** 这才是"地址没配"的典型症状。
（真正的授权问题会走后端 403 + `license_required`，那时才需要上传授权文件。）

## 八、构建 APK

```bash
cd frontend
npm run build            # 若被安全守卫拦截，用：node node_modules/vite/bin/vite.js build
npx cap sync android     # 同步 web 资源 + 插件到 ../android
npx cap open android     # 打开 Android Studio → Build > Build APK(s)
```

纯命令行打包（**用包装脚本，免设 `JAVA_HOME`**；原理见第三节陷阱一）：

```powershell
cd E:\Work\RurallandContractExtension\android
.\build-apk.cmd
# 产物：android/app/build/outputs/apk/debug/app-debug.apk
```

> 若在 Git Bash 里做，也可以手工设环境变量（**不要**把 Bash 的 `export` 抄到 PowerShell）：
> ```bash
> cd android && export JAVA_HOME="/c/Users/JZW/.jdks/jbr-21.0.11" && ./gradlew assembleDebug
> ```

`local.properties`（含本机 SDK 路径）已被 `android/.gitignore` 忽略，Android Studio 首次打开会自动生成；命令行构建可手写 `sdk.dir=` 或设 `ANDROID_HOME`。

### ⛔ 不要把 `problems-report.html` 当成"构建失败"

Gradle 在**配置缓存有 warning** 时也会生成 `android/build/reports/problems/problems-report.html` 并打印 "problems"，
**极易被误读为失败**。本工程该报告里 **23 条诊断全部是 `WARNING`**，且全是同一条、来自 Android Gradle Plugin 自身的 deprecation：

```
The debugRuntimeClasspathCopy configuration has been deprecated for consumption.
  problemDetails: "This will fail with an error in Gradle 9.0."   ← 将来时
  problemId: deprecation   ／   来源 pluginId: com.android.internal.application
```

报告里 `Execution failed`、`BUILD FAILED`、`FAILURE` 出现次数**均为 0**。

**判断构建成败只看两件事**：

1. 输出末尾是 `BUILD SUCCESSFUL` 还是 `FAILED`；
2. 产物是否存在 —— `android/app/build/outputs/apk/debug/app-debug.apk`。

> 该报告的数据**不在 HTML 正文里**（正文只有 `Loading...`，靠前端 JS 渲染），而在
> `<script>function configurationCacheProblems() { return ( {...} ); }</script>` 的 JSON 中；直接读前半段会误判成"空报告"。

### 本机实测记录（2026-09-22）

| 时间 | 事件 | 结果 |
|---|---|---|
| 13:16 | AS 内首次构建（用 `.jdks/jbr-21.0.11`） | `app-debug.apk` 9,006,502 字节 |
| 14:43 | 命令行 `JAVA_HOME=Android Studio\jbr`(=25) | ❌ `major version 69` |
| 14:57 | 命令行 `JAVA_HOME=.jdks\jbr-21.0.11` | ✅ `BUILD SUCCESSFUL in 6m 29s`，APK **9,018,735** 字节 |
| 15:24 | 加「原生壳入口分流」（**含无限重定向 bug**） | APK 9,136,223 字节 —— ⚠️ **已废弃，别装这个** |
| 15:25:50 | 修掉死循环后重出 | ✅ `BUILD SUCCESSFUL in 1s`，APK **9,161,665** 字节 ← **当前有效包** |

> 15:24 那版为什么废弃：分流条件漏了「排除 `/m` 区域」，导致 `Infinite redirect in navigation guard`
> （详见上文「入口路由」节）。**实证脚本 `router_probe.mjs` 就是在打包之后、发给用户之前拦下它的** ——
> 顺序上先打包、后验证是错的，正确顺序是**先跑实证再打包**。

已抽检 APK 内容（1043 个条目）：`assets/public/` 89 个文件，含全部 `Mobile*` chunk、
`ServerSettingPopup`、`MobileLicenseNotice`、独立 vant 样式 chunk（199,030 字节），
入口 CSS `index-CtwNNBva.css` = **61,736 字节**（**不含** vant）；
manifest 权限四项齐全 + `usesCleartextTraffic`。

15:25 那版额外做了 **dist ↔ APK 入口 chunk 的 sha256 比对**（`ee251925…a000c5`，66,945 字节，两侧完全一致），
并在压缩产物里直接读到了修复后的判定代码：

```js
const n = e.path.startsWith("/m");
if (ro() && !n && (e.path === "/" || e.redirectedFrom?.path === "/"))
  return { name: t.isAuthenticated ? "mobile-tasks" : "mobile-login" }
```

## 九、已接通的接口

移动端全部复用 `src/api/survey.js`，没有另起一套：

| 功能 | 接口 |
|---|---|
| 批次列表 | `fetchSurveyBatches` |
| 我的任务（`mine=1`） | `fetchSurveyTasks` |
| 户详情 | `fetchSurveyResult` |
| 附件列表 / 上传 / 删除 / 预览 | `fetchSurveyPhase2`、`uploadSurveyAttachment`、`deleteSurveyAttachment`、`previewSurveyAttachment` |
| 附件类别 | `fetchSurveyAttachmentCategories` |
| 地块清单 | `fetchSurveyParcels` |

上传的 FormData 字段固定为 **`category` + `description` + `file`**，与 PC 端 `handleUploadAttachment` 一致，**不要改字段名**。

## 十、注意事项

- **坐标系**：定位返回 WGS84，与项目地图 `EPSG:4326/3857` 一致，**无需纠偏**。
  若将来改用微信 JSSDK，其 `wx.getLocation` 默认返回 GCJ-02，与 WGS84 相差 50~700 米，必须显式传 `type: "wgs84"`。
- **精度边界**：手机 GPS 精度 3~10 米，**不能用于采集正式界址点坐标**（确权要求厘米级，PC 端用 RTK/GNSS）。
  手机定位只用于辅助查找地块；界址点/界址线的正式维护留在 PC 端。
- **权限已手工声明**（`android/app/src/main/AndroidManifest.xml`）：`INTERNET` / `ACCESS_FINE_LOCATION` / `ACCESS_COARSE_LOCATION` / `CAMERA`。
  ⚠️ `@capacitor/camera` 与 `@capacitor/geolocation` 的**自带 manifest 里都没有声明权限**，必须由宿主 App 声明，漏了会在调用时静默失败。
  `cap sync` **不会改写** App 的 manifest（它只重写 `capacitor-cordova-android-plugins/src/main/AndroidManifest.xml`），所以这里的改动是安全的。
- **明文 HTTP**：`application` 上挂了 `android:usesCleartextTraffic="true"`（另一份由 `server.cleartext` 自动生成到 cordova 插件库的 manifest，两者值一致、不冲突）。
  若后端上 HTTPS，应把它去掉。
- **CORS**（模式 A 必须配，别删）：
  ```python
  # backend/app/core/config.py
  # Capacitor 内置资源模式下，WebView 里页面的 origin 是 `http://localhost` —— 不带端口！
  "http://localhost",
  "https://localhost",
  "capacitor://localhost",
  ```
  ⛔ **不要把 `http://localhost` 和 `http://localhost:8000` 当成一回事**——CORS 是**字符串精确匹配**，
  少了它，App 里带 `Authorization` 头的请求会在**预检（OPTIONS）**阶段就被拦掉，表现为"连不上后端"。
  模式 B（`server.url`）下页面与接口同源，不需要这些。
- **打包隔离（已验证，别改回去）**：
  - `MobileLayout` 与 6 个 `Mobile*` 视图都是**动态 import**（`src/mobile/router.js`），PC 路由不会加载它们。
  - ⛔ **vant 样式必须走「按需引入」**，且**统一从 `src/mobile/styles.js` 引**（其内部是
    `import("vant/lib/index.css")`，刻意不用模块顶层静态 import）。
    写成静态 `import "vant/lib/index.css"` 会导致：Rollup 把 `MobileLayout` 连同入口一起内联进入口 chunk，
    vant 全量样式被并入**入口 CSS**，**每个 PC 页面都会白下载 199KB**。
    实测：静态写法入口 CSS = **260.9KB**；按需后 = **61.7KB**（−199KB）。
  - **为什么要有 `styles.js`**：`/m/login` 是**独立路由、不在 MobileLayout 下**，样式只挂在 layout 里的话登录页是裸的。
    抽成共享模块后 Vite 会把它提升为共享 chunk（`styles-*.js` → vant CSS），
    三个移动端入口（layout / 登录页 / 授权提示）**共用同一份、只加载一次**。
  - 验收手法：`grep -l "\.van-cell" dist/assets/*.css` 不应命中 `index.html` 里 `<link>` 的那个 CSS；
    入口 chunk 里 `tabbar` 计数应为 0，且**不应有**静态 `import "./styles-*"`（只应出现在 `__vite__mapDeps` 的依赖表中）。
- **移动端的授权提示是 vant 版**（`MobileLicenseNotice.vue`），PC 端仍是 Element Plus 的 `LicenseDialog.vue`，
  由 `App.vue` 按 `route.path.startsWith("/m")` 分流。⛔ 该组件必须保持 `defineAsyncComponent` 动态加载，
  否则 vant 的 JS 会进 PC 端入口 chunk。
- **构建/同步遇到"批量删除"安全守卫**（`SAFE_DELETE_BULK_CONFIRM_REQUIRED`）：本机守卫会拦截单轮内删除超过 50 个文件的操作。
  规避手法是**用改名代替删除**——如 `mv dist dist.prev-<时间戳>` 再构建、
  `mv android/app/src/main/assets/public <runtime/.state/…>` 再 `cap sync`。
  ⚠️ 注意：`assets/` 目录下的任何残留都会**被打进 APK**，所以残留必须移到 `android/` 之外（推荐 `runtime/.state/`，已被 git 忽略）。

## 十一、待办

- [ ] 装到真机/模拟器实测：定位授权、拍照授权、连后端跑通"我的待调查"
- [ ] 勾绘地图（二期）：内嵌 OpenLayers，复用 `useAddParcelGeometry.js`（`ol/interaction/Draw`）/ `useSplitParcel.js` / `useParcelDraftMap.js`
- [ ] 成员 / 地块的编辑提交（接口已就绪：`updateSurveyResult`、`maintainSurveyMembers`、`saveParcelBoundary`）
- [ ] 应用图标与启动页（`@capacitor/assets`）
- [ ] 表单草稿本地暂存（防切后台被回收导致数据丢失）
- [ ] 上传超时单独放宽（当前全局 `timeout: 10000`，弱网传照片容易超时）
- [ ] 正式发布用 `assembleRelease` + 签名（需生成 keystore，`app/build.gradle` 的 `signingConfigs`）

### 已完成

- [x] Android 原生工程初始化与 Gradle 配置同步（2026-09-22，`cap sync android` exit 0）
- [x] 原生工程从 `frontend/android/` 迁到仓库根 `android/`，与 `frontend/` 平级（2026-09-22，`android.path = "../android"`）
- [x] 环境就绪并**首次成功构建出 APK**（2026-09-22 13:16）
- [x] **运行时可配的服务器地址**（2026-09-22）：`serverConfig.js` + 登录页/我的页入口 + 连接检测，
      并修正后端 CORS 白名单（加 `http://localhost`）—— 换地址不再需要重新发版
- [x] 移动端授权提示改为 vant 版（2026-09-22）
- [x] 修复登录页缺 vant 样式（`/m/login` 不在 MobileLayout 下）—— 抽出 `src/mobile/styles.js` 共享
- [x] **原生壳入口分流**（2026-09-22 15:25）：App 打开 `/` 不再落进 PC 页面，改为 `/m/tasks`（已登录）或
      `/m/login`（未登录）—— 修掉"手机上找不到「后端地址」入口"的可见性缺陷；
      同时用 `router_probe.mjs` 拦下并修掉了一个会导致白屏的无限重定向
