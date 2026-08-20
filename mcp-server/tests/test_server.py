# SPDX-License-Identifier: AGPL-3.0-only
"""工具注册与只读模式测试。"""

from __future__ import annotations

import httpx
import respx

from coursemanage_mcp.client import CourseManageClient
from coursemanage_mcp.config import Settings
from coursemanage_mcp.server import build_server

BASE = "http://api.test"

READ_TOOLS = {
    "get_system_status",
    "get_site_info",
    "list_courses",
    "list_teachers",
    "list_classes",
    "list_students",
    "get_student",
    "list_rooms",
    "list_schedules",
    "get_schedules_by_day",
    "get_schedule",
    "list_schedule_conflicts",
    "get_absent_students",
    "list_leaves",
    "list_holidays",
    "get_dashboard_kpi",
    "get_teacher_workload",
    "get_room_utilization",
    "get_incomplete_schedules",
    "list_grades",
    "get_student_grade_trend",
    "get_student_evaluation_profile",
    "parse_smart_command",
}

WRITE_TOOLS = {
    "run_smart_command",
    "create_schedule",
    "complete_schedule",
    "postpone_schedule",
    "cancel_schedule",
    "update_attendance",
    "create_leave",
    "create_student",
    "create_course",
}

NOTIFICATION_TOOLS = {"notify_schedule"}


def _build(**kwargs):
    settings = Settings(api_base=BASE, token="T", **kwargs)
    client = CourseManageClient(settings)
    return settings, client, build_server(settings, client)


async def _tool_names(**kwargs) -> set[str]:
    _, client, mcp = _build(**kwargs)
    try:
        return {t.name for t in await mcp.list_tools()}
    finally:
        await client.aclose()


async def test_read_write_tools_registered() -> None:
    names = await _tool_names()
    missing = (READ_TOOLS | WRITE_TOOLS) - names
    assert not missing, f"缺少工具：{sorted(missing)}"


async def test_readonly_hides_write_tools() -> None:
    names = await _tool_names(readonly=True)
    assert READ_TOOLS <= names
    assert not (WRITE_TOOLS & names), f"只读模式下仍暴露了写工具：{sorted(WRITE_TOOLS & names)}"


async def test_notification_tool_is_opt_in() -> None:
    assert not (NOTIFICATION_TOOLS & await _tool_names())
    assert NOTIFICATION_TOOLS <= await _tool_names(allow_notifications=True)


async def test_every_tool_has_chinese_description() -> None:
    _, client, mcp = _build()
    try:
        tools = await mcp.list_tools()
    finally:
        await client.aclose()
    for tool in tools:
        assert tool.description, f"{tool.name} 缺少描述"
        assert any("\u4e00" <= ch <= "\u9fff" for ch in tool.description), f"{tool.name} 描述不是中文"


async def test_prompts_and_resources_registered() -> None:
    _, client, mcp = _build()
    try:
        prompts = {p.name for p in await mcp.list_prompts()}
        resources = {str(r.uri).rstrip("/") for r in await mcp.list_resources()}
    finally:
        await client.aclose()
    assert {"daily_briefing", "conflict_review"} <= prompts
    assert "coursemanage://today-schedules" in resources


@respx.mock
async def test_get_schedules_by_day_builds_date_range() -> None:
    route = respx.get(f"{BASE}/api/schedules").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )
    _, client, mcp = _build()
    try:
        await mcp.call_tool("get_schedules_by_day", {"day": "2026-03-02"})
    finally:
        await client.aclose()

    url = str(route.calls[0].request.url)
    assert "start_date=2026-03-02" in url
    assert "end_date=2026-03-02" in url


async def test_offline_schedule_requires_room() -> None:
    """线下课缺少 room_id 时必须报错，且错误信息要点出 room_id。

    不同 mcp SDK 版本下 FastMCP.call_tool 既可能抛出 ToolError，
    也可能返回 isError 结果，这里两种都接受，只要错误信息正确。
    """
    _, client, mcp = _build()
    payload = {
        "course_id": 1,
        "teacher_id": 1,
        "class_id": 1,
        "day_of_week": 1,
        "start_time": "19:00",
        "end_time": "20:30",
        "start_date": "2026-03-02",
        "end_date": "2026-03-02",
    }
    try:
        try:
            result = await mcp.call_tool("create_schedule", payload)
        except Exception as exc:
            assert "room_id" in str(exc)
        else:
            assert "room_id" in str(result)
    finally:
        await client.aclose()


@respx.mock
async def test_notifications_downgraded_by_default() -> None:
    route = respx.post(f"{BASE}/api/schedules/5/cancel").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    _, client, mcp = _build()
    try:
        await mcp.call_tool(
            "cancel_schedule",
            {"schedule_id": 5, "cancel_reason": "教师临时请假", "send_notification": True},
        )
    finally:
        await client.aclose()

    body = route.calls[0].request.content.decode()
    # 未开启 ALLOW_NOTIFICATIONS 时强制降级为 false，避免机器人误发群通知
    assert '"send_notification": false' in body or '"send_notification":false' in body


@respx.mock
async def test_list_limit_capped_by_max_items() -> None:
    route = respx.get(f"{BASE}/api/courses").mock(
        return_value=httpx.Response(200, json={"items": [], "total": 0})
    )
    _, client, mcp = _build(max_items=5)
    try:
        await mcp.call_tool("list_courses", {"limit": 200})
    finally:
        await client.aclose()

    assert "limit=5" in str(route.calls[0].request.url)
