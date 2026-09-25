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
    # - /api/v1/license：必须放行，否则前端无法查询授权状态、获取机器码、上传新授权文件
    # - /api/v1/auth   ：放行登录动作本身，使未授权时仍能进入系统看到授权提示并上传授权文件
    #   （业务数据接口仍会被拦截，见下方第 3 步）
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
        #    validate() 的结果与授权文件签名绑定，文件被替换/删除会立即反映出来
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
                headers={"Cache-Control": "no-store"},
            )

        return await call_next(request)
