from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（config.py 位于 backend/app/core/ 下）。
# .env 一律按绝对路径解析：无论从项目根、backend/ 还是脚本里启动，
# 加载行为保持一致（离线验收脚本不依赖 cwd）。
_BACKEND_DIR = Path(__file__).resolve().parents[2]

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
    jwt_secret_key: str = _INSECURE_JWT_DEFAULT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 8
    #: 生产默认关闭 /docs、/redoc（接口清单不暴露给未认证用户）。
    #: 开发调试时在 .env 里设 ENABLE_DOCS=true 打开。
    enable_docs: bool = False

    model_config = SettingsConfigDict(env_file=_BACKEND_DIR / ".env", env_file_encoding="utf-8")

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg://{self.database_user}:{self.database_password}"
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
