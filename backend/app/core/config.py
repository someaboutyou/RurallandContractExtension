from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（config.py 位于 backend/app/core/ 下）。
# .env 一律按绝对路径解析：无论从项目根、backend/ 还是脚本里启动，
# 加载行为保持一致（离线验收脚本不依赖 cwd）。
#
# ⛔ Cython 编译布局：backend/dist/app/core/config.pyd → parents[2] = backend/dist，
# 而 install.ps1 在目标机把 .env 写到 backend/.env（package.ps1 排除一切 .env，
# dist 里也不会有）。模块位于 dist/ 内 ⇒ 跑的是编译产物，.env 回落到上一级 backend/。
# 否则编译产物在构建自检和目标机上都会因找不到 .env 被下方 JWT fail-fast 拦死。
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if _BACKEND_DIR.name.lower() == "dist":
    _BACKEND_DIR = _BACKEND_DIR.parent

# ⛔ 安全哨兵：jwt_secret_key 等于该默认值时启动即失败（见文件末尾 fail-fast）。
_INSECURE_JWT_DEFAULT = "replace-this-in-production"


class Settings(BaseSettings):
    app_name: str = "Rural Land Contract Extension Platform"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = [
        # 开发环境（Vite dev server）
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        # 生产环境 / 单端口部署
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        # Capacitor 移动端（内置资源模式）
        #
        # WebView 里页面的 origin 是 `http://localhost` —— **不带端口**，
        # 与上面的 `http://localhost:8000` 不是同一个字符串，CORS 是精确匹配，必须单独列出。
        # 此时 App 用绝对地址请求后端属于跨域，而请求带 `Authorization` 头会触发
        # 预检（OPTIONS），白名单缺了它就在浏览器/WebView 侧直接被拦，表现为"连不上后端"。
        #
        # ⚠️ 只有 Capacitor「在线模式」（capacitor.config.json 配了 server.url，
        # 页面从服务器加载）才是同源、不需要这些；当前工程用的是内置资源模式。
        # origin 的具体形态取决于 server.androidScheme：
        #   http（当前）→ http://localhost ｜ https → https://localhost ｜ iOS 默认 → capacitor://localhost
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
    ]
    database_host: str = "127.0.0.1"
    database_port: int = 5432
    database_name: str = "erlunyanbao"
    database_user: str = "RurallandContractExtension"
    database_password: str = "RurallandContractExtension"
    #: 目标坐标系（EPSG 代码）。安装初始化时由 install.ps1 让部署人选择后写入 .env，
    #: 首次启动固化进 system_config 表，此后不再允许修改（改带只能走全库迁移工具）。
    #: 环境变量名 TARGET_SRID，默认 4527（CGCS2000 3°带 39 带）保持现网兼容。
    target_srid: int = 4527
    #: 区域初始化范围：6 位国家统计局县级区划码，逗号分隔（如 150502,150521）。
    #: 安装时由 install.ps1 让部署人填写后写入 .env；后端首次启动 bootstrap 从
    #: 随包分发的 region_full.zip（fetch_region_seed.py --full 生成）抽取
    #: 省->市->县->镇->村 子树「缺则补」。留空则**不初始化任何区域**（全新库为空），
    #: 由部署人补配 .env 后重启，或在「区域管理」页手工建立。
    region_seed_counties: str = ""
    jwt_secret_key: str = _INSECURE_JWT_DEFAULT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 8
    #: 生产默认关闭 /docs、/redoc（接口清单不暴露给未认证用户）。
    #: 开发调试时在 .env 里设 ENABLE_DOCS=true 打开。
    enable_docs: bool = False

    # ⛔ 编码必须 utf-8-sig：install.ps1（PS 5.1 Set-Content -Encoding UTF8）等
    # Windows 工具写 .env 可能带 BOM，按裸 utf-8 读时首键名会变成 "\ufeffapp_name"，
    # 被 pydantic 当多余字段拒掉（extra_forbidden，目标机 init 阶段炸过）。utf-8-sig
    # 对无 BOM 文件行为与 utf-8 完全一致，读带 BOM 文件自动剥离。
    model_config = SettingsConfigDict(env_file=_BACKEND_DIR / ".env", env_file_encoding="utf-8-sig")

    @property
    def sqlalchemy_database_uri(self) -> str:
        # ⛔ 密码必须 URL 编码：init.ps1/start-postgres.ps1 生成的随机密码曾含
        # !#$%&* 等字符，裸拼进 URI 时 # 被当 fragment、% 被当百分号编码，
        # psycopg 解析出的密码就错了 ⇒ FATAL: password authentication failed
        # （2026-10-19 目标机全新部署 init 阶段踩过）。quote_plus 对任意密码安全。
        return (
            f"postgresql+psycopg://{quote_plus(self.database_user)}:{quote_plus(self.database_password)}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


settings = Settings()

# ---------------------------------------------------------------------------
# ⛔ 安全 fail-fast（审计 H1）：默认 JWT 密钥等于公开硬编码值时，任何人都能
# 自签 `{"sub":"1"}` 伪造成平台管理员读取全部租户数据。宁可拒绝启动，
# 也不允许带着公开密钥上线。修复方式：在 backend/.env 写入随机
# JWT_SECRET_KEY（scripts/install.ps1 / 本仓库 .gitignore 已忽略 .env）。
# ---------------------------------------------------------------------------
if not settings.jwt_secret_key or settings.jwt_secret_key == _INSECURE_JWT_DEFAULT:
    raise RuntimeError(
        "JWT_SECRET_KEY 仍为公开默认值，拒绝启动。"
        "请在 backend/.env 中配置随机密钥，例如："
        "python -c \"import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))\""
    )
