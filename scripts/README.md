# 脚本与打包能力总览

整套脚本覆盖三个完整阶段：**开发**、**构建**、**生产部署**。

---

## 开发阶段

日常写代码时使用的脚本。

### start-all-dev — 一键启动（开发模式）

拉起整个项目：PostGIS 数据库、Redis 缓存、GeoServer 地图服务、FastAPI 后端，以及可选的 Vue 前端 dev server（带热更新）。

| 场景 | Windows | Linux |
|------|---------|-------|
| 后端 + 基础设施 + 前端 dev | `.\scripts\start-all-dev.cmd -WithFrontend` | `bash ./scripts/start-all-dev.sh` |
| 仅后端 + 基础设施 | `.\scripts\start-all-dev.cmd` | `bash ./scripts/start-all-dev.sh` |

### stop-all — 停止全部服务

停止所有相关进程，包括残留的 Java、Python、Node、Redis 进程，并释放占用的端口（8000、8080、15432、16379、5173）。

| Windows | Linux |
|---------|-------|
| `.\scripts\stop-all.cmd` | `bash ./scripts/stop-all.sh` |

---

## 构建阶段

准备交付时使用。将源码编译为不可读的二进制产物。

### build — 编译前端与后端

前端通过 Vite 压缩混淆输出到 `frontend/dist/`，后端通过 Cython 把 `backend/app/` 下几乎所有 `.py` 编译成平台原生的 `.pyd`（Windows）或 `.so`（Linux）二进制扩展。

编译后的代码不可读，无法直接反编译回源码。仅保留 `main.py` 和 `db/bootstrap.py` 两个入口文件保持 `.py` 格式。

| Windows | Linux |
|---------|-------|
| `.\scripts\build.cmd` | `bash ./scripts/build.sh` |

构建后如需恢复源码继续开发，执行 `git checkout -- backend/`。编译产物 `.pyd` / `.so` 已加入 `.gitignore`，不会被提交到仓库。

---

## 打包阶段

### package — 构建并打包

自动先执行 `build`，然后复制整个项目到临时目录，剔除以下内容：

运行时数据：`runtime/data`、`runtime/logs`、`runtime/.state`（Redis 持久化文件位于 `runtime/data/redis`）
开发依赖：`frontend/node_modules`、`backend/.venv`
仓库与缓存：`.git`、`.pytest_cache`、`.mypy_cache`、`backend/build`
源码：已编译的 `.py` 源文件（入口模块 `main.py`、`bootstrap.py` 除外）
临时文件：`*.pyc`、`*.c`、`.DS_Store`、`Thumbs.db`

最后压缩成带版本号和时间戳的 zip 或 tar.gz，输出到 `dist/` 目录。打包产物不含任何敏感的本地测试数据或源码，可以直接交付客户。

| Windows | Linux |
|---------|-------|
| `.\scripts\package.cmd` | `bash ./scripts/package.sh` |

---

## 生产部署阶段

客户拿到包后，在目标机器上执行以下步骤。

### 1. 解压

### 2. install — 验证运行环境

检查 `runtime/` 下的 postgresql、redis、jdk、python、geoserver 可执行文件是否齐全，Python 依赖是否安装。

| Windows | Linux |
|---------|-------|
| `powershell -File .\scripts\install.ps1` | `bash ./scripts/install.sh` |

### 3. init — 初始化数据库

创建 PostgreSQL 数据库、启用 PostGIS 扩展、启动 Redis 并固定持久化目录、运行 SQL 初始化脚本、引导后端数据模型、配置 GeoServer 工作区和数据存储。生成随机密码与 Redis 连接配置写入 `runtime/.state/runtime.env`。

| Windows | Linux |
|---------|-------|
| `powershell -File .\scripts\init.ps1` | `bash ./scripts/init.sh` |

### 4. start-all — 一键启动（生产模式）

启动 PostGIS、Redis、GeoServer、FastAPI 后端。前端由后端通过 StaticFiles 托管，无需 Node.js 或 npm。

| Windows | Linux |
|---------|-------|
| `.\scripts\start-all.cmd` | `bash ./scripts/start-all.sh` |

启动后访问：
- 后端 API：http://127.0.0.1:8000
- API 文档：http://127.0.0.1:8000/docs
- 前端界面：http://127.0.0.1:8000（由后端托管）
- GeoServer：http://127.0.0.1:8080/geoserver

生产环境运行时不需要 Node.js、npm、Cython 或 C 编译器。

---

## 密码安全机制

整套脚本内置了数据库密码安全策略：

- **首次初始化**：`initdb` 时自动生成 24 位高复杂度随机密码（字符集不含 `@` 以避免连接 URI 解析错误）
- **密码持久化**：写入 `runtime/.state/runtime.env`，各脚本和 Python 配置均从此文件读取
- **默认密码检测**：启动时若检测到密码仍为默认值 `RurallandContractExtension`，自动触发密码轮换
- **原地轮换**：通过 `ALTER ROLE ... PASSWORD` SQL 语句修改密码，不删除数据库数据目录，保护已有数据
- **URL 编码**：后端连接 URI 对密码进行 `quote_plus` 编码，确保特殊字符不会破坏连接串

---

## 完整工作流

```text
┌─ 开发 ──────────────────────────────────────────┐
│  .\scripts\start-all-dev.cmd -WithFrontend       │
│  写代码 → 热更新 → 调试                           │
│  .\scripts\stop-all.cmd                          │
└──────────────────────────────────────────────────┘
                    │
                    ▼ 准备交付
┌─ 构建 ──────────────────────────────────────────┐
│  .\scripts\build.cmd                             │
│  前端 Vite 压缩混淆 → frontend/dist/              │
│  后端 Cython 编译 → .pyd（不可读二进制）           │
└──────────────────────────────────────────────────┘
                    │
                    ▼
┌─ 打包 ──────────────────────────────────────────┐
│  .\scripts\package.cmd                           │
│  排除数据/依赖/源码 → dist/*.zip                  │
└──────────────────────────────────────────────────┘
                    │
                    ▼ 交付客户
┌─ 部署 ──────────────────────────────────────────┐
│  1. 解压                                         │
│  2. install  → 验证运行环境                       │
│  3. init     → 初始化数据库 + 随机密码             │
│  4. start-all → 一键启动                          │
└──────────────────────────────────────────────────┘
```

## 默认配置

数据库：`127.0.0.1:15432/erlunyanbao`，用户 `RurallandContractExtension`
Redis：`127.0.0.1:16379`，持久化目录 `runtime/data/redis`
GeoServer：`http://127.0.0.1:8080/geoserver`，工作区 `erlunyanbao`
后端：`http://127.0.0.1:8000`

---

## Runtime 目录要求

### Windows

`runtime/windows/jdk/bin/java.exe`
`runtime/windows/python/python.exe`（已安装 `backend/requirements.txt`）
`runtime/windows/postgresql/bin/pg_ctl.exe`、`initdb.exe`、`psql.exe`、`createdb.exe`、`pg_isready.exe`
`runtime/windows/redis/redis-server.exe`、`redis-cli.exe`
`runtime/windows/geoserver/bin/startup.bat` 或 `start.jar`

### Linux

`runtime/linux/jdk/bin/java`
`runtime/linux/python/bin/python`（已安装 `backend/requirements.txt`）
`runtime/linux/postgresql/bin/pg_ctl`、`initdb`、`psql`、`createdb`、`pg_isready`
`runtime/linux/geoserver/bin/startup.sh` 或 `start.jar`
