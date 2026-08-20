# SPDX-License-Identifier: AGPL-3.0-only
"""配置解析测试。"""

from __future__ import annotations

import os

import pytest

from coursemanage_mcp.config import ConfigError, Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("COURSEMANAGE_"):
            monkeypatch.delenv(key, raising=False)


def test_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEMANAGE_API_BASE", "http://localhost:8000")
    with pytest.raises(ConfigError, match="TOKEN"):
        Settings.from_env()


def test_from_env_with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEMANAGE_API_BASE", "http://localhost:8000/")
    monkeypatch.setenv("COURSEMANAGE_USERNAME", "admin")
    monkeypatch.setenv("COURSEMANAGE_PASSWORD", "Admin.123")
    settings = Settings.from_env()
    assert settings.api_base == "http://localhost:8000"  # 末尾斜杠被去掉
    assert settings.transport == "stdio"
    assert settings.readonly is False
    assert settings.max_items == 50


def test_transport_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEMANAGE_TOKEN", "abc")
    for alias in ("http", "HTTP", "streamable_http", "streamable-http"):
        monkeypatch.setenv("COURSEMANAGE_MCP_TRANSPORT", alias)
        assert Settings.from_env().transport == "http"


def test_rejects_bad_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEMANAGE_TOKEN", "abc")
    monkeypatch.setenv("COURSEMANAGE_MCP_TRANSPORT", "grpc")
    with pytest.raises(ConfigError, match="MCP_TRANSPORT"):
        Settings.from_env()


def test_rejects_bad_api_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEMANAGE_TOKEN", "abc")
    monkeypatch.setenv("COURSEMANAGE_API_BASE", "backend:8000")
    with pytest.raises(ConfigError, match="http"):
        Settings.from_env()


def test_describe_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COURSEMANAGE_USERNAME", "admin")
    monkeypatch.setenv("COURSEMANAGE_PASSWORD", "super-secret")
    monkeypatch.setenv("COURSEMANAGE_MCP_AUTH_TOKEN", "client-secret")
    described = Settings.from_env().describe()
    assert "super-secret" not in described
    assert "client-secret" not in described
    assert "admin" in described
