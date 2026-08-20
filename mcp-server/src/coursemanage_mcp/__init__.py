# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2024-2026 courseManage Contributors
"""courseManage MCP 服务器。

将 courseManage 后端 REST API 暴露为 Model Context Protocol 工具，
可直接被 AstrBot、Claude Desktop、Cherry Studio、Dify 等第三方框架调用。
"""

from .config import Settings
from .client import ApiError, CourseManageClient
from .server import build_server

__all__ = ["Settings", "ApiError", "CourseManageClient", "build_server", "__version__"]

__version__ = "1.0.0"
