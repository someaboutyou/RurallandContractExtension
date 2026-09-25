from pydantic_settings import BaseSettings, SettingsConfigDict


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
    jwt_secret_key: str = "replace-this-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 8

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def sqlalchemy_database_uri(self) -> str:
        return (
            f"postgresql+psycopg://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


settings = Settings()
