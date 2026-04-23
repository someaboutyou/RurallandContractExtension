# 农村承包经营权一体化平台

基于 `FastAPI + Vue 3` 的农村承包经营权一体化平台起步工程。

当前版本先完成：

- 后端基础骨架
- 前端基础骨架
- 模块化目录设计
- PostgreSQL 数据库接入
- 登录认证与 JWT 基础能力
- 用户 / 角色 / 区域 / 发包方 / 业务申请的初始表结构
- 仪表盘 / 用户权限 / 发包方 / 业务申请的初始页面与接口
- 后续工作流、GIS、数据权限的扩展预留

## 目录结构

```text
backend/   FastAPI 后端
frontend/  Vue 3 前端
docs/      需求、架构、数据模型文档
```

## 后端启动

```powershell
cd E:\Work\RurallandContractExtension\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

如需自定义数据库连接，请先复制环境变量文件：

```powershell
Copy-Item .env.example .env
```

默认地址：

- API: <http://127.0.0.1:8000>
- OpenAPI: <http://127.0.0.1:8000/docs>

初始化演示账号：

- 账号：`admin`
- 密码：`Admin123456`

## 前端启动

```powershell
cd E:\Work\RurallandContractExtension\frontend
npm install
npm run dev
```

默认地址：

- Web: <http://127.0.0.1:5173>

## 第一阶段目标

- 登录认证
- 用户 / 角色 / 区域权限骨架
- 发包方管理
- 业务申请管理
- 审批流预留
- WebGIS 模块预留

## 下一步建议

1. 接入真实数据库 `PostgreSQL + PostGIS`
2. 补登录鉴权与 JWT
3. 引入 `PyCasbin` 做数据权限
4. 引入 `SpiffWorkflow` 做三级审批
5. 接入 `OpenLayers + GeoServer`
