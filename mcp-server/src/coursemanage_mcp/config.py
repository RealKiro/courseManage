# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""运行期配置：全部通过环境变量注入，便于容器化部署。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

ENV_PREFIX: Final = "COURSEMANAGE_"

VALID_TRANSPORTS: Final = ("stdio", "http", "sse")

VALID_LOG_LEVELS: Final = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class ConfigError(RuntimeError):
    """配置不合法。"""


def _env(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(f"{ENV_PREFIX}{name}")
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on", "y")


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - 明显配置错误
        raise ConfigError(f"{ENV_PREFIX}{name} 必须是整数，当前为 {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover
        raise ConfigError(f"{ENV_PREFIX}{name} 必须是数字，当前为 {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """MCP 服务器配置。"""

    # ---- 后端 API ----
    api_base: str = "http://backend:8000"
    username: str | None = None
    password: str | None = None
    token: str | None = None
    timeout: float = 30.0
    verify_ssl: bool = True

    # ---- MCP 传输层 ----
    transport: str = "stdio"
    host: str = "0.0.0.0"
    port: int = 8765
    path: str = "/mcp"
    stateless_http: bool = True

    # ---- 安全与行为 ----
    auth_token: str | None = None
    readonly: bool = False
    allow_notifications: bool = False
    max_items: int = 50
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        transport = (_env("MCP_TRANSPORT", "stdio") or "stdio").lower()
        if transport in ("streamable_http", "streamable-http", "streamablehttp"):
            transport = "http"

        # FastMCP / uvicorn 只接受固定的几个级别，未知值退回 INFO 而不是直接崩溃
        log_level = (_env("LOG_LEVEL", "INFO") or "INFO").upper()
        if log_level == "TRACE":
            log_level = "DEBUG"
        if log_level not in VALID_LOG_LEVELS:
            log_level = "INFO"

        settings = cls(
            api_base=(_env("API_BASE", "http://backend:8000") or "").rstrip("/"),
            username=_env("USERNAME"),
            password=_env("PASSWORD"),
            token=_env("TOKEN"),
            timeout=_env_float("TIMEOUT", 30.0),
            verify_ssl=_env_bool("VERIFY_SSL", True),
            transport=transport,
            host=_env("MCP_HOST", "0.0.0.0") or "0.0.0.0",
            port=_env_int("MCP_PORT", 8765),
            path=_env("MCP_PATH", "/mcp") or "/mcp",
            stateless_http=_env_bool("MCP_STATELESS", True),
            auth_token=_env("MCP_AUTH_TOKEN"),
            readonly=_env_bool("MCP_READONLY", False),
            allow_notifications=_env_bool("MCP_ALLOW_NOTIFICATIONS", False),
            max_items=_env_int("MCP_MAX_ITEMS", 50),
            log_level=log_level,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.api_base:
            raise ConfigError(f"必须设置 {ENV_PREFIX}API_BASE，例如 http://backend:8000")
        if not self.api_base.startswith(("http://", "https://")):
            raise ConfigError(f"{ENV_PREFIX}API_BASE 必须以 http:// 或 https:// 开头")
        if self.transport not in VALID_TRANSPORTS:
            raise ConfigError(
                f"{ENV_PREFIX}MCP_TRANSPORT 只支持 {'/'.join(VALID_TRANSPORTS)}，当前为 {self.transport!r}"
            )
        if not self.token and not (self.username and self.password):
            raise ConfigError(
                f"必须提供 {ENV_PREFIX}TOKEN，或同时提供 "
                f"{ENV_PREFIX}USERNAME 与 {ENV_PREFIX}PASSWORD"
            )
        if not self.path.startswith("/"):
            raise ConfigError(f"{ENV_PREFIX}MCP_PATH 必须以 / 开头")
        if self.max_items < 1:
            raise ConfigError(f"{ENV_PREFIX}MCP_MAX_ITEMS 必须大于 0")
        if not 1 <= self.port <= 65535:
            raise ConfigError(f"{ENV_PREFIX}MCP_PORT 越界：{self.port}")

    def describe(self) -> str:
        """用于启动日志：不泄露任何凭据。"""
        mode = "只读" if self.readonly else "读写"
        auth = "静态 Token" if self.token else f"账号 {self.username}"
        guard = "已启用" if self.auth_token else "未启用"
        return (
            f"api_base={self.api_base} transport={self.transport} 模式={mode} "
            f"认证={auth} 客户端鉴权={guard} max_items={self.max_items}"
        )
