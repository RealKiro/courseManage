# SPDX-License-Identifier: AGPL-3.0-only
"""API 客户端与格式化测试（使用 respx 拦截 HTTP）。"""

from __future__ import annotations

import httpx
import pytest
import respx

from coursemanage_mcp import formatting as fmt
from coursemanage_mcp.client import ApiError, CourseManageClient
from coursemanage_mcp.config import Settings

BASE = "http://api.test"


def _settings(**kwargs) -> Settings:
    defaults = dict(api_base=BASE, username="admin", password="pw")
    defaults.update(kwargs)
    return Settings(**defaults)


@respx.mock
async def test_login_then_request() -> None:
    login = respx.post(f"{BASE}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "T1", "token_type": "bearer"})
    )
    listing = respx.get(f"{BASE}/api/courses").mock(
        return_value=httpx.Response(200, json={"items": [{"id": 1, "name": "数学", "code": "MATH"}], "total": 1})
    )

    client = CourseManageClient(_settings())
    try:
        data = await client.get("/api/courses", limit=10, search=None)
    finally:
        await client.aclose()

    assert login.called
    assert listing.called
    request = listing.calls[0].request
    assert request.headers["authorization"] == "Bearer T1"
    # None 参数不会出现在 query 中
    assert "search" not in str(request.url)
    assert data["total"] == 1


@respx.mock
async def test_relogin_on_401() -> None:
    respx.post(f"{BASE}/api/auth/login").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "expired"}),
            httpx.Response(200, json={"access_token": "fresh"}),
        ]
    )
    route = respx.get(f"{BASE}/api/auth/me").mock(
        side_effect=[
            httpx.Response(401, json={"detail": "Token expired"}),
            httpx.Response(200, json={"username": "admin"}),
        ]
    )

    client = CourseManageClient(_settings())
    try:
        payload = await client.get("/api/auth/me")
    finally:
        await client.aclose()

    assert payload["username"] == "admin"
    assert route.call_count == 2
    assert route.calls[1].request.headers["authorization"] == "Bearer fresh"


@respx.mock
async def test_premium_403_message() -> None:
    respx.post(f"{BASE}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "T"})
    )
    respx.get(f"{BASE}/api/statistics/kpi").mock(
        return_value=httpx.Response(403, json={"detail": "功能 '运营大屏' 需要授权"})
    )

    client = CourseManageClient(_settings())
    try:
        with pytest.raises(ApiError) as excinfo:
            await client.get("/api/statistics/kpi")
    finally:
        await client.aclose()

    assert "系统授权管理" in str(excinfo.value)
    assert excinfo.value.status == 403


@respx.mock
async def test_bool_params_serialized() -> None:
    respx.post(f"{BASE}/api/auth/login").mock(
        return_value=httpx.Response(200, json={"access_token": "T"})
    )
    route = respx.get(f"{BASE}/api/students").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )

    client = CourseManageClient(_settings())
    try:
        await client.get("/api/students", is_active=True)
    finally:
        await client.aclose()

    assert "is_active=true" in str(route.calls[0].request.url)


@respx.mock
async def test_static_token_skips_login() -> None:
    route = respx.get(f"{BASE}/api/courses").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )

    client = CourseManageClient(_settings(username=None, password=None, token="static"))
    try:
        await client.get("/api/courses")
    finally:
        await client.aclose()

    assert route.called
    assert route.calls[0].request.headers["authorization"] == "Bearer static"
    assert all("/api/auth/login" not in str(call.request.url) for call in respx.calls)


def test_schedule_projection_is_compact() -> None:
    raw = {
        "id": 7,
        "start_date": "2026-03-02",
        "end_date": "2026-03-02",
        "day_of_week": 1,
        "start_time": "19:00",
        "end_time": "20:30",
        "course": {"id": 3, "name": "初中数学"},
        "teacher": {"id": 5, "name": "王老师"},
        "class_": {"id": 9, "name": "三年级A班"},
        "room": {"id": 2, "name": "301教室"},
        "room_type": "offline_physical",
        "execution_status": "pending",
        "schedule_type": "formal",
        "has_conflict": False,
        "conflict_reason": "不该出现",
        "available_time_slots": "一大堆无用字段",
        "scheduled_students": [
            {"student_id": 1, "attendance_status": "present"},
            {"student_id": 2, "attendance_status": "absent"},
        ],
    }
    out = fmt.schedule(raw)
    assert out["weekday"] == "周一"
    assert out["status"] == "待上课"
    assert out["room_type"] == "线下"
    assert out["date"] == "2026-03-02"
    assert out["attendance"] == {"出席": 1, "缺席": 1}
    assert "conflict" not in out
    assert "available_time_slots" not in out


def test_paginated_truncation_note() -> None:
    payload = {"items": [{"id": i, "name": f"课程{i}", "code": str(i)} for i in range(10)], "total": 10}
    out = fmt.paginated(payload, "course", limit=3)
    assert out["returned"] == 3
    assert len(out["items"]) == 3
    assert out["total"] == 10
    assert "note" in out
