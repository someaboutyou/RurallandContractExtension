# 启动脚本

- `start-backend.ps1`：启动 FastAPI 后端
- `start-frontend.ps1`：启动 Vue 前端
- `start-dev.ps1`：分别打开两个 PowerShell 窗口，同时启动前后端
- `start-backend.cmd`：在 `cmd` 中启动 FastAPI 后端
- `start-frontend.cmd`：在 `cmd` 中启动 Vue 前端
- `start-dev.cmd`：分别打开两个 `cmd` 窗口，同时启动前后端

在项目根目录执行示例：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-backend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-frontend.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

在 `cmd` 中执行示例：

```bat
scripts\start-backend.cmd
scripts\start-frontend.cmd
scripts\start-dev.cmd
```
