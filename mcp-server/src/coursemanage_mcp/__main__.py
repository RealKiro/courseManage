# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""命令行入口：``python -m coursemanage_mcp`` 或 ``coursemanage-mcp``。"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import hmac
import json
import logging
import sys
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from . import __version__
from .client import CourseManageClient
from .config import ConfigError, Settings
from .server import build_server

logger = logging.getLogger("coursemanage_mcp")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]

HEALTH_PATHS = ("/healthz", "/health")


class GatewayMiddleware:
    """纯 ASGI 中间件：健康检查 + 客户端 Bearer 鉴权。

    刻意不使用 ``BaseHTTPMiddleware``——它会缓冲响应体，
    破坏 Streamable HTTP / SSE 的流式语义。
    """

    def __init__(self, app: Any, *, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = "/" + (scope.get("path") or "/").strip("/")
        if path in HEALTH_PATHS:
            await self._json(send, 200, {"status": "ok", "version": __version__})
            return

        if self.token and not self._authorized(scope):
            await self._json(send, 401, {"error": "unauthorized", "detail": "缺少或错误的访问令牌"})
            return

        await self.app(scope, receive, send)

    def _authorized(self, scope: Scope) -> bool:
        headers = {k.lower(): v for k, v in (scope.get("headers") or [])}
        raw = headers.get(b"authorization", b"").decode("latin-1").strip()
        provided = raw[7:].strip() if raw[:7].lower() == "bearer " else ""
        if not provided:
            provided = headers.get(b"x-api-key", b"").decode("latin-1").strip()
        if not provided:
            return False
        # 先编码成 bytes：compare_digest 不接受含非 ASCII 字符的 str
        return hmac.compare_digest(provided.encode("utf-8"), (self.token or "").encode("utf-8"))

    @staticmethod
    async def _json(send: Send, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _configure_logging(level: str) -> None:
    # stdio 传输下 stdout 属于 MCP 协议通道，日志必须走 stderr
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="coursemanage-mcp",
        description="courseManage MCP 服务器：把课程管理系统接入 AstrBot 等第三方框架",
    )
    parser.add_argument("--version", action="version", version=f"coursemanage-mcp {__version__}")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        help="传输方式，默认取 COURSEMANAGE_MCP_TRANSPORT（stdio）",
    )
    parser.add_argument("--host", help="HTTP 监听地址，默认 0.0.0.0")
    parser.add_argument("--port", type=int, help="HTTP 监听端口，默认 8765")
    parser.add_argument("--path", help="Streamable HTTP 端点路径，默认 /mcp")
    parser.add_argument("--readonly", action="store_true", help="强制只读，不注册任何写操作工具")
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="打印已注册的工具清单后退出（不连接后端，便于 CI 自检）",
    )
    return parser.parse_args(argv)


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    changes: dict[str, Any] = {}
    if args.transport:
        changes["transport"] = args.transport
    if args.host:
        changes["host"] = args.host
    if args.port:
        changes["port"] = args.port
    if args.path:
        changes["path"] = args.path
    if args.readonly:
        changes["readonly"] = True
    if not changes:
        return settings
    updated = dataclasses.replace(settings, **changes)
    updated.validate()
    return updated


async def _list_tools(settings: Settings) -> int:
    client = CourseManageClient(settings)
    try:
        mcp = build_server(settings, client)
        tools = await mcp.list_tools()
        print(f"courseManage MCP {__version__} —— 共 {len(tools)} 个工具"
              f"（{'只读模式' if settings.readonly else '读写模式'}）")
        for item in sorted(tools, key=lambda t: t.name):
            summary = (item.description or "").strip().splitlines()
            print(f"  - {item.name}: {summary[0] if summary else ''}")
    finally:
        await client.aclose()
    return 0


async def _serve(settings: Settings) -> int:
    client = CourseManageClient(settings)
    mcp = build_server(settings, client)
    logger.info("courseManage MCP %s 启动：%s", __version__, settings.describe())

    try:
        if settings.transport == "stdio":
            await mcp.run_stdio_async()
            return 0

        import uvicorn

        if settings.transport == "sse":
            inner = mcp.sse_app()
            endpoint = "/sse"
        else:
            inner = mcp.streamable_http_app()
            endpoint = settings.path

        app = GatewayMiddleware(inner, token=settings.auth_token)
        logger.info(
            "MCP 端点：http://%s:%s%s（健康检查 /healthz）",
            settings.host,
            settings.port,
            endpoint,
        )
        if not settings.auth_token:
            logger.warning(
                "未设置 COURSEMANAGE_MCP_AUTH_TOKEN：任何能访问该端口的客户端都可调用工具，"
                "请勿直接暴露到公网。"
            )

        config = uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level.lower(),
            access_log=False,
        )
        await uvicorn.Server(config).serve()
        return 0
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        settings = _apply_overrides(Settings.from_env(), args)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 2

    _configure_logging(settings.log_level)

    runner = _list_tools if args.list_tools else _serve
    with contextlib.suppress(KeyboardInterrupt):
        return asyncio.run(runner(settings))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
