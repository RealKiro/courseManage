# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""courseManage 后端 API 异步客户端。

职责：
  * OAuth2 密码模式登录（``POST /api/auth/login``），缓存 JWT
  * 401 时自动重新登录并重放一次请求
  * 把后端错误翻译成对 LLM 友好的中文提示（含高级授权/权限不足提示）
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

_JSON = dict[str, Any] | list[Any]


class ApiError(RuntimeError):
    """后端返回了错误响应，或网络层失败。"""

    def __init__(self, message: str, *, status: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


def _friendly(status: int, detail: str, method: str, path: str) -> str:
    if status == 401:
        return f"认证失败（{method} {path}）：账号或密码错误，或 Token 已过期。"
    if status == 403:
        return (
            f"权限不足或功能未授权（{method} {path}）：{detail or '需要更高角色权限'}。"
            "若提示需要激活，请在系统的「系统授权管理」中启用对应高级功能。"
        )
    if status == 404:
        return f"资源不存在（{method} {path}）：{detail or '请确认 ID 是否正确'}。"
    if status == 422:
        return f"参数校验失败（{method} {path}）：{detail}"
    if status >= 500:
        return f"后端服务异常（{method} {path}，HTTP {status}）：{detail or '请检查后端日志'}。"
    return f"请求失败（{method} {path}，HTTP {status}）：{detail}"


def _extract_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(payload, dict):
        detail = payload.get("detail", payload)
    else:
        detail = payload
    if isinstance(detail, list):
        # FastAPI 校验错误
        parts = []
        for item in detail:
            if isinstance(item, Mapping):
                loc = ".".join(str(x) for x in item.get("loc", []) if x != "body")
                parts.append(f"{loc}: {item.get('msg', '')}".strip(": "))
            else:
                parts.append(str(item))
        return "；".join(parts)[:800]
    return str(detail)[:800]


class CourseManageClient:
    """轻量级 API 客户端，供 MCP 工具复用同一条连接池。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = settings.token
        self._static_token = bool(settings.token)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ 生命周期
    @property
    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._settings.api_base,
                timeout=self._settings.timeout,
                verify=self._settings.verify_ssl,
                follow_redirects=True,
                headers={"User-Agent": "coursemanage-mcp/1.0"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    # ------------------------------------------------------------------ 认证
    async def login(self, *, force: bool = False) -> str:
        async with self._lock:
            if self._token and not force:
                return self._token
            if not (self._settings.username and self._settings.password):
                raise ApiError(
                    "未配置 COURSEMANAGE_USERNAME / COURSEMANAGE_PASSWORD，无法自动登录。",
                    status=401,
                )
            try:
                response = await self._http.post(
                    "/api/auth/login",
                    data={
                        "username": self._settings.username,
                        "password": self._settings.password,
                    },
                )
            except httpx.HTTPError as exc:
                raise ApiError(f"无法连接后端 {self._settings.api_base}：{exc}") from exc

            if response.status_code >= 400:
                raise ApiError(
                    _friendly(response.status_code, _extract_detail(response), "POST", "/api/auth/login"),
                    status=response.status_code,
                )
            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise ApiError("登录响应中缺少 access_token", status=500, detail=payload)
            self._token = token
            self._static_token = False
            logger.info("已登录 courseManage：用户 %s", self._settings.username)
            return token

    # ------------------------------------------------------------------ 请求
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
        _retry: bool = True,
    ) -> _JSON:
        token = self._token or await self.login()
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        # httpx 不会把 bool 序列化成 true/false，需要手动转换
        for key, value in list(clean_params.items()):
            if isinstance(value, bool):
                clean_params[key] = "true" if value else "false"

        try:
            response = await self._http.request(
                method,
                path,
                params=clean_params or None,
                json=json,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"请求 {method} {path} 失败：{exc}") from exc

        if response.status_code == 401 and _retry and not self._settings.token:
            logger.info("Token 已失效，重新登录后重试 %s %s", method, path)
            await self.login(force=True)
            return await self.request(method, path, params=params, json=json, _retry=False)

        if response.status_code >= 400:
            detail = _extract_detail(response)
            raise ApiError(
                _friendly(response.status_code, detail, method, path),
                status=response.status_code,
                detail=detail,
            )

        if response.status_code == 204 or not response.content:
            return {"ok": True}
        try:
            return response.json()
        except ValueError:
            return {"ok": True, "raw": response.text[:1000]}

    # ------------------------------------------------------------------ 便捷方法
    async def get(self, path: str, **params: Any) -> _JSON:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: Any | None = None, **params: Any) -> _JSON:
        return await self.request("POST", path, params=params, json=json)

    async def put(self, path: str, json: Any | None = None, **params: Any) -> _JSON:
        return await self.request("PUT", path, params=params, json=json)

    async def delete(self, path: str, **params: Any) -> _JSON:
        return await self.request("DELETE", path, params=params)

    async def ping(self) -> dict[str, Any]:
        """不带认证的健康检查。"""
        try:
            response = await self._http.get("/health")
        except httpx.HTTPError as exc:
            return {"reachable": False, "error": str(exc), "api_base": self._settings.api_base}
        return {
            "reachable": response.status_code < 400,
            "status_code": response.status_code,
            "api_base": self._settings.api_base,
        }
