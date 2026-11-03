from contextlib import asynccontextmanager
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.api.router import api_router
from app.core.config import settings
from app.db.bootstrap import bootstrap_database
from app.core.license.middleware import LicenseCheckMiddleware


def setup_logging() -> None:
    # ⛔ 走 app.paths（编译布局下裸 parents[N] 会把日志写进 backend/dist/runtime/logs）
    from app.paths import RUNTIME_DIR

    log_dir = RUNTIME_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "backend-app.log"

    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(isinstance(handler, RotatingFileHandler) and getattr(handler, "baseFilename", None) == str(log_file) for handler in root_logger.handlers):
        root_logger.addHandler(file_handler)


# ---------------------------------------------------------------------------
# 生产环境：单端口部署 — 前端静态文件 + GeoServer 反向代理
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """向上查找包含 backend/ 和 frontend/ 的项目根目录。

    兼容 dev（backend/app/main.py）和 prod（backend/dist/app/main.py）两种运行路径。
    """
    current = Path(__file__).resolve().parent
    for _ in range(6):
        current = current.parent
        if (current / "backend").is_dir():
            return current
    return Path(__file__).resolve().parents[2]


def _find_frontend_dist() -> Path | None:
    """返回已构建的前端静态文件目录，不存在则返回 None。"""
    dist_dir = _find_project_root() / "frontend" / "dist"
    if (dist_dir / "index.html").exists():
        return dist_dir
    return None


# ---- GeoServer 反向代理（需要 httpx，未安装则跳过注册） ----

_geoserver_client = None
_geoserver_base_url = "http://127.0.0.1:8080/geoserver"

try:
    import httpx  # noqa: F401

    async def _get_geoserver_client():
        global _geoserver_client
        if _geoserver_client is None:
            _geoserver_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        return _geoserver_client

    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


async def _proxy_geoserver_request(request: Request, path: str) -> Response:
    """将请求转发到本地 GeoServer。"""
    if not _HAS_HTTPX:
        return Response(
            content="httpx is not installed; GeoServer proxy unavailable.",
            status_code=500,
        )

    client = await _get_geoserver_client()
    target = f"{_geoserver_base_url}/{path}" if path else _geoserver_base_url
    if request.url.query:
        target = f"{target}?{request.url.query}"

    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()

    resp = await client.request(
        method=request.method,
        url=target,
        headers=headers,
        content=body or None,
    )

    response_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in ("transfer-encoding", "content-encoding", "connection")
    }

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=response_headers,
        media_type=resp.headers.get("content-type"),
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    bootstrap_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        # 生产默认关闭接口文档（审计 L2）：/docs 会把全部接口清单与参数结构
        # 暴露给未认证用户。开发调试时在 backend/.env 设 ENABLE_DOCS=true。
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        lifespan=lifespan,
    )

    # 添加授权检查中间件
    app.add_middleware(LicenseCheckMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["Health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    # ---- API 路由 -------------------------------------------------------
    app.include_router(api_router, prefix=settings.api_prefix)

    # ---- 手机 App 安装包下载（免登录静态目录） ---------------------------
    # APK 放 backend/storage/app-downloads/，字典 app_download.path 填
    # /downloads/<文件名>（右上角二维码 = http://{外网ip}:{port}{path}）。
    # 放在 SPA catch-all 之前注册才能被命中；license 中间件只拦 /api/*，
    # 手机浏览器扫码下载发生在登录之前，走这里天然放行。
    from app.paths import STORAGE_DIR

    # Windows 注册表可能没有 .apk 映射，StaticFiles 会退回 text/plain，
    # 部分浏览器会当成网页渲染而不是触发下载；这里显式补上标准类型。
    import mimetypes

    mimetypes.add_type("application/vnd.android.package-archive", ".apk")

    app_downloads_dir = STORAGE_DIR / "app-downloads"
    app_downloads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/downloads", StaticFiles(directory=str(app_downloads_dir)), name="app-downloads")

    # ---- GeoServer 反向代理 --------------------------------------------
    if _HAS_HTTPX:
        proxy_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]

        @app.api_route("/geoserver/{path:path}", methods=proxy_methods, tags=["GeoServer Proxy"])
        async def proxy_geoserver(request: Request, path: str):
            return await _proxy_geoserver_request(request, path)

        @app.api_route("/geoserver", methods=proxy_methods, tags=["GeoServer Proxy"])
        async def proxy_geoserver_root(request: Request):
            return await _proxy_geoserver_request(request, "")
    else:
        logging.getLogger(__name__).warning(
            "httpx not installed — GeoServer reverse proxy is disabled. "
            "Install httpx to enable single-port deployment."
        )

    # ---- 前端静态文件 + SPA catch-all（最低优先级，仅在生产/构建后生效）----
    frontend_dist = _find_frontend_dist()
    if frontend_dist:
        from starlette.responses import FileResponse

        _static = StaticFiles(directory=str(frontend_dist))

        @app.get("/{path:path}", include_in_schema=False)
        async def serve_frontend(path: str):
            # 如果是真实文件（js/css/图片等），直接返回
            file_path = frontend_dist / path
            if file_path.is_file():
                return FileResponse(file_path)
            # 否则返回 index.html，让前端路由接管
            return FileResponse(frontend_dist / "index.html")

    return app


app = create_app()
