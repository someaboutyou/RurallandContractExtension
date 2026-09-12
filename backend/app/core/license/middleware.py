# -*- coding: utf-8 -*-
"""
授权检查中间件

只拦截 API 请求；前端静态文件和页面路由始终放行，
由前端自行调用 /api/v1/license/status 判断授权状态并展示提示。
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .license_validator import license_validator
from .license_models import LicenseStatus


class LicenseCheckMiddleware(BaseHTTPMiddleware):

    # API 白名单（前缀匹配，不受授权限制）
    _API_WHITELIST = (
        "/api/v1/auth",
        "/api/v1/license",
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. 非 API 请求（前端页面、静态资源）一律放行
        if not path.startswith("/api/"):
            return await call_next(request)

        # 2. API 白名单放行
        for prefix in self._API_WHITELIST:
            if path.startswith(prefix):
                return await call_next(request)

        # 3. 其余 API：授权无效则拦截
        result = license_validator.validate()
        if result.status != LicenseStatus.VALID:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "license_required",
                    "status": result.status.value,
                    "message": result.error_message,
                    "detail": "系统未授权，请联系管理员",
                },
            )

        return await call_next(request)
