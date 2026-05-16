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
