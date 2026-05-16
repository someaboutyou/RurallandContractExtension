# 农村承包经营权一体化平台

基于 `FastAPI + Vue 3` 的农村承包经营权一体化平台起步工程。

## 目录结构

```text
backend/   python FastAPI 后端
frontend/  Vue 3 前端
docs/      需求、架构、数据模型文档
runtime/   不含代码，包含了基础运行环境（postgis、jdk、python、geoserver）。windows和linux 各有一份
datas/     项目用到的数据
scripts/   项目中用到的启动脚本
```

## 命令说明

### 开发环境

| 命令 | Windows | Linux |
|------|---------|-------|
| 一键启动（后端+PostGIS+GeoServer+前端dev） | `.\scripts\start-all-dev.cmd -WithFrontend` | `bash ./scripts/start-all-dev.sh` |
| 仅后端+基础设施 | `.\scripts\start-all-dev.cmd` | `bash ./scripts/start-all-dev.sh` |
| 停止所有服务 | `.\scripts\stop-all.cmd` | `bash ./scripts/stop-all.sh` |

### 构建与打包

| 命令 | Windows | Linux |
|------|---------|-------|
| 构建（前端混淆+后端Cython编译→.pyd/.so） | `.\scripts\build.cmd` | `bash ./scripts/build.sh` |
| 打包（构建→排除源码→zip/tar.gz） | `.\scripts\package.cmd` | `bash ./scripts/package.sh` |

构建过程：
1. 前端 `npm run build` → `frontend/dist/`（Vite 压缩混淆）
2. 后端 Cython 编译 `.py` → `.pyd`（Windows）/ `.so`（Linux），输出到 `backend/dist/`
3. 源码 `backend/app/*.py` 保持不变，可继续开发
4. 保留 `main.py`、`bootstrap.py`、`land_parcel_repository.py`、`data_import_service.py` 为入口模块

### 生产环境（打包后部署）

| 命令 | Windows | Linux |
|------|---------|-------|
| 一键启动（后端+静态前端） | `.\scripts\start-all.cmd` | `bash ./scripts/start-all.sh` |
| 安装运行时依赖 | `powershell -File .\scripts\install.ps1` | `bash ./scripts/install.sh` |
| 初始化数据库 | `powershell -File .\scripts\init.ps1` | `bash ./scripts/init.sh` |

生产环境特点：
- 前端已预构建为静态文件，后端通过 StaticFiles 托管
- 后端编译产物在 `backend/dist/`，运行时从该目录启动
- 源码 `backend/app/*.py` 保留在开发环境中，不随打包发布
- 不依赖 npm / Node.js

## 数据模型约定

三组核心表以 `survey_*` 命名，遵循「base 存前值、result 存后值」的模式：

- **survey_*_base（base 表）**：存放基础数据和变化前的值。当前状态 `a` 存放在 base 表中
- **survey_*_result（result 表）**：存放变化后的值。`a → b` 时，`b` 写入 result，`a` 保留在 base；`b → c` 时，`c` 写入 result，`b` 保留在 base。即 result 总是最新状态，base 总是上一状态
- **survey_*_diff（diff 表）**：存放完整变化过程记录（如 `a → b`、`b → c`），用于追溯
